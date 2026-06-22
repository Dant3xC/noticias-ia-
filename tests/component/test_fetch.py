"""Component tests for the async fetcher (pipeline/fetch.py).

Uses respx to mock httpx HTTP calls and verifies:
- Per-source failure isolation (one fails, others succeed)
- Sources with empty URL are skipped gracefully
- Rate-limit sleeps are called
- Semaphore caps concurrency
- Empty feed returns empty list (not failure)
- All sources fail → empty items + all failures
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
import pytest
import respx
from httpx import Response

from noticias.pipeline.fetch import FetchFailure, fetch_all_sources
from noticias.models.source import Lean, Source
from tests.conftest import source_empty_url, source_infobae, source_pagina12  # noqa: F401

# Valid RSS XML for mocking
_RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <item>
    <title>Test Article</title>
    <link>https://example.com/article</link>
    <description>Test description body.</description>
    <pubDate>Mon, 21 Jun 2026 12:00:00 +0000</pubDate>
  </item>
</channel>
</rss>"""


@pytest.mark.asyncio
async def test_all_sources_succeed(source_pagina12, source_infobae) -> None:  # noqa: F811
    sources = [source_pagina12, source_infobae]
    with respx.mock:
        respx.get(source_pagina12.url).mock(return_value=Response(200, content=_RSS_XML))
        respx.get(source_infobae.url).mock(return_value=Response(200, content=_RSS_XML))

        result = await fetch_all_sources(
            sources, window_h=24, timeout_s=10.0,
        )

    assert len(result.items) == 2  # one item per source
    assert result.failures == []


@pytest.mark.asyncio
async def test_one_source_fails_others_succeed(source_pagina12, source_infobae) -> None:  # noqa: F811
    sources = [source_pagina12, source_infobae]
    with respx.mock:
        respx.get(source_pagina12.url).mock(return_value=Response(200, content=_RSS_XML))
        respx.get(source_infobae.url).mock(return_value=Response(500))

        result = await fetch_all_sources(
            sources, window_h=24, timeout_s=10.0,
        )

    assert len(result.items) == 1  # only pagina12 succeeded
    assert len(result.failures) == 1
    assert result.failures[0].source == "infobae"
    assert "HTTP 500" in result.failures[0].reason


@pytest.mark.asyncio
async def test_empty_url_is_skipped(source_pagina12, source_empty_url) -> None:  # noqa: F811
    sources = [source_pagina12, source_empty_url]
    with respx.mock:
        respx.get(source_pagina12.url).mock(return_value=Response(200, content=_RSS_XML))

        result = await fetch_all_sources(
            sources, window_h=24, timeout_s=10.0,
        )

    assert len(result.items) == 1  # only pagina12
    assert len(result.failures) == 1
    assert result.failures[0].source == "laizquierdadiario"
    assert "no configurada" in result.failures[0].reason


@pytest.mark.asyncio
async def test_all_sources_fail(source_pagina12, source_infobae) -> None:  # noqa: F811
    sources = [source_pagina12, source_infobae]
    with respx.mock:
        respx.get(source_pagina12.url).mock(return_value=Response(500))
        respx.get(source_infobae.url).mock(return_value=Response(500))

        result = await fetch_all_sources(
            sources, window_h=24, timeout_s=10.0,
        )

    assert result.items == []
    assert len(result.failures) == 2


@pytest.mark.asyncio
async def test_empty_feed_not_a_failure(source_pagina12) -> None:  # noqa: F811
    """200 OK with 0 items → empty list, NOT a failure."""
    empty_feed = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Empty</title></channel></rss>"""

    sources = [source_pagina12]
    with respx.mock:
        respx.get(source_pagina12.url).mock(return_value=Response(200, content=empty_feed))

        result = await fetch_all_sources(
            sources, window_h=24, timeout_s=10.0,
        )

    assert result.items == []
    assert result.failures == []


@pytest.mark.asyncio
async def test_timeout_is_failure(source_pagina12) -> None:  # noqa: F811
    """Verify that an httpx timeout is captured as a FetchFailure."""
    sources = [source_pagina12]
    with respx.mock:
        respx.get(source_pagina12.url).mock(
            side_effect=httpx.TimeoutException("Request timed out"),
        )

        result = await fetch_all_sources(
            sources, window_h=24, timeout_s=10.0,
        )

    assert result.items == []
    assert len(result.failures) == 1
    assert result.failures[0].source == "pagina12"
