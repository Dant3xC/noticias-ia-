"""Near-duplicate detection and removal for news items.

Uses rapidfuzz for fuzzy title matching and canonical URL comparison.
Duplicates are detected both within a single source and across sources.

Thresholds (design Q1):
    - Title fuzz ratio > 0.85 → duplicate
    - Canonical URL fuzz ratio > 0.9 → duplicate

When duplicates are detected the item with the earliest published_at is kept.
If both items lack a date the first one in iteration order survives.
"""

from __future__ import annotations

import re
from typing import Final
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from rapidfuzz import fuzz

from noticias.models.item import NewsItem

# Tracking / analytics query parameters stripped during URL canonicalisation.
_TRACKING_PARAMS: Final[set[str]] = {
    "utm_source", "utm_medium", "utm_campaign",
    "utm_term", "utm_content", "gclid", "fbclid",
    "gclsrc", "dclid", "msclkid", "ref", "source",
}


def canonical_url(url: str) -> str:
    """Canonicalise a URL for duplicate comparison.

    Transformations applied (in order):
        1. Lowercase the hostname.
        2. Strip ``www.`` prefix from host.
        3. Strip trailing ``/`` from path.
        4. Remove common tracking / analytics query parameters.
        5. Drop the fragment (never meaningful for canonical form).

    Args:
        url: The raw URL string.

    Returns:
        A canonicalised URL string (or ``""`` for empty input).
    """
    if not url:
        return ""

    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return url

    # Lowercase + strip www.
    host = (parsed.hostname or "").lower()
    host = re.sub(r"^www\.", "", host)

    netloc = host
    if parsed.port is not None:
        netloc = f"{host}:{parsed.port}"

    # Strip trailing slash from path (keep at least "/").
    path = parsed.path.rstrip("/") or "/"

    # Remove tracking params from query string.
    query = _strip_tracking_params(parsed.query)

    # Rebuild without fragment.
    return urlunparse((parsed.scheme, netloc, path, parsed.params, query, ""))


def _strip_tracking_params(query: str) -> str:
    """Remove known tracking/analytics parameters from a query string."""
    if not query:
        return ""
    try:
        params = parse_qs(query, keep_blank_values=True)
    except Exception:  # noqa: BLE001
        return query

    cleaned = {
        k: v for k, v in params.items()
        if k.lower() not in _TRACKING_PARAMS
    }
    if not cleaned:
        return ""
    return urlencode(cleaned, doseq=True)


def dedup(items: list[NewsItem]) -> list[NewsItem]:
    """Remove near-duplicate items, keeping the earliest published_at.

    Two items are considered duplicates when the fuzzy title ratio exceeds
    0.85 **or** the canonical URL fuzzy ratio exceeds 0.9.

    The comparison is O(n²) which is acceptable for the expected corpus
    size (n < 100 items per run).

    Args:
        items: The list of items to de-duplicate.

    Returns:
        A new list with duplicates removed. Order is preserved, and the
        earliest item (by published_at) from each duplicate group survives.
    """
    if not items:
        return []

    # Pre-compute canonical URLs so each URL is computed only once.
    urls = [canonical_url(item.url) for item in items]
    n = len(items)
    kept = [True] * n

    for i in range(n):
        if not kept[i]:
            continue
        for j in range(i + 1, n):
            if not kept[j]:
                continue

            title_ratio = fuzz.ratio(items[i].title, items[j].title) / 100.0

            url_ratio = 0.0
            if urls[i] and urls[j]:
                url_ratio = fuzz.ratio(urls[i], urls[j]) / 100.0

            if title_ratio > 0.85 or url_ratio > 0.90:
                # Keep the item with earliest published_at.
                pub_i = items[i].published_at
                pub_j = items[j].published_at

                if pub_i is None and pub_j is None:
                    # Both None → keep first in iteration order.
                    kept[j] = False
                elif pub_i is None:
                    # j has a date → keep j.
                    kept[i] = False
                    break
                elif pub_j is None:
                    # i has a date → keep i.
                    kept[j] = False
                elif pub_j < pub_i:
                    # j is earlier → keep j.
                    kept[i] = False
                    break
                else:
                    # i is earlier or equal → keep i.
                    kept[j] = False

    return [items[i] for i in range(n) if kept[i]]
