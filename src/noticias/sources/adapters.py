"""RSS/Atom feed adapter — normalizes feedparser raw entries to NewsItem.

Handles both RSS 2.0 and Atom feeds via feedparser's unified output shape.
The adapter layer is the only code that touches feedparser directly; all
downstream pipeline stages consume NewsItem objects.

Body fallback chain (body SHALL NOT be empty):
    1. entry.content[0].value  (content:encoded in RSS, <content> in Atom)
    2. entry.summary           (RSS <description>, Atom <summary>)
    3. entry.title             (last resort)

Date parsing:
    - Tries published_parsed first (RSS pubDate, Atom published)
    - Falls back to updated_parsed (RSS lastBuildDate, Atom updated)
    - Uses calendar.timegm for UTC-safe conversion
    - Returns None on any parse failure (item filtered later by window)
"""

from __future__ import annotations

import calendar
import time
from datetime import datetime, timezone

import feedparser

from noticias.models.item import NewsItem
from noticias.models.source import Source


class RSSAdapter:
    """Default adapter for RSS 2.0 and Atom feeds.

    Parses feed bytes via feedparser and returns raw entry dicts.
    feedparser transparently handles both RSS 2.0 (with content:encoded)
    and Atom (with <content> and <summary>) in its unified output shape.
    """

    def parse(self, feed_bytes: bytes) -> list[dict]:
        """Parse feed bytes into a list of raw feedparser entry dicts.

        Returns an empty list if the feed has no entries, is empty XML,
        or cannot be parsed as a valid feed.
        """
        feed = feedparser.parse(feed_bytes)
        return list(feed.entries)


def normalize(raw_entry: dict, source: Source) -> NewsItem:
    """Normalize a raw feedparser entry to a NewsItem.

    Args:
        raw_entry: A single entry dict from feedparser (dotted access also
            works on the feedparser object, but we use dict access for safety).
        source: The Source this entry was fetched from.

    Returns:
        A fully populated NewsItem. Body is guaranteed non-empty via the
        fallback chain (content:encoded → summary → title).
    """
    title = (raw_entry.get("title") or "").strip()
    url = raw_entry.get("link") or ""
    body = _extract_body(raw_entry)
    published_at = _parse_date(raw_entry)

    return NewsItem(
        title=title,
        url=url,
        source=source.name,
        lean=source.lean.value if source.lean else "",
        body=body,
        published_at=published_at,
    )


def _extract_body(entry: dict) -> str:
    """Extract body text from a feedparser entry with fallback chain.

    Priority:
        1. entry.content[0].value — content:encoded (RSS 2.0) / <content> (Atom)
        2. entry.summary — <description> (RSS) / <summary> (Atom)
        3. entry.title — last resort, guarantees non-empty body
    """
    # content:encoded is stored in entry.content list by feedparser
    content = entry.get("content")
    if content and isinstance(content, list) and len(content) > 0:
        value = content[0].get("value", "")
        if value and value.strip():
            return value.strip()

    # Fallback to summary (RSS description / Atom summary)
    summary = entry.get("summary", "")
    if summary and summary.strip():
        return summary.strip()

    # Last resort: title (never empty, body SHALL NOT be empty)
    return (entry.get("title") or "").strip()


def _parse_date(entry: dict) -> datetime | None:
    """Parse a datetime from a feedparser entry.

    Tries published_parsed (RSS pubDate, Atom published) first,
    then updated_parsed (Atom updated). Converts from time.struct_time
    to a timezone-aware UTC datetime.

    Returns None on parse failure (item will be excluded by time window).
    """
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None

    try:
        timestamp = calendar.timegm(parsed)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError, TypeError):
        return None


def get_adapter(source: Source) -> RSSAdapter:
    """Return a default RSSAdapter for the given source.

    Custom adapter registration is deferred to a later PR. All sources
    currently use the default adapter which handles both RSS 2.0 and Atom.
    """
    return RSSAdapter()
