"""Keyword-based content filter — drops entertainment/gossip items.

Runs after fetch, before the topic filter. Removes items whose title or
body contains any blocked keyword (case-insensitive substring match).

The default keyword list targets Argentine entertainment content
(horóscopo, Gran Hermano, farándula, etc.). Users can override via
``SourceConfig.blocked_keywords`` or opt out entirely via
``PipelineOptions.no_filter``.
"""

from __future__ import annotations

import logging
import unicodedata

from noticias.models.item import NewsItem

logger = logging.getLogger(__name__)

_DEFAULT_BLOCKED: list[str] = [
    "horóscopo",
    "astrología",
    "Gran Hermano",
    "Billboard",
    "reality",
    "farándula",
    "chismes",
    "escandalos",
    "tarot",
    "videncia",
    "carta astral",
    "signo zodiacal",
    "horoscopo",
    "astrologia",
]


def _normalize(text: str) -> str:
    """NFKD-normalize → strip combining marks → lowercase.

    This folds accented characters to their ASCII base form so that
    e.g. ``"horóscopo"`` and ``"horoscopo"`` compare equal.
    """
    lowered = text.lower()
    # Fast path: pure ASCII — no accent decomposition needed.
    if lowered.isascii():
        return lowered
    nfkd = unicodedata.normalize("NFKD", lowered)
    return nfkd.encode("ascii", "ignore").decode("ascii")


def filter_content(
    items: list[NewsItem],
    blocked: list[str] | None = None,
) -> list[NewsItem]:
    """Drop items whose title or body contains any blocked keyword.

    Args:
        items: The list of news items to filter.
        blocked: Keywords to block. ``None`` uses the module-level default
            list (``_DEFAULT_BLOCKED``). ``[]`` passes all items through.

    Returns:
        A new list with matching items removed.
    """
    keywords = blocked if blocked is not None else _DEFAULT_BLOCKED
    if not keywords:
        return list(items)

    keywords_norm = [_normalize(k) for k in keywords]
    result: list[NewsItem] = []
    dropped = 0

    for item in items:
        text = _normalize(item.title + " " + item.body)
        if not any(kw in text for kw in keywords_norm):
            result.append(item)
        else:
            dropped += 1

    if dropped:
        logger.info("Content filter dropped %d item(s)", dropped)

    return result
