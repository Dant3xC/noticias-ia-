"""Story clustering by title similarity and canonical URL matching.

Groups news items into story families (clusters) using union-find.

Two items belong to the same cluster when **one or more** of the following
conditions hold:

    1. (Primary) Embedding-based cosine similarity ≥ 0.85 (when an
       ``Embedder`` instance is provided and produces results).
    2. (Fallback) Fuzzy title ratio > 0.75 (used when no embedder is
       available, or for items with empty titles).
    3. They share the same canonical domain AND have meaningful slug
       overlap.

The second heuristic catches cases where different outlets cover the same
event but use different headline phrasings (e.g. ``"Corte Suprema falla..."``
vs ``"La Corte decidió..."`` but both link to the same court ruling URL).

Single items that do not match any other item form clusters of size 1.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Final
from urllib.parse import urlparse

import numpy as np
from rapidfuzz import fuzz

from noticias.models.cluster import Cluster
from noticias.models.item import NewsItem
from noticias.pipeline.dedup import canonical_url
from noticias.pipeline.embed import COSINE_THRESHOLD, Embedder

# Minimum slug similarity ratio for same-domain matching.
_SLUG_THRESHOLD: Final[float] = 0.5

logger = logging.getLogger(__name__)


def _slug(url: str) -> str:
    """Extract the last 2-3 path segments of a URL as a story slug heuristic.

    News article URLs typically encode the article slug in the last 2-3
    path segments. Outlets covering the same story often have similar slug
    patterns for the same event (e.g. ``/politica/jubilaciones-nuevas-medidas``
    and ``/politica/jubilaciones-medidas-gobierno``).

    This is a **heuristic** — it trades precision for zero dependencies.
    Embedding-based semantic clustering is a documented future enhancement.
    """
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    if not segments:
        return ""
    n = min(len(segments), 3)
    return "/".join(segments[-n:]).lower()


def cluster(
    items: list[NewsItem],
    embedder: Embedder | None = None,
) -> list[Cluster]:
    """Group related news items into story clusters.

    Uses a union-find (disjoint-set) data structure so that chains of
    similarity propagate transitively: if A matches B and B matches C,
    all three land in the same cluster even if A does not directly match C.

    When *embedder* is provided and produces embeddings, cosine similarity
    (≥ ``COSINE_THRESHOLD`` = 0.85) is used as the **primary** clustering
    signal. Items with empty titles, or when the embedder call fails, fall
    back to the existing rapidfuzz title-ratio heuristic (ratio > 0.75).

    When *embedder* is ``None`` (the default), the function behaves exactly
    as before — rapidfuzz-only with domain+slug fallback.

    Args:
        items: De-duplicated, time-windowed news items.
        embedder: Optional ``Embedder`` instance for semantic clustering.
            When ``None``, rapidfuzz title similarity is used exclusively.

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

    # Pre-compute canonical URLs, domains, and slugs (avoids recomputation).
    can_urls = [canonical_url(item.url) for item in items]
    domains = [_domain(item.url) for item in items]
    slugs = [_slug(item.url) for item in items]

    # Compute embeddings if an embedder is provided.
    embeddings: np.ndarray | None = None
    if embedder is not None:
        titles = [item.title for item in items]
        embeddings = embedder.embed(titles)
        if embeddings is None:
            logger.warning(
                "Embedder returned None for %d items; "
                "falling back to rapidfuzz for this run.",
                n,
            )

    # --- pairwise comparison ---
    for i in range(n):
        for j in range(i + 1, n):
            matched = False

            # 1. Embedding-based similarity (primary signal).
            if embeddings is not None:
                title_i = items[i].title.strip()
                title_j = items[j].title.strip()
                if title_i and title_j:
                    if Embedder.is_similar(embeddings[i], embeddings[j]):
                        union(i, j)
                        matched = True

            # 2. rapidfuzz title similarity (fallback — used when no
            #    embeddings are available, or for empty-title items).
            if not matched:
                title_ratio = fuzz.ratio(items[i].title, items[j].title) / 100.0
                if title_ratio > 0.75:
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
