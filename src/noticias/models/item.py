from __future__ import annotations

from datetime import datetime

import msgspec


class NewsItem(msgspec.Struct, frozen=True):
    """A normalized news item from any RSS/Atom source."""

    title: str
    url: str
    source: str
    lean: str
    body: str
    published_at: datetime | None = None
