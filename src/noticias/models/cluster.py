from __future__ import annotations

import msgspec

from noticias.models.item import NewsItem


class FamilyFormatSource(msgspec.Struct, frozen=True):
    """A source entry within a family-format payload."""

    name: str
    lean: str


class PerSourceEntry(msgspec.Struct, frozen=True):
    """Per-source headline and body excerpt within a family-format payload."""

    source: str
    headline: str
    body_excerpt: str
    published_at: str  # ISO-format datetime string


class FamilyFormatPayload(msgspec.Struct):
    """Compact per-cluster payload sent to the LLM.

    This is the cost-control boundary: the LLM receives only this structured
    payload, never raw article bodies.
    """

    event_label: str
    sources: list[FamilyFormatSource]
    per_source: list[PerSourceEntry]
    common_facts: list[str]
    divergences: list[str]


class LLMResponse(msgspec.Struct):
    """Parsed response from the LLM summary call."""

    cluster_id: str
    summary: str
    highlights: list[str] = []


class Cluster(msgspec.Struct):
    """A story cluster grouping related news items from one or more sources."""

    event_label: str = ""
    items: list[NewsItem] = []
    sources: list[str] = []
    per_source: list[PerSourceEntry] = []
    common_facts: list[str] = []
    divergences: list[str] = []
    trust_label: str = ""
    trust_reason: str = ""
    summary: str = ""
    highlights: list[str] = []
    divergence_ratio: float = 0.0
