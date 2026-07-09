"""Unit tests for the sync ``run_pipeline`` wrapper (pipeline/orchestrator.py).

Covers the sync convenience wrapper that calls ``asyncio.run(run_pipeline_async(...))``.
Uses ``StubLLMClient`` so no API keys or network calls are needed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from noticias.llm.client import StubLLMClient
from noticias.models.source import Lean, Source, SourceConfig
from noticias.pipeline.fetch import FetchResult
from noticias.pipeline.orchestrator import run_pipeline
from tests.helpers import make_item


def _sample_sources() -> list[Source]:
    return [
        Source(name="pagina12", url="https://p12.com/rss", lean=Lean.LEFT),
        Source(name="infobae", url="https://infobae.com/rss", lean=Lean.CENTER),
    ]


def _sample_config() -> SourceConfig:
    return SourceConfig(
        sources=_sample_sources(),
        fetch_timeout_s=10.0,
        max_concurrent_sources=5,
        rate_limit_s=1,
        token_budget=5000,
    )


def test_run_pipeline_happy_path() -> None:
    """Sync wrapper: runs pipeline with StubLLMClient and returns clusters."""
    sources = _sample_sources()
    config = _sample_config()
    llm = StubLLMClient()

    # Items need published_at within the window filter (24 hours from now).
    now = datetime.now(timezone.utc)
    items = [
        make_item(
            title="Corte Suprema argentina falla libertad expresion",
            source="pagina12", lean="left",
            url="https://example.com/politica/corte/fallo-libertad-expresion",
            published_at=now - timedelta(hours=1),
        ),
        make_item(
            title="Suprema Corte falla libertad de expresion en Argentina",
            source="infobae", lean="center",
            url="https://example.com/politica/corte/fallo-expresion-libertad",
            published_at=now - timedelta(hours=2),
        ),
    ]

    with patch(
        "noticias.pipeline.orchestrator.fetch_all_sources",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = FetchResult(items=items, failures=[])

        clusters = run_pipeline(
            sources=sources,
            window=timedelta(hours=24),
            llm=llm,
            config=config,
        )

    # Clusters should be formed from the 2 related items.
    assert len(clusters) > 0, "Expected at least one cluster from 2 related items"

    # Each cluster should have a stub summary populated.
    for cluster in clusters:
        assert len(cluster.summary) > 0, (
            f"Cluster '{cluster.event_label}' has empty summary"
        )
        # StubLLMClient returns stub summaries.
        assert "no disponible" in cluster.summary.lower()


def test_run_pipeline_empty_fetch() -> None:
    """Sync wrapper: empty fetch returns empty list."""
    sources = _sample_sources()
    config = _sample_config()
    llm = StubLLMClient()

    with patch(
        "noticias.pipeline.orchestrator.fetch_all_sources",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = FetchResult(items=[], failures=[])

        clusters = run_pipeline(
            sources=sources,
            window=timedelta(hours=24),
            llm=llm,
            config=config,
        )

    assert clusters == [], "Expected empty list when no items are fetched"
