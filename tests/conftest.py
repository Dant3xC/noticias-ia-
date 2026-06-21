"""Shared test fixtures for the noticias test suite.

This file contains only pytest fixtures. Builder functions (make_item,
make_cluster) live in tests/helpers.py for explicit import.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noticias.models.item import NewsItem
from noticias.models.source import Lean, Source, SourceConfig


# ── Sources ────────────────────────────────────────────────────────────────


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
def source_pagina12() -> Source:
    """A Source fixture for pagina12 (left)."""
    return Source(
        name="pagina12",
        url="https://www.pagina12.com.ar/rss/portada",
        lean=Lean.LEFT,
    )


@pytest.fixture
def source_infobae() -> Source:
    """A Source fixture for infobae (center)."""
    return Source(
        name="infobae",
        url="https://www.infobae.com/rss/",
        lean=Lean.CENTER,
    )


@pytest.fixture
def source_empty_url() -> Source:
    """A Source with an empty URL (placeholder)."""
    return Source(
        name="laizquierdadiario",
        url="",
        lean=Lean.LEFT,
    )


# ── NewsItems ──────────────────────────────────────────────────────────────


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


# ── RSS XML fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def rss20_feed_bytes() -> bytes:
    """A minimal RSS 2.0 feed with content:encoded."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
  <title>Test Channel</title>
  <link>https://example.com</link>
  <item>
    <title>  Headline One  </title>
    <link>https://example.com/article-1</link>
    <description>Summary text for article one.</description>
    <content:encoded><![CDATA[<p>Full body of article one.</p>]]></content:encoded>
    <pubDate>Mon, 21 Jun 2026 12:00:00 +0000</pubDate>
  </item>
  <item>
    <title>Headline Two</title>
    <link>https://example.com/article-2</link>
    <description>Summary for article two.</description>
    <pubDate>Tue, 22 Jun 2026 08:30:00 +0000</pubDate>
  </item>
</channel>
</rss>"""


@pytest.fixture
def atom_feed_bytes() -> bytes:
    """A minimal Atom 1.0 feed."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Atom Channel</title>
  <link href="https://example.com/atom"/>
  <entry>
    <title>Atom Entry Title</title>
    <link href="https://example.com/atom-entry-1"/>
    <summary>Atom summary for the entry.</summary>
    <published>2026-06-21T12:00:00Z</published>
  </entry>
</feed>"""


@pytest.fixture
def rss_no_body_feed_bytes() -> bytes:
    """RSS feed where items have only titles (no content:encoded or summary)."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Minimal Channel</title>
  <link>https://example.com</link>
  <item>
    <title>Title-only article</title>
    <link>https://example.com/title-only</link>
  </item>
</channel>
</rss>"""
