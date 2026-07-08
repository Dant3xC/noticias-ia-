from __future__ import annotations

from datetime import datetime
from enum import Enum

import msgspec


class Lean(str, Enum):
    """Ideological lean of a news source."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class Source(msgspec.Struct, frozen=True):
    """A news source with its RSS feed URL and ideological lean."""

    name: str
    url: str
    lean: Lean
    last_fetched_status: str = "never"
    last_fetched_at: datetime | None = None


class SourceConfig(msgspec.Struct):
    """Persistent configuration holding sources and pipeline settings."""

    version: int = 1
    sources: list[Source] = []
    topics: list[str] = []
    blocked_keywords: list[str] | None = None
    model: str = "groq/llama-3.3-70b-versatile"
    fetch_timeout_s: float = 15.0
    default_window_h: int = 24
    token_budget: int = 9000
    max_concurrent_sources: int = 5
    rate_limit_s: int = 5
