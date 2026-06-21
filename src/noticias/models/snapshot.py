from __future__ import annotations

from datetime import datetime

import msgspec


class SnapshotCluster(msgspec.Struct):
    """A single cluster entry within a persisted daily snapshot."""

    event_label: str
    trust_label: str
    trust_reason: str = ""
    summary: str = ""
    sources: list[str] = []
    highlights: list[str] = []


class Snapshot(msgspec.Struct):
    """Daily snapshot of the full pipeline output.

    version: schema version for backward compatibility — missing fields on
    decode will be filled from Struct defaults. Placed last so that all
    required fields precede optional ones (msgspec convention).
    """

    date: str  # YYYY-MM-DD
    generated_at: datetime
    sources_used: list[str]
    clusters: list[SnapshotCluster] = []
    fetch_failures: list[dict] = []
    version: int = 1
