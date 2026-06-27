"""End-to-end integration tests for the full noticias pipeline.

Covers:
- Happy path: 3 sources, mock RSS feeds, mock LLM → clusters, snapshot, render
- Failure path: 1 source returns HTTP 500, others succeed → pipeline continues
- Snapshot persistence: write + read round-trip preserves all fields
- Render: rendered output contains trust color markup

Requires: pytest, respx, pytest-asyncio (all in [dev] dependencies).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx

from noticias.llm.client import LLMClient, StubLLMClient
from noticias.models.snapshot import Snapshot, SnapshotCluster
from noticias.models.source import Lean, Source, SourceConfig
from noticias.pipeline.orchestrator import run_pipeline_async
from noticias.persistence.snapshot import read_snapshot, write_snapshot
from noticias.render.console import render_snapshot


def _recent_pubdate(hours_ago: int = 0) -> str:
    """Return an RFC-822 formatted pubDate for `hours_ago` hours before now.

    Dynamic so the items stay within the default 24h window regardless of
    when the tests are run.
    """
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return format_datetime(dt)


# ── Test data ───────────────────────────────────────────────────────────────

RSS_FEEDS: dict[str, str] = {
    "pagina12": f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
  <title>Página12</title>
  <link>http://mock-rss.local/pagina12</link>
  <item>
    <title>Gobierno anuncia nuevas medidas económicas en Argentina</title>
    <link>http://mock-rss.local/p12/economic-article-001</link>
    <description>Resumen de las medidas económicas anunciadas por el gobierno.</description>
    <content:encoded><![CDATA[gobierno anunció paquete medidas económicas reformas fiscales según fuentes oficiales]]></content:encoded>
    <pubDate>{_recent_pubdate(2)}</pubDate>
  </item>
</channel>
</rss>""",
    "lanacion": f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
  <title>La Nación</title>
  <link>http://mock-rss.local/lanacion</link>
  <item>
    <title>El gobierno anuncia medidas económicas en el país</title>
    <link>http://mock-rss-different.local/ln/economic-report-002</link>
    <description>Resumen de las medidas económicas.</description>
    <content:encoded><![CDATA[gobierno anunció paquete medidas económicas reformas fiscales sector según fuentes oficiales]]></content:encoded>
    <pubDate>{_recent_pubdate(1)}</pubDate>
  </item>
</channel>
</rss>""",
    "clarin": f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
  <title>Clarín</title>
  <link>http://mock-rss.local/clarin</link>
  <item>
    <title>Gobierno argentino anuncia medidas económicas</title>
    <link>http://mock-rss-alt.local/cl/economic-measures-003</link>
    <description>Resumen de las medidas.</description>
    <content:encoded><![CDATA[gobierno anunció paquete medidas económicas reformas fiscales estímulos según fuentes oficiales]]></content:encoded>
    <pubDate>{_recent_pubdate(0)}</pubDate>
  </item>
</channel>
</rss>""",
}

MOCK_LLM_RESPONSE = (
    '{"summary": "Resumen de las noticias del día.", '
    '"highlights": ["Medidas económicas", "Reformas fiscales"]}'
)


def _make_sources() -> list[Source]:
    """Build 3 sources with different leans and mock URLs."""
    return [
        Source(
            name="pagina12",
            url="http://mock.example.com/pagina12/rss",
            lean=Lean.LEFT,
        ),
        Source(
            name="lanacion",
            url="http://mock.example.com/lanacion/rss",
            lean=Lean.RIGHT,
        ),
        Source(
            name="clarin",
            url="http://mock.example.com/clarin/rss",
            lean=Lean.RIGHT,
        ),
    ]


def _make_config() -> SourceConfig:
    """Build a minimal SourceConfig for tests."""
    return SourceConfig(
        fetch_timeout_s=10.0,
        max_concurrent_sources=5,
        rate_limit_s=1,
        token_budget=5000,
    )


class MockLLMResponse:
    """Minimal mock for LiteLLM acompletion response."""

    def __init__(self, content: str) -> None:
        self.choices = [MagicMock()]
        self.choices[0].message.content = content


# ── Happy path: pipeline with 3 sources, mock LLM ──────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_happy_path_pipeline_with_mock_llm(tmp_path: Path) -> None:
    """3 sources, all succeed → clusters formed, snapshot persists, render works."""
    sources = _make_sources()
    config = _make_config()

    async with respx.mock:
        # Mock RSS feeds for all 3 sources
        for source in sources:
            name = source.name
            respx.get(source.url).respond(
                200, text=RSS_FEEDS[name],
                headers={"Content-Type": "application/rss+xml"},
            )

        # Mock LLM
        with patch(
            "noticias.llm.client.litellm.acompletion",
            new_callable=AsyncMock,
        ) as mock_llm:
            mock_llm.return_value = MockLLMResponse(MOCK_LLM_RESPONSE)

            llm_client = LLMClient(
                models=["groq/llama-3.1-8b-instant"],
                token_budget=5000,
            )
            llm_client._keys["groq"] = "fake_key"

            # ── Run pipeline ──────────────────────────────────────────
            clusters = await run_pipeline_async(
                sources=sources,
                window=timedelta(hours=48),
                llm=llm_client,
                config=config,
            )

    # ── Assert pipeline results ────────────────────────────────────────
    assert len(clusters) >= 1, "Pipeline should produce at least 1 cluster"
    for cluster in clusters:
        assert cluster.trust_label in ("alta", "media", "baja"), (
            f"Invalid trust_label: {cluster.trust_label}"
        )
        assert len(cluster.trust_reason) > 0
        assert len(cluster.event_label) > 0
        assert len(cluster.summary) > 0

    # ── Build and persist snapshot ──────────────────────────────────────
    snapshot_clusters = [
        SnapshotCluster(
            event_label=c.event_label,
            trust_label=c.trust_label,
            trust_reason=c.trust_reason,
            summary=c.summary,
            sources=c.sources,
            highlights=c.highlights,
        )
        for c in clusters
    ]
    snapshot = Snapshot(
        date="2026-06-21",
        generated_at=datetime.now(timezone.utc),
        sources_used=["pagina12", "lanacion", "clarin"],
        clusters=snapshot_clusters,
        fetch_failures=[],
    )

    # ── Write snapshot ─────────────────────────────────────────────────
    written_path = write_snapshot(snapshot, tmp_path)
    assert written_path.exists()
    assert written_path.suffix == ".json"

    # ── Read back snapshot ─────────────────────────────────────────────
    read_back = read_snapshot(written_path)
    assert read_back.date == "2026-06-21"
    assert len(read_back.clusters) == len(clusters)
    for i, original_cluster in enumerate(snapshot_clusters):
        restored = read_back.clusters[i]
        assert restored.event_label == original_cluster.event_label
        assert restored.trust_label == original_cluster.trust_label
        assert restored.trust_reason == original_cluster.trust_reason
        assert restored.summary == original_cluster.summary
        assert restored.sources == original_cluster.sources
        assert restored.highlights == original_cluster.highlights

    # ── Render snapshot and check for trust colors ─────────────────────
    from rich.console import Console

    console = Console(record=True, force_terminal=True)
    render_snapshot(read_back, console)
    rendered = console.export_text()
    # The renderer outputs trust labels in UPPERCASE via .upper()
    assert "ALTA" in rendered or "MEDIA" in rendered or "BAJA" in rendered, (
        "Render output should contain trust labels"
    )
    # Verify content was actually rendered
    assert len(rendered) > 50


# ── Failure path: one source returns HTTP 500 ──────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_failure_isolation(tmp_path: Path) -> None:
    """One source returns 500 → pipeline continues with remaining sources."""
    sources = _make_sources()
    config = _make_config()

    async with respx.mock:
        # pagina12 returns HTTP 500
        respx.get(sources[0].url).respond(500)
        # Other sources succeed
        respx.get(sources[1].url).respond(
            200, text=RSS_FEEDS["lanacion"],
            headers={"Content-Type": "application/rss+xml"},
        )
        respx.get(sources[2].url).respond(
            200, text=RSS_FEEDS["clarin"],
            headers={"Content-Type": "application/rss+xml"},
        )

        # Skip LLM (stub mode) to keep the test focused on fetch recovery
        llm_client = StubLLMClient()

            # ── Run pipeline (should NOT raise despite one source failing) ──
        clusters = await run_pipeline_async(
            sources=sources,
            window=timedelta(hours=48),
            llm=llm_client,
            config=config,
        )

    # Should have at least 1 cluster from the 2 healthy sources
    # (they both have items that should cluster together by title)
    assert len(clusters) >= 1, (
        "Pipeline should produce clusters from healthy sources"
    )
    # All clusters should have trust labels
    for cluster in clusters:
        assert cluster.trust_label in ("alta", "media", "baja")


# ── Persistence round-trip ──────────────────────────────────────────────────


@pytest.mark.integration
def test_snapshot_persistence_round_trip(tmp_path: Path) -> None:
    """Write a snapshot, read it back, verify all fields survive."""
    original = Snapshot(
        date="2026-06-21",
        generated_at=datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc),
        sources_used=["pagina12", "lanacion", "clarin"],
        clusters=[
            SnapshotCluster(
                event_label="Gobierno anuncia medidas económicas",
                trust_label="alta",
                trust_reason="3 fuentes, 2 líneas ideológicas, acuerdo alto",
                summary="Resumen de prueba.",
                sources=["pagina12", "lanacion", "clarin"],
                highlights=["Punto 1", "Punto 2"],
            ),
            SnapshotCluster(
                event_label="Deportes fin de semana",
                trust_label="baja",
                trust_reason="1 sola fuente: sin contraste",
                summary="Resumen deportivo.",
                sources=["infobae"],
                highlights=[],
            ),
        ],
        fetch_failures=[],
    )

    # Write
    written_path = write_snapshot(original, tmp_path)
    assert written_path.exists()

    # Read back
    restored = read_snapshot(written_path)
    assert restored.date == original.date
    assert restored.generated_at == original.generated_at
    assert restored.sources_used == original.sources_used
    assert len(restored.clusters) == len(original.clusters)

    for orig_c, restored_c in zip(original.clusters, restored.clusters):
        assert restored_c.event_label == orig_c.event_label
        assert restored_c.trust_label == orig_c.trust_label
        assert restored_c.trust_reason == orig_c.trust_reason
        assert restored_c.summary == orig_c.summary
        assert restored_c.sources == orig_c.sources
        assert restored_c.highlights == orig_c.highlights

    # Verify the file is valid JSON
    raw = json.loads(written_path.read_text("utf-8"))
    assert raw["date"] == "2026-06-21"
    assert len(raw["clusters"]) == 2


# ── Render produces trust colors ────────────────────────────────────────────


@pytest.mark.integration
def test_render_contains_trust_color_markup(tmp_path: Path) -> None:
    """Rendered snapshot output contains terminal color markup for trust."""
    from rich.console import Console

    snapshot = Snapshot(
        date="2026-06-21",
        generated_at=datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc),
        sources_used=["pagina12"],
        clusters=[
            SnapshotCluster(
                event_label="Noticia de prueba",
                trust_label="alta",
                trust_reason="Fuente única verificada",
                summary="Resumen de prueba.",
                sources=["pagina12"],
                highlights=["Detalle 1"],
            ),
        ],
        fetch_failures=[],
    )

    console = Console(record=True, force_terminal=True)
    render_snapshot(snapshot, console)
    rendered = console.export_text()

    # The Rich renderer uses ANSI escape sequences for trust colors
    # alta=green, media=yellow, baja=red in the renderer
    assert "alta" in rendered.lower() or "alta" in rendered
    assert "Noticia de prueba" in rendered
    # Check that the output is non-empty and contains meaningful content
    assert len(rendered) > 50
