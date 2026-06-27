"""Test helpers — factory functions with sensible defaults.

These are NOT pytest fixtures; they take arguments and return objects.
Import them explicitly in test files.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from noticias.models.cluster import Cluster, LLMResponse
from noticias.models.item import NewsItem

# Sentinel to distinguish "not provided" from "explicitly None".
_UNSET: Any = object()


def make_item(
    title: str = "Default headline",
    url: str = "https://example.com/article",
    source: str = "pagina12",
    lean: str = "left",
    body: str = "Content of the article with enough words for tokenization testing purposes.",
    published_at: datetime | None = _UNSET,
) -> NewsItem:
    """Build a NewsItem with sensible defaults for quick construction.

    When ``published_at`` is not provided it defaults to a fixed UTC datetime.
    Pass ``published_at=None`` explicitly to create an item with no timestamp.
    """
    if published_at is _UNSET:
        published_at = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)
    return NewsItem(
        title=title,
        url=url,
        source=source,
        lean=lean,
        body=body,
        published_at=published_at,
    )


def make_batch_response(
    clusters: list[tuple[list[str], str, list[str]]],
) -> str:
    """Build a batch LLM response JSON string.

    Args:
        clusters: Each tuple is ``(titles, summary, highlights)`` where
            ``titles`` are the NewsItem titles of the cluster (used to
            compute the event_label), ``summary`` is the expected summary
            text, and ``highlights`` is the expected highlights list.

    Returns:
        A JSON string in batch format ready for ``parse_batch_llm_response``.
    """
    from noticias.pipeline.event_label import event_label

    entries: list[dict[str, Any]] = []
    for titles, summary, highlights in clusters:
        label = event_label(titles)
        entries.append({
            "cluster_id": label,
            "summary": summary,
            "highlights": highlights,
        })
    return json.dumps({"clusters": entries})


def make_cluster(
    items: list[NewsItem] | None = None,
    event_label: str = "",
    sources: list[str] | None = None,
) -> Cluster:
    """Build a Cluster with explicit field overrides."""
    if items is None:
        items = [make_item()]
    if sources is None:
        sources = list({it.source for it in items})
    return Cluster(
        event_label=event_label,
        items=items,
        sources=sources,
    )
