"""Topic-based allowlist filter — keeps only items matching user topics.

Runs after the content filter, before the time-window filter. Items whose
title or body contain at least one configured topic (case-insensitive
substring match) are kept; all others are dropped.

When no topics are configured (empty list), all items pass through
(passthrough mode). This preserves backward compatibility with
configurations that don't use topics.
"""

from __future__ import annotations

import logging

from noticias.models.item import NewsItem

logger = logging.getLogger(__name__)

# Maximum number of topics to apply (configurable via PipelineOptions).
_MAX_TOPICS: int = 10


def filter_topics(
    items: list[NewsItem],
    topics: list[str],
) -> list[NewsItem]:
    """Keep only items whose title or body contains at least one topic.

    Matching is case-insensitive substring search. Multi-word topics match
    as a single phrase (e.g. ``"economía argentina"`` requires the words
    to appear in that order).

    Args:
        items: The list of news items to filter.
        topics: The list of topics to allowlist. Empty list passes all
            items through. Empty/whitespace-only strings are ignored.

    Returns:
        A new list containing only items that match at least one topic.
    """
    if not topics:
        return list(items)

    # Strip whitespace and ignore empty entries.
    topics_clean = [t.lower().strip() for t in topics if t and t.strip()]
    if not topics_clean:
        return list(items)

    # Cap at max topics.
    if len(topics_clean) > _MAX_TOPICS:
        logger.warning(
            "Topic count (%d) exceeds maximum (%d). Using first %d topics.",
            len(topics_clean),
            _MAX_TOPICS,
            _MAX_TOPICS,
        )
        topics_clean = topics_clean[:_MAX_TOPICS]

    result: list[NewsItem] = []
    dropped = 0

    for item in items:
        text = (item.title + " " + item.body).lower()
        if any(topic in text for topic in topics_clean):
            result.append(item)
        else:
            dropped += 1

    if dropped:
        logger.info("Topic filter dropped %d item(s)", dropped)

    return result
