"""Unit tests for the RSS/Atom adapter (sources/adapters.py).

Covers:
- RSS 2.0 item normalisation (title, url, body, date)
- Atom item normalisation
- Body fallback chain (content:encoded > summary > title)
- Date parsing (valid RFC 822, ISO 8601, unparseable)
- Empty feed handling
- get_adapter returns default adapter
"""

from __future__ import annotations

from datetime import timezone

from noticias.sources.adapters import RSSAdapter, get_adapter, normalize


class TestRSSAdapterParse:
    def test_rss20_parse_returns_entries(self, rss20_feed_bytes: bytes) -> None:
        adapter = RSSAdapter()
        entries = adapter.parse(rss20_feed_bytes)
        assert len(entries) == 2

    def test_atom_parse_returns_entries(self, atom_feed_bytes: bytes) -> None:
        adapter = RSSAdapter()
        entries = adapter.parse(atom_feed_bytes)
        assert len(entries) == 1

    def test_empty_feed(self) -> None:
        adapter = RSSAdapter()
        entries = adapter.parse(b"<rss version='2.0'><channel><title>Empty</title></channel></rss>")
        assert entries == []

    def test_malformed_xml_does_not_raise(self) -> None:
        adapter = RSSAdapter()
        entries = adapter.parse(b"not xml at all")
        # feedparser returns [] or [single entry w/ error]; should not raise.
        assert isinstance(entries, list)


class TestNormalizeRSS20:
    def test_title_stripped(self, rss20_feed_bytes: bytes, source_pagina12) -> None:
        adapter = RSSAdapter()
        entries = adapter.parse(rss20_feed_bytes)
        item = normalize(entries[0], source_pagina12)
        assert item.title == "Headline One"  # whitespace stripped

    def test_url_from_link(self, rss20_feed_bytes: bytes, source_pagina12) -> None:
        adapter = RSSAdapter()
        entries = adapter.parse(rss20_feed_bytes)
        item = normalize(entries[0], source_pagina12)
        assert item.url == "https://example.com/article-1"

    def test_source_and_lean(self, rss20_feed_bytes: bytes, source_pagina12) -> None:
        adapter = RSSAdapter()
        entries = adapter.parse(rss20_feed_bytes)
        item = normalize(entries[0], source_pagina12)
        assert item.source == "pagina12"
        assert item.lean == "left"

    def test_body_from_content_encoded(self, rss20_feed_bytes: bytes, source_pagina12) -> None:
        adapter = RSSAdapter()
        entries = adapter.parse(rss20_feed_bytes)
        item = normalize(entries[0], source_pagina12)
        assert "Full body of article one." in item.body

    def test_body_fallback_summary(self, rss20_feed_bytes: bytes, source_infobae) -> None:
        """Item 2 has no content:encoded, body should come from summary."""
        adapter = RSSAdapter()
        entries = adapter.parse(rss20_feed_bytes)
        item = normalize(entries[1], source_infobae)
        assert "Summary for article two." in item.body

    def test_published_at_parsed(self, rss20_feed_bytes: bytes, source_pagina12) -> None:
        adapter = RSSAdapter()
        entries = adapter.parse(rss20_feed_bytes)
        item = normalize(entries[0], source_pagina12)
        assert item.published_at is not None
        assert item.published_at.hour == 12  # 12:00 UTC
        assert item.published_at.tzinfo is not None


class TestNormalizeAtom:
    def test_title_extracted(self, atom_feed_bytes: bytes, source_infobae) -> None:
        adapter = RSSAdapter()
        entries = adapter.parse(atom_feed_bytes)
        item = normalize(entries[0], source_infobae)
        assert item.title == "Atom Entry Title"

    def test_url_from_link_href(self, atom_feed_bytes: bytes, source_infobae) -> None:
        adapter = RSSAdapter()
        entries = adapter.parse(atom_feed_bytes)
        item = normalize(entries[0], source_infobae)
        assert item.url == "https://example.com/atom-entry-1"

    def test_body_from_summary(self, atom_feed_bytes: bytes, source_infobae) -> None:
        adapter = RSSAdapter()
        entries = adapter.parse(atom_feed_bytes)
        item = normalize(entries[0], source_infobae)
        assert "Atom summary for the entry." in item.body

    def test_published_at_from_iso(self, atom_feed_bytes: bytes, source_infobae) -> None:
        adapter = RSSAdapter()
        entries = adapter.parse(atom_feed_bytes)
        item = normalize(entries[0], source_infobae)
        assert item.published_at is not None
        assert item.published_at.tzinfo is not None


class TestBodyFallback:
    def test_no_content_no_summary_uses_title(self, rss_no_body_feed_bytes: bytes, source_pagina12) -> None:
        """When neither content:encoded nor summary exists, body = title."""
        adapter = RSSAdapter()
        entries = adapter.parse(rss_no_body_feed_bytes)
        item = normalize(entries[0], source_pagina12)
        assert item.body == "Title-only article"


class TestGetAdapter:
    def test_returns_default_adapter(self, source_pagina12) -> None:
        adapter = get_adapter(source_pagina12)
        assert isinstance(adapter, RSSAdapter)
