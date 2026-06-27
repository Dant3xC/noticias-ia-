"""Component tests for the pipeline orchestrator with filter stages.

Covers the content filter and topic filter stages within the full pipeline
using mocked fetch and mocked LLM. Each test verifies that items pass
through or are dropped by the correct filter stage.

Test cases:
- Happy path with content filter: entertainment items dropped before clustering
- Content filter opt-out: ``--no-filter`` passes all items through
- Topic filter: items matching topic kept, non-matching dropped
- Topic filter opt-out: ``no_topics=True`` skips topic filter
- Persistent topics from config used when no CLI topics given
- CLI topics override config topics
- Topic cap: more than 10 topics → only first 10 used + warning
- Empty results path: when all items dropped by filters, return empty clusters
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from noticias.llm.client import LLMClient
from noticias.models.source import Lean, Source, SourceConfig
from noticias.pipeline.fetch import FetchFailure, FetchResult
from noticias.pipeline.options import PipelineOptions
from noticias.pipeline.orchestrator import run_pipeline_async
from tests.helpers import make_item


# ── Test helpers ───────────────────────────────────────────────────────────

# Use a dynamic base timestamp so items stay within test time windows
# regardless of when the test is run.
_BASE_DT = datetime.now(timezone.utc) - timedelta(hours=1)


def _item(
    title: str = "Noticia importante",
    body: str = "Contenido de la noticia con informacion relevante.",
    source: str = "pagina12",
    lean: str = "left",
    url: str | None = None,
) -> "NewsItem":  # noqa: F821
    """Create a NewsItem with dynamic timestamp and unique URL per call."""
    if url is None:
        # Use title hash to make each item's URL unique (avoid dedup).
        url = f"https://{source}.example.com/article/{hash(title) % 1000000}"
    return make_item(
        title=title,
        url=url,
        source=source,
        lean=lean,
        body=body,
        published_at=_BASE_DT,
    )


def _make_config(topics: list[str] | None = None) -> SourceConfig:
    """Build a SourceConfig with 3 sources and optional persistent topics."""
    kwargs: dict = {
        "sources": [
            Source(name="pagina12", url="https://p12.com/rss", lean=Lean.LEFT),
            Source(name="infobae", url="https://infobae.com/rss", lean=Lean.CENTER),
            Source(name="clarin", url="https://clarin.com/rss", lean=Lean.RIGHT),
        ],
        "fetch_timeout_s": 10.0,
        "max_concurrent_sources": 5,
        "rate_limit_s": 1,
    }
    if topics is not None:
        kwargs["topics"] = topics
    return SourceConfig(**kwargs)


class MockLLMResponse:
    """Minimal mock for LiteLLM acompletion response."""

    def __init__(self, content: str) -> None:
        self.choices = [MagicMock()]
        self.choices[0].message.content = content


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_content_filter_drops_entertainment_items() -> None:
    """Happy path: items with entertainment keywords are dropped before clustering."""
    config = _make_config()
    sources = config.sources

    items = [
        _item(title="Noticia política importante sobre economía", source="infobae", lean="center"),
        _item(title="Horóscopo de hoy: qué dicen los astros", source="pagina12", lean="left"),
        _item(title="Gran Hermano: la gala de esta noche", source="clarin", lean="right"),
        _item(title="El presidente anunció nuevas medidas", source="lanacion", lean="right"),
    ]

    with (
        patch(
            "noticias.pipeline.orchestrator.fetch_all_sources",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "noticias.llm.client.litellm.acompletion",
            new_callable=AsyncMock,
        ) as mock_llm,
    ):
        mock_fetch.return_value = FetchResult(items=items, failures=[])
        mock_llm.return_value = MockLLMResponse(
            '{"summary": "Resumen.", "highlights": []}',
        )

        llm_client = LLMClient(token_budget=5000)
        llm_client._keys["groq"] = "fake_key"

        opts = PipelineOptions()
        clusters = await run_pipeline_async(
            sources=sources,
            window=timedelta(hours=48),
            llm=llm_client,
            config=config,
            options=opts,
        )

    # Entertainment items were dropped, only 2 real news items remain.
    # 2 items with different titles about different topics → won't cluster
    # → each is its own cluster (unless they cluster via domain+slug fallback).
    # At minimum, we should have clusters, and they should NOT contain
    # entertainment titles.
    assert len(clusters) > 0
    all_titles = []
    for c in clusters:
        for item in c.items:
            all_titles.append(item.title)
    assert "Horóscopo de hoy: qué dicen los astros" not in all_titles
    assert "Gran Hermano: la gala de esta noche" not in all_titles


@pytest.mark.asyncio
async def test_content_filter_opt_out() -> None:
    """``no_filter=True`` passes ALL items through the content filter."""
    config = _make_config()
    sources = config.sources

    items = [
        _item(title="Horóscopo de hoy", source="pagina12", lean="left"),
        _item(title="Noticia política importante", source="infobae", lean="center"),
        _item(title="Gran Hermano: lo último", source="clarin", lean="right"),
    ]

    with (
        patch(
            "noticias.pipeline.orchestrator.fetch_all_sources",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "noticias.llm.client.litellm.acompletion",
            new_callable=AsyncMock,
        ) as mock_llm,
    ):
        mock_fetch.return_value = FetchResult(items=items, failures=[])
        mock_llm.return_value = MockLLMResponse(
            '{"summary": "Resumen.", "highlights": []}',
        )

        llm_client = LLMClient(token_budget=5000)
        llm_client._keys["groq"] = "fake_key"

        opts = PipelineOptions(no_filter=True)
        clusters = await run_pipeline_async(
            sources=sources,
            window=timedelta(hours=48),
            llm=llm_client,
            config=config,
            options=opts,
        )

    # With no_filter=True, entertainment items survive the content filter.
    # The 3 items may or may not cluster together depending on similarity.
    # But ALL 3 items should appear in at least one cluster.
    all_titles = set()
    for c in clusters:
        for item in c.items:
            all_titles.add(item.title)
    assert "Horóscopo de hoy" in all_titles
    assert "Gran Hermano: lo último" in all_titles


@pytest.mark.asyncio
async def test_topic_filter_keeps_matching() -> None:
    """Topic filter: items matching a topic are kept, non-matching dropped."""
    config = _make_config()
    sources = config.sources

    items = [
        _item(
            title="Crisis económica: el PBI cayó 3%",
            body="La economía argentina enfrenta una crisis sin precedentes.",
            source="infobae", lean="center",
        ),
        _item(
            title="Boca Juniors campeón del torneo",
            body="Boca Juniors ganó el torneo de fútbol argentino.",
            source="clarin", lean="right",
        ),
        _item(
            title="Nueva tecnología revoluciona la medicina",
            body="Un avance tecnológico en el campo de la medicina.",
            source="lanacion", lean="right",
        ),
    ]

    with (
        patch(
            "noticias.pipeline.orchestrator.fetch_all_sources",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "noticias.llm.client.litellm.acompletion",
            new_callable=AsyncMock,
        ) as mock_llm,
    ):
        mock_fetch.return_value = FetchResult(items=items, failures=[])
        mock_llm.return_value = MockLLMResponse(
            '{"summary": "Resumen.", "highlights": []}',
        )

        llm_client = LLMClient(token_budget=5000)
        llm_client._keys["groq"] = "fake_key"

        opts = PipelineOptions(topics=["economía"])
        clusters = await run_pipeline_async(
            sources=sources,
            window=timedelta(hours=48),
            llm=llm_client,
            config=config,
            options=opts,
        )

    # Only the "economía" item survives the topic filter.
    # Single item → single cluster.
    assert len(clusters) == 1
    cluster_titles = {item.title for c in clusters for item in c.items}
    assert "Crisis económica: el PBI cayó 3%" in cluster_titles
    assert "Boca Juniors campeón del torneo" not in cluster_titles
    assert "Nueva tecnología revoluciona la medicina" not in cluster_titles


@pytest.mark.asyncio
async def test_topic_filter_opt_out() -> None:
    """``no_topics=True`` skips topic filter entirely."""
    config = _make_config()
    sources = config.sources

    items = [
        _item(title="Noticia de economía", body="Contenido económico.", source="infobae", lean="center"),
        _item(title="Noticia de fútbol", body="Contenido deportivo.", source="clarin", lean="right"),
    ]

    with (
        patch(
            "noticias.pipeline.orchestrator.fetch_all_sources",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "noticias.llm.client.litellm.acompletion",
            new_callable=AsyncMock,
        ) as mock_llm,
    ):
        mock_fetch.return_value = FetchResult(items=items, failures=[])
        mock_llm.return_value = MockLLMResponse(
            '{"summary": "Resumen.", "highlights": []}',
        )

        llm_client = LLMClient(token_budget=5000)
        llm_client._keys["groq"] = "fake_key"

        # Even with topics set, no_topics=True should skip the filter
        opts = PipelineOptions(topics=["economía"], no_topics=True)
        clusters = await run_pipeline_async(
            sources=sources,
            window=timedelta(hours=48),
            llm=llm_client,
            config=config,
            options=opts,
        )

    # Both items survive (topic filter skipped).
    all_titles = set()
    for c in clusters:
        for item in c.items:
            all_titles.add(item.title)
    assert "Noticia de economía" in all_titles
    assert "Noticia de fútbol" in all_titles


@pytest.mark.asyncio
async def test_persistent_topics_from_config() -> None:
    """Config topics used when CLI topics are empty."""
    config = _make_config(topics=["fútbol"])
    sources = config.sources

    items = [
        _item(
            title="La selección argentina ganó",
            body="La selección de fútbol argentina ganó el partido.",
            source="clarin", lean="right",
        ),
        _item(
            title="Subió la bolsa",
            body="La bolsa de valores subió 2% hoy.",
            source="infobae", lean="center",
        ),
    ]

    with (
        patch(
            "noticias.pipeline.orchestrator.fetch_all_sources",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "noticias.llm.client.litellm.acompletion",
            new_callable=AsyncMock,
        ) as mock_llm,
    ):
        mock_fetch.return_value = FetchResult(items=items, failures=[])
        mock_llm.return_value = MockLLMResponse(
            '{"summary": "Resumen.", "highlights": []}',
        )

        llm_client = LLMClient(token_budget=5000)
        llm_client._keys["groq"] = "fake_key"

        # No CLI topics — pipeline should use config.topics
        opts = PipelineOptions()
        clusters = await run_pipeline_async(
            sources=sources,
            window=timedelta(hours=48),
            llm=llm_client,
            config=config,
            options=opts,
        )

    # Only the fútbol item survives.
    assert len(clusters) == 1
    titles = {item.title for c in clusters for item in c.items}
    assert "La selección argentina ganó" in titles
    assert "Subió la bolsa" not in titles


@pytest.mark.asyncio
async def test_cli_topics_override_config() -> None:
    """CLI topics override config topics when explicitly provided."""
    config = _make_config(topics=["fútbol"])
    sources = config.sources

    items = [
        _item(
            title="Nueva ley de economía aprobada",
            body="El congreso aprobó la nueva ley de economía.",
            source="infobae", lean="center",
        ),
        _item(
            title="Fútbol: clásico el fin de semana",
            body="Se viene el clásico de fútbol este fin de semana.",
            source="clarin", lean="right",
        ),
    ]

    with (
        patch(
            "noticias.pipeline.orchestrator.fetch_all_sources",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "noticias.llm.client.litellm.acompletion",
            new_callable=AsyncMock,
        ) as mock_llm,
    ):
        mock_fetch.return_value = FetchResult(items=items, failures=[])
        mock_llm.return_value = MockLLMResponse(
            '{"summary": "Resumen.", "highlights": []}',
        )

        llm_client = LLMClient(token_budget=5000)
        llm_client._keys["groq"] = "fake_key"

        # CLI topics override config topics
        opts = PipelineOptions(topics=["economía"])
        clusters = await run_pipeline_async(
            sources=sources,
            window=timedelta(hours=48),
            llm=llm_client,
            config=config,
            options=opts,
        )

    # Only the economía item survives (CLI override).
    assert len(clusters) == 1
    titles = {item.title for c in clusters for item in c.items}
    assert "Nueva ley de economía aprobada" in titles
    assert "Fútbol: clásico el fin de semana" not in titles


@pytest.mark.asyncio
async def test_topic_cap_with_warning() -> None:
    """More than 10 topics → only first 10 used + warning logged.

    Verifies:
    1. A warning is logged when topic count exceeds the cap.
    2. Some items survive the pipeline (the cap-limited topics match).
    3. At least some items were filtered out (surviving count < total items).
    """
    config = _make_config()
    sources = config.sources

    # 12 items from 3 sources, each with a distinct topic mention.
    items = [
        _item(title=f"Noticia política {i}",
              body=f"cubre_tema_{i}",
              source=["pagina12", "infobae", "clarin"][i % 3],
              lean=["left", "center", "right"][i % 3])
        for i in range(12)
    ]

    with (
        patch(
            "noticias.pipeline.orchestrator.fetch_all_sources",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "noticias.llm.client.litellm.acompletion",
            new_callable=AsyncMock,
        ) as mock_llm,
        patch("noticias.pipeline.orchestrator.logger") as mock_logger,
    ):
        mock_fetch.return_value = FetchResult(items=items, failures=[])
        mock_llm.return_value = MockLLMResponse(
            '{"summary": "Resumen.", "highlights": []}',
        )

        llm_client = LLMClient(token_budget=5000)
        llm_client._keys["groq"] = "fake_key"

        # 12 topics but max_topics=10. Only first 10 topics are used.
        topics_12 = [f"tema_{i}" for i in range(12)]
        opts = PipelineOptions(topics=topics_12)
        clusters = await run_pipeline_async(
            sources=sources,
            window=timedelta(hours=48),
            llm=llm_client,
            config=config,
            options=opts,
        )

    # Warning was logged about topic cap
    mock_logger.warning.assert_called_once()

    # Some clusters should exist (first 10 items matched first 10 topics).
    # But some items were dropped (items 10-11 beyond cap).
    # With 12 input items, at most 10 survive the topic filter.
    surviving_count = sum(len(c.items) for c in clusters)
    assert surviving_count > 0, "Some items should survive the topic filter"
    assert surviving_count < 12, "Items beyond the topic cap should be dropped"



@pytest.mark.asyncio
async def test_empty_results_when_all_dropped_by_content_filter() -> None:
    """When all items are dropped by content filter, return empty clusters."""
    config = _make_config()
    sources = config.sources

    items = [
        _item(title="Horóscopo de hoy"),
        _item(title="Gran Hermano: lo último"),
    ]

    with (
        patch(
            "noticias.pipeline.orchestrator.fetch_all_sources",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = FetchResult(items=items, failures=[])

        llm_client = LLMClient(token_budget=5000)

        opts = PipelineOptions()
        clusters = await run_pipeline_async(
            sources=sources,
            window=timedelta(hours=48),
            llm=llm_client,
            config=config,
            options=opts,
        )

    assert clusters == []


@pytest.mark.asyncio
async def test_empty_results_when_all_dropped_by_topic_filter() -> None:
    """When all items are dropped by topic filter, return empty clusters."""
    config = _make_config()
    sources = config.sources

    items = [
        _item(title="Política internacional", body="Noticias del mundo.", source="infobae", lean="center"),
        _item(title="Tecnología de punta", body="Avances tecnológicos.", source="clarin", lean="right"),
    ]

    with (
        patch(
            "noticias.pipeline.orchestrator.fetch_all_sources",
            new_callable=AsyncMock,
        ) as mock_fetch,
    ):
        mock_fetch.return_value = FetchResult(items=items, failures=[])

        llm_client = LLMClient(token_budget=5000)

        # Topic filter with no matching topics → all items dropped
        opts = PipelineOptions(topics=["fútbol"])
        clusters = await run_pipeline_async(
            sources=sources,
            window=timedelta(hours=48),
            llm=llm_client,
            config=config,
            options=opts,
        )

    assert clusters == []


@pytest.mark.asyncio
async def test_content_and_topic_filter_combined() -> None:
    """Both filters work together: content drops entertainment, topic keeps only matching."""
    config = _make_config()
    sources = config.sources

    items = [
        # Should be dropped by content filter (entertainment)
        _item(title="Horóscopo de hoy", source="pagina12", lean="left"),
        # Should survive content filter but dropped by topic filter (no match)
        _item(title="Tecnología avanzada", body="Noticias de tecnología.", source="infobae", lean="center"),
        # Should survive both filters (not entertainment + matches topic)
        _item(title="Nueva ley de economía", body="Ley económica aprobada.", source="clarin", lean="right"),
    ]

    with (
        patch(
            "noticias.pipeline.orchestrator.fetch_all_sources",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "noticias.llm.client.litellm.acompletion",
            new_callable=AsyncMock,
        ) as mock_llm,
    ):
        mock_fetch.return_value = FetchResult(items=items, failures=[])
        mock_llm.return_value = MockLLMResponse(
            '{"summary": "Resumen.", "highlights": []}',
        )

        llm_client = LLMClient(token_budget=5000)
        llm_client._keys["groq"] = "fake_key"

        opts = PipelineOptions(topics=["economía"])
        clusters = await run_pipeline_async(
            sources=sources,
            window=timedelta(hours=48),
            llm=llm_client,
            config=config,
            options=opts,
        )

    # Only the economía item survives both filters.
    assert len(clusters) == 1
    titles = {item.title for c in clusters for item in c.items}
    assert "Nueva ley de economía" in titles
    assert "Horóscopo de hoy" not in titles
    assert "Tecnología avanzada" not in titles
