"""Family-format payload builder for story clusters.

Builds the compact per-cluster ``FamilyFormatPayload`` that is the **only**
input sent to the LLM.  This is the cost-control boundary of the system:
raw article bodies never reach the LLM.

The payload contains:
    - ``event_label`` — derived from cluster titles (via ``event_label.py``).
    - ``sources`` — distinct sources with their ideological lean.
    - ``per_source`` — headline + body excerpt (500 chars) + published date
      per source, taking the first item per distinct source.
    - ``common_facts`` — tokens present in >70 % of source bodies.
    - ``divergences`` — tokens present in exactly **one** source body.

Both ``common_facts`` and ``divergences`` are capped at 30 tokens each.
The ``divergence_ratio`` is a standalone function (design-review req #3).
"""

from __future__ import annotations

from collections import Counter

import msgspec

from noticias.models.cluster import (
    Cluster,
    FamilyFormatPayload,
    FamilyFormatSource,
    PerSourceEntry,
)
from noticias.pipeline.tokenize import tokenize


def build_family_format(cluster: Cluster) -> FamilyFormatPayload:
    """Build a ``FamilyFormatPayload`` from a cluster.

    This function mutates several fields of the cluster **in place**:
    ``event_label``, ``common_facts``, ``divergences``, and
    ``divergence_ratio``. The returned payload can be passed to
    ``truncate_payload`` for size enforcement before LLM dispatch.

    Args:
        cluster: A story cluster containing one or more NewsItems.

    Returns:
        A fully populated ``FamilyFormatPayload``.
    """
    items = cluster.items
    if not items:
        _reset_cluster_facts(cluster)
        return FamilyFormatPayload(
            event_label="",
            sources=[],
            per_source=[],
            common_facts=[],
            divergences=[],
        )

    # --- event label ---
    from noticias.pipeline.event_label import event_label as _event_label

    titles = [item.title for item in items]
    label = _event_label(titles)
    cluster.event_label = label

    # --- distinct sources with leans ---
    seen_sources: dict[str, str] = {}
    for item in items:
        if item.source not in seen_sources:
            seen_sources[item.source] = item.lean

    sources = [
        FamilyFormatSource(name=name, lean=lean)
        for name, lean in seen_sources.items()
    ]

    # --- per-source entries (first item per source) ---
    per_source_items: dict[str, NewsItem] = {}
    for item in items:
        if item.source not in per_source_items:
            per_source_items[item.source] = item

    per_source: list[PerSourceEntry] = []
    for source_name in seen_sources:
        item = per_source_items[source_name]
        published_at_str = (
            item.published_at.isoformat() if item.published_at is not None else ""
        )
        per_source.append(
            PerSourceEntry(
                source=source_name,
                headline=item.title,
                body_excerpt=item.body[:500],
                published_at=published_at_str,
            ),
        )

    # --- common facts & divergences ---
    bodies: list[str] = [
        per_source_items[sn].body[:500] for sn in seen_sources
    ]
    common, divs = _compute_facts_divergences(bodies)
    cluster.common_facts = common
    cluster.divergences = divs

    divergence_ratio(cluster)

    return FamilyFormatPayload(
        event_label=label,
        sources=sources,
        per_source=per_source,
        common_facts=common,
        divergences=divs,
    )


def _reset_cluster_facts(cluster: Cluster) -> None:
    """Zero out all fact/divergence fields on an empty cluster."""
    cluster.event_label = ""
    cluster.common_facts = []
    cluster.divergences = []
    cluster.divergence_ratio = 0.0


def _compute_facts_divergences(
    bodies: list[str],
) -> tuple[list[str], list[str]]:
    """Tokenise bodies and separate common facts from divergences.

    A token is a **common fact** if it appears in more than 70 % of the
    source bodies.  A token is a **divergence** if it appears in exactly
    one body.

    Both lists are sorted alphabetically for deterministic output and
    capped at 30 entries each.
    """
    if not bodies:
        return [], []

    token_sets = [tokenize(b) for b in bodies if b.strip()]
    if len(token_sets) < 2:
        # Single source — no divergences possible; all tokens are common.
        all_tokens = sorted(t for ts in token_sets for t in ts)
        return all_tokens[:30], []

    n = len(token_sets)
    counter: Counter[str] = Counter()
    for ts in token_sets:
        counter.update(ts)

    threshold = 0.7
    common = sorted(t for t, c in counter.items() if c / n > threshold)
    divs = sorted(t for t, c in counter.items() if c == 1)

    return common[:30], divs[:30]


def divergence_ratio(cluster: Cluster) -> float:
    """Compute the divergence ratio for a cluster.

    Formula
    -------
    .. code::

        |divergence tokens| / |union of all body tokens|

    where *divergence tokens* are tokens that appear in exactly *one*
    source body and *union* is the set of all distinct tokens across all
    source bodies.

    A ratio of 0.0 means all sources fully agree on vocabulary; 1.0 means
    no two sources share any token (complete divergence).  Empty clusters
    return 0.0.

    This function is intentionally a **standalone function with a
    docstring** (see design-review recommendation #3) so that it can be
    unit-tested and reasoned about independently of the rest of the
    family-format builder.

    Args:
        cluster: A cluster (its ``items`` attribute is inspected).

    Returns:
        The divergence ratio as a float in [0.0, 1.0].
    """
    items = cluster.items
    if not items:
        cluster.divergence_ratio = 0.0
        return 0.0

    # One body per distinct source.
    seen: dict[str, str] = {}
    for item in items:
        if item.source not in seen:
            seen[item.source] = item.body

    bodies = list(seen.values())
    token_sets = [tokenize(b) for b in bodies if b.strip()]

    # Single source → no divergence possible.
    if len(token_sets) < 2:
        cluster.divergence_ratio = 0.0
        return 0.0

    if not token_sets or all(not ts for ts in token_sets):
        cluster.divergence_ratio = 0.0
        return 0.0

    # Union of all tokens.
    union: set[str] = set()
    for ts in token_sets:
        union.update(ts)

    if not union:
        cluster.divergence_ratio = 0.0
        return 0.0

    # Count occurrences per token.
    counter: Counter[str] = Counter()
    for ts in token_sets:
        counter.update(ts)

    divergence_count = sum(1 for c in counter.values() if c == 1)
    ratio = divergence_count / len(union)
    cluster.divergence_ratio = ratio
    return ratio


def truncate_payload(
    payload: FamilyFormatPayload,
    max_chars: int = 6000,
) -> FamilyFormatPayload:
    """Truncate a family-format payload so its JSON encoding fits ``max_chars``.

    If the payload is already within budget it is returned unchanged.
    Otherwise ``per_source[*].body_excerpt`` is progressively shortened
    (binary-search fashion: 250 → 125 → 62 → … chars) until the size
    constraint is satisfied or the excerpts are empty.

    6000 chars ≈ 1500 tokens at char/4 with 25 % headroom (see design Q3).
    The hard ceiling is 2000 tokens / 8000 chars.

    Args:
        payload: The payload to potentially truncate.
        max_chars: Maximum byte size of the JSON-encoded payload.

    Returns:
        A (possibly truncated) ``FamilyFormatPayload`` whose JSON encoding
        fits within ``max_chars``.
    """
    encoded = msgspec.json.encode(payload)
    if len(encoded) <= max_chars:
        return payload

    entries = list(payload.per_source)

    # Progressive truncation — halve each body until under cap.
    step = 250
    while step >= 1:
        entries = [
            PerSourceEntry(
                source=e.source,
                headline=e.headline,
                body_excerpt=e.body_excerpt[:step],
                published_at=e.published_at,
            )
            if len(e.body_excerpt) > step
            else e
            for e in entries
        ]
        test_payload = FamilyFormatPayload(
            event_label=payload.event_label,
            sources=payload.sources,
            per_source=entries,
            common_facts=payload.common_facts,
            divergences=payload.divergences,
        )
        if len(msgspec.json.encode(test_payload)) <= max_chars:
            return test_payload
        step //= 2

    # Last resort: empty all body excerpts.
    entries = [
        PerSourceEntry(
            source=e.source,
            headline=e.headline,
            body_excerpt="",
            published_at=e.published_at,
        )
        for e in entries
    ]
    return FamilyFormatPayload(
        event_label=payload.event_label,
        sources=payload.sources,
        per_source=entries,
        common_facts=payload.common_facts,
        divergences=payload.divergences,
    )
