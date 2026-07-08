"""Unit/component tests for per-cluster budget allocation in the orchestrator.

Covers:
- truncate_payload is called on each payload before LLM dispatch
- Greedy per-cluster allocation (largest-first)
- Overflow clusters get stub_summary
- Per-cluster parse-failure isolation
- Single-call happy path when budget allows
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from noticias.llm.client import LLMClient
from noticias.models.source import Lean, Source, SourceConfig
from noticias.pipeline.fetch import FetchResult
from tests.helpers import make_batch_response, make_item


def _make_item_for_source(
    title: str,
    source: str,
    lean: str = "center",
    body: str | None = None,
    url: str | None = None,
    published_at_delta_hours: int = 0,
) -> "NewsItem":  # noqa: F821
    """Create a NewsItem with source-specific metadata."""
    from datetime import datetime, timezone

    if body is None:
        body = f"Article body content for {source} with enough words for tokenization purposes."
    if url is None:
        url = f"https://{source}.example.com/article"
    base_dt = datetime.now(timezone.utc) - timedelta(hours=1)
    dt = base_dt - timedelta(hours=published_at_delta_hours)
    return make_item(
        title=title,
        url=url,
        source=source,
        lean=lean,
        body=body,
        published_at=dt,
    )


# ── Cluster fixtures ─────────────────────────────────────────────────────────

# 3 clusters that form from these items
_SAMPLE_CLUSTER_ITEMS = [
    # Cluster 1: 3 sources (largest, ~720 chars total)
    _make_item_for_source(
        title="Corte Suprema argentina falla libertad expresion en fallo historico",
        source="pagina12", lean="left",
        body="La Corte Suprema falló a favor de la libertad de expresión en un fallo histórico que sienta precedente judicial en el país con respaldo institucional.",
        url="https://example.com/politica/corte/fallo-libertad-expresion-argentina",
        published_at_delta_hours=0,
    ),
    _make_item_for_source(
        title="Suprema Corte fallo a favor de la libertad de expresion en Argentina",
        source="infobae", lean="center",
        body="La Corte Suprema de Argentina falló a favor de la libertad de expresión en un fallo histórico que sienta un importante precedente judicial para el país con respaldo institucional.",
        url="https://example.com/politica/suprema/juicio-fallo-libertad-historico",
        published_at_delta_hours=1,
    ),
    _make_item_for_source(
        title="La Corte Suprema falla a favor de libertad de expresion en fallo nacional",
        source="clarin", lean="right",
        body="La Corte Suprema falla a favor de la libertad de expresión en un fallo histórico que sienta precedente para el país con respaldo institucional judicial.",
        url="https://example.com/politica/nacional/fallo-expresion-historico",
        published_at_delta_hours=2,
    ),
    # Cluster 2: 2 sources (medium)
    _make_item_for_source(
        title="Gobierno argentino nuevo plan economico ajuste fiscal reformas",
        source="pagina12", lean="left",
        body="El gobierno anunció un nuevo plan económico con medidas de ajuste fiscal y reformas estructurales para el próximo trimestre fiscal en Argentina.",
        url="https://example.com/economia/plan/anuncio-ajuste-fiscal-reformas",
        published_at_delta_hours=4,
    ),
    _make_item_for_source(
        title="Gobierno de Argentina anuncia plan economico en conferencia prensa",
        source="clarin", lean="right",
        body="El gobierno presentó un nuevo plan económico en conferencia de prensa con medidas de ajuste fiscal para el próximo trimestre en Argentina.",
        url="https://example.com/economia/plan/conferencia-prensa-anuncio",
        published_at_delta_hours=5,
    ),
    # Cluster 3: 1 source (smallest, ~90 chars)
    _make_item_for_source(
        title="Resultados deportivos del fin de semana en Argentina futbol",
        source="infobae", lean="center",
        body="Resultados deportivos del fin de semana con detalles de los partidos más importantes del torneo local de fútbol argentino.",
        url="https://deportes.example.com/futbol/resultados-fin-semana",
        published_at_delta_hours=3,
    ),
]


def _make_config() -> SourceConfig:
    return SourceConfig(
        sources=[
            Source(name="pagina12", url="https://p12.com/rss", lean=Lean.LEFT),
            Source(name="infobae", url="https://infobae.com/rss", lean=Lean.CENTER),
            Source(name="clarin", url="https://clarin.com/rss", lean=Lean.RIGHT),
        ],
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


# ── Group A: truncate_payload wiring ────────────────────────────────────────


class TestTruncatePayloadWiring:
    """truncate_payload is invoked on each payload before LLM dispatch."""

    @pytest.mark.asyncio
    async def test_truncate_payload_called_per_cluster(self) -> None:
        """truncate_payload is called once per cluster payload."""
        from noticias.pipeline.family import truncate_payload

        config = _make_config()
        sources = config.sources

        with (
            patch(
                "noticias.pipeline.orchestrator.fetch_all_sources",
                new_callable=AsyncMock,
            ) as mock_fetch,
            patch(
                "noticias.pipeline.orchestrator.truncate_payload",
                wraps=truncate_payload,
            ) as spy_truncate,
            patch(
                "noticias.llm.client.litellm.acompletion",
                new_callable=AsyncMock,
            ) as mock_llm,
        ):
            mock_fetch.return_value = FetchResult(
                items=_SAMPLE_CLUSTER_ITEMS,
                failures=[],
            )
            batch_json = make_batch_response([
                (["Corte Suprema argentina falla libertad expresion en fallo historico",
                  "Suprema Corte fallo a favor de la libertad de expresion en Argentina",
                  "La Corte Suprema falla a favor de libertad de expresion en fallo nacional"],
                 "Summary 1", ["H1"]),
                (["Gobierno argentino nuevo plan economico ajuste fiscal reformas",
                  "Gobierno de Argentina anuncia plan economico en conferencia prensa"],
                 "Summary 2", ["H2"]),
                (["Resultados deportivos del fin de semana en Argentina futbol"],
                 "Summary 3", ["H3"]),
            ])
            mock_llm.return_value = MockLLMResponse(batch_json)

            llm_client = LLMClient(token_budget=5000)
            llm_client._keys["groq"] = "fake_key"

            from noticias.pipeline.orchestrator import run_pipeline_async

            clusters = await run_pipeline_async(
                sources=sources,
                window=timedelta(hours=24),
                llm=llm_client,
                config=config,
            )

        # Should have 3 clusters
        assert len(clusters) == 3

        # truncate_payload was called exactly once per cluster (3 times)
        assert spy_truncate.call_count == len(clusters), (
            f"Expected {len(clusters)} calls to truncate_payload, "
            f"got {spy_truncate.call_count}"
        )
