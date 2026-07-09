"""Story clustering by title similarity, body token overlap, and domain+slug matching.

Groups news items into story families (clusters) using union-find.

Two items belong to the same cluster when **one or more** of the following
conditions hold:

    1. Fuzzy title ratio > 0.55 (primary signal — uses rapidfuzz).
    2. Body token overlap (Jaccard via ``tokenize()``) > 0.30 (catches stories
       whose headlines differ but article bodies cover the same event).
    3. They share the same domain AND have meaningful slug overlap (ratio > 0.40).

Body token overlap was added to compensate for the removal of the Embedder
(fastembed) path, since no local ML models are available. The overlap is computed
on the first 500 characters of each item's body to keep pairwise comparison fast.

Single items that do not match any other item form clusters of size 1.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Final
from urllib.parse import urlparse

from rapidfuzz import fuzz

from noticias.models.cluster import Cluster
from noticias.models.item import NewsItem
from noticias.pipeline.tokenize import tokenize

# Minimum slug similarity ratio for same-domain matching.
_SLUG_THRESHOLD: Final[float] = 0.4

logger = logging.getLogger(__name__)


def _slug(url: str) -> str:
    """Extract the last 2-3 path segments of a URL as a story slug heuristic.

    News article URLs typically encode the article slug in the last 2-3
    path segments. Outlets covering the same story often have similar slug
    patterns for the same event (e.g. ``/politica/jubilaciones-nuevas-medidas``
    and ``/politica/jubilaciones-medidas-gobierno``).

    This is a **heuristic** — it trades precision for zero model dependencies.
    """
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    if not segments:
        return ""
    n = min(len(segments), 3)
    return "/".join(segments[-n:]).lower()


def cluster(items: list[NewsItem]) -> list[Cluster]:
    """Group related news items into story clusters.

    Uses a union-find (disjoint-set) data structure so that chains of
    similarity propagate transitively: if A matches B and B matches C,
    all three land in the same cluster even if A does not directly match C.

    Clustering signals (checked in order for each pair):

        1. **Title fuzzy ratio** > 0.55 (rapidfuzz).
        2. **Body token overlap** (Jaccard via ``tokenize()``) > 0.30.
        3. **Same domain + slug ratio** > 0.40.

    Args:
        items: De-duplicated, time-windowed news items.

    Returns:
        A list of Cluster objects, sorted by cluster size (largest first).
        Every input item appears in exactly one cluster.
    """
    if not items:
        return []

    n = len(items)

    # --- union-find helpers ---
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    # Pre-compute domains, slugs, and body token sets (avoids recomputation).
    domains = [_domain(item.url) for item in items]
    slugs = [_slug(item.url) for item in items]
    body_tokens = [
        tokenize(item.body[:500]) if item.body else set()
        for item in items
    ]

    # --- pairwise comparison ---
    for i in range(n):
        for j in range(i + 1, n):
            matched = False

            # 1. rapidfuzz title similarity (primary signal).
            title_ratio = fuzz.ratio(items[i].title, items[j].title) / 100.0
            if title_ratio > 0.55:
                union(i, j)
                matched = True

            # 2. Body token overlap (catches stories whose headlines differ
            #    but article bodies cover the same event).
            if not matched and body_tokens[i] and body_tokens[j]:
                inter = len(body_tokens[i] & body_tokens[j])
                uni = len(body_tokens[i] | body_tokens[j])
                if uni > 0 and (inter / uni) > 0.3:
                    union(i, j)
                    matched = True

            # 3. Same domain + slug overlap (only when neither 1 nor 2
            #    matched — preserves existing behavior).
            if not matched and domains[i] and domains[j] and domains[i] == domains[j]:
                slug_i, slug_j = slugs[i], slugs[j]
                if slug_i and slug_j:
                    slug_ratio = fuzz.ratio(slug_i, slug_j) / 100.0
                    if slug_ratio > _SLUG_THRESHOLD:
                        union(i, j)

    # --- group by root ---
    groups: dict[int, list[NewsItem]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(items[i])

    # --- build Cluster objects ---
    clusters: list[Cluster] = [
        Cluster(
            items=group,
            sources=list({item.source for item in group}),
        )
        for group in groups.values()
    ]

    # Sort largest first for consistent output ordering.
    clusters.sort(key=lambda c: len(c.items), reverse=True)
    return clusters


def _domain(url: str) -> str:
    """Extract the lower-case hostname from a URL (used internally)."""
    try:
        host = urlparse(url).hostname or ""
        return host.lower()
    except Exception:  # noqa: BLE001
        return ""
