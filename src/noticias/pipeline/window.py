"""Time-window filter for news items.

Parses --since duration strings (e.g. "24h", "7d", "30m") and filters
items by their published_at timestamp. Items outside the window or with
no parseable date are excluded.

All datetime values are timezone-aware (UTC) for consistent comparison.
Items with published_at=None are treated as outside the window and
are excluded.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from noticias.models.item import NewsItem


def parse_since(s: str) -> timedelta:
    """Parse a human-readable duration string into a timedelta.

    Supported formats:
        - "30m" → 30 minutes
        - "24h" → 24 hours
        - "7d"  → 7 days

    Raises:
        ValueError: If the string format is unrecognised or the numeric
            part cannot be parsed.
    """
    if not s or not isinstance(s, str):
        raise ValueError(f"Invalid duration: {s!r}")

    match = re.fullmatch(r"(\d+)([hdm])", s.strip().lower())
    if not match:
        raise ValueError(
                f"Invalid duration format: {s!r}. "
                f"Use e.g. '24h', '7d', '30m'.",
            )

    value = int(match.group(1))
    unit = match.group(2)

    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)

    # Unreachable given the regex, but satisfy the type checker.
    raise ValueError(f"Unknown time unit: {unit}")


def filter_by_window(items: list[NewsItem], since: timedelta) -> list[NewsItem]:
    """Keep items whose published_at falls within the given time window.

    Items with published_at=None are always excluded — they are treated as
    being outside any window.

    Args:
        items: The list of items to filter.
        since: A timedelta defining how far back the window extends.

    Returns:
        A new list containing only items within the window.
    """
    cutoff = datetime.now(tz=timezone.utc) - since

    result: list[NewsItem] = []
    for item in items:
        if item.published_at is None:
            continue
        if item.published_at >= cutoff:
            result.append(item)

    return result


def apply_window(items: list[NewsItem], since: timedelta) -> list[NewsItem]:
    """Public alias for filter_by_window — the name used in the pipeline.

    This function exists so that the pipeline orchestrator calls
    ``apply_window`` rather than ``filter_by_window`` for readability.
    """
    return filter_by_window(items, since)
