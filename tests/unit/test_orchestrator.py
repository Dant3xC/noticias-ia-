"""Unit tests for the pipeline orchestrator helper functions.

Focuses on ``_resolve_topics`` — the topic resolution logic that decides
whether the topic filter runs, which topics to use (CLI vs config), and
enforces the topic cap.

Test cases:
- CLI topics override config topics
- Config topics used when no CLI topics
- ``no_topics=True`` skips regardless of config
- Topic cap (more than 10 topics → only first 10 + warning)
- Empty topics list in either CLI or config → no filter applied
- Topic list with empty strings → ignored (passthrough from _resolve_topics)

Does NOT test ``filter_topics`` itself (covered in test_topic_filter.py),
nor the integration with ``run_pipeline_async`` (covered in
tests/component/test_orchestrator.py and
tests/component/test_orchestrator_with_filters.py).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from noticias.models.source import SourceConfig
from noticias.pipeline.options import PipelineOptions
from noticias.pipeline.orchestrator import _resolve_topics


# ── Helper factories ───────────────────────────────────────────────────────


def _make_opts(
    topics: list[str] | None = None,
    no_topics: bool = False,
    max_topics: int = 10,
) -> PipelineOptions:
    """Build a PipelineOptions with only topic-relevant fields."""
    kwargs: dict = {"no_topics": no_topics, "max_topics": max_topics}
    if topics is not None:
        kwargs["topics"] = topics
    return PipelineOptions(**kwargs)


def _make_config(topics: list[str] | None = None) -> SourceConfig:
    """Build a SourceConfig with optional topics."""
    kwargs: dict = {}
    if topics is not None:
        kwargs["topics"] = topics
    return SourceConfig(**kwargs)


# ── Tests ──────────────────────────────────────────────────────────────────


class TestResolveTopics:
    """Tests for ``_resolve_topics`` topic resolution logic."""

    def test_cli_topics_override_config(self) -> None:
        """CLI topics take precedence over config topics."""
        opts = _make_opts(topics=["política"])
        config = _make_config(topics=["economía"])
        result = _resolve_topics(opts, config)
        assert result == ["política"]

    def test_config_topics_used_when_no_cli_topics(self) -> None:
        """Config topics used when CLI provides no explicit topics."""
        opts = _make_opts(topics=[])
        config = _make_config(topics=["economía"])
        result = _resolve_topics(opts, config)
        assert result == ["economía"]

    def test_no_topics_true_skips_despite_config(self) -> None:
        """``no_topics=True`` returns ``None`` even if config has topics."""
        opts = _make_opts(topics=[], no_topics=True)
        config = _make_config(topics=["economía"])
        result = _resolve_topics(opts, config)
        assert result is None

    def test_no_topics_true_skips_despite_cli_topics(self) -> None:
        """``no_topics=True`` returns ``None`` even if CLI provided topics."""
        opts = _make_opts(topics=["política"], no_topics=True)
        config = _make_config(topics=[])
        result = _resolve_topics(opts, config)
        assert result is None

    def test_excess_topics_capped(self) -> None:
        """More than ``max_topics`` topics → only first ``max_topics`` used."""
        opts = _make_opts(
            topics=[str(i) for i in range(15)],
            max_topics=10,
        )
        config = _make_config(topics=[])
        with patch("noticias.pipeline.orchestrator.logger") as mock_logger:
            result = _resolve_topics(opts, config)
        assert result == [str(i) for i in range(10)]
        mock_logger.warning.assert_called_once()

    def test_excess_topics_capped_from_config(self) -> None:
        """Config topics > max_topics also gets capped."""
        opts = _make_opts(topics=[], max_topics=3)
        config = _make_config(topics=["a", "b", "c", "d", "e"])
        with patch("noticias.pipeline.orchestrator.logger") as mock_logger:
            result = _resolve_topics(opts, config)
        assert result == ["a", "b", "c"]
        mock_logger.warning.assert_called_once()

    def test_empty_cli_and_empty_config_returns_none(self) -> None:
        """When both CLI and config have empty lists, topic filter is skipped."""
        opts = _make_opts(topics=[])
        config = _make_config(topics=[])
        result = _resolve_topics(opts, config)
        assert result is None

    def test_cli_not_provided_and_config_empty_returns_none(self) -> None:
        """Default PipelineOptions (no topics anywhere) → skip filter."""
        opts = _make_opts()  # topics defaults to []
        config = _make_config(topics=[])
        result = _resolve_topics(opts, config)
        assert result is None

    def test_at_limit_no_warning(self) -> None:
        """Exactly ``max_topics`` topics → all used, no warning."""
        opts = _make_opts(topics=[str(i) for i in range(10)])
        config = _make_config(topics=[])
        with patch("noticias.pipeline.orchestrator.logger") as mock_logger:
            result = _resolve_topics(opts, config)
        assert result == [str(i) for i in range(10)]
        mock_logger.warning.assert_not_called()

    def test_empty_strings_in_cli_topics_passed_through(self) -> None:
        """Empty strings in CLI topics are passed through (filter_topics handles stripping)."""
        opts = _make_opts(topics=["economía", "", "política"])
        config = _make_config(topics=[])
        result = _resolve_topics(opts, config)
        assert result == ["economía", "", "política"]

    def test_config_with_empty_strings_passed_through(self) -> None:
        """Empty strings in config topics are passed through."""
        opts = _make_opts(topics=[])
        config = _make_config(topics=["economía", ""])
        result = _resolve_topics(opts, config)
        assert result == ["economía", ""]
