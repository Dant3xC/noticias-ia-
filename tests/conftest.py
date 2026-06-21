"""Shared test fixtures for the noticias test suite."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noticias.models.item import NewsItem
from noticias.models.source import Lean, Source, SourceConfig


@pytest.fixture
def sample_source_config() -> SourceConfig:
    """A SourceConfig with 2 pre-configured sources."""
    return SourceConfig(
        sources=[
            Source(
                name="pagina12",
                url="https://www.pagina12.com.ar/rss/portada",
                lean=Lean.LEFT,
            ),
            Source(
                name="infobae",
                url="https://www.infobae.com/rss/",
                lean=Lean.CENTER,
            ),
        ],
    )


@pytest.fixture
def sample_news_item() -> NewsItem:
    """A minimal NewsItem for use in model encoding/decoding tests."""
    return NewsItem(
        title="Test headline",
        url="https://example.com/test",
        source="pagina12",
        lean="left",
        published_at=datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc),
        body="This is the article body for testing.",
    )
