"""PipelineOptions — frozen dataclass for orchestrator filter configuration.

Carries filter-stage configuration (content filter keywords, topic filter
topics, opt-out flags) from the CLI layer into the pipeline orchestrator.

Designed as a frozen dataclass so that test fixtures are cheap and
accidental mutation is prevented.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PipelineOptions:
    """Configuration options for the orchestrator's filter stages.

    Attributes:
        blocked_keywords: Keywords to block in the content filter.
            ``None`` (default) = use the module-level default keyword list.
            ``[]`` = no filtering (passthrough).
        topics: Topics to allowlist in the topic filter.
            ``[]`` (default) = no topic filter applied.
        no_filter: If ``True``, skip the content filter entirely.
        no_topics: If ``True``, skip the topic filter entirely.
        max_topics: Maximum number of topics to apply (default 10).
    """

    blocked_keywords: list[str] | None = None
    topics: list[str] = field(default_factory=list)
    no_filter: bool = False
    no_topics: bool = False
    max_topics: int = 10
