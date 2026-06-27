"""Unit tests for PipelineOptions frozen dataclass (pipeline/options.py).

Covers:
- Default values for all fields
- ``blocked_keywords=None`` means use default
- ``topics=[]`` means no topic filter
- ``no_filter=False`` means filter is active
- ``no_topics=False`` means filter is active
- Frozen: mutation raises FrozenInstanceError
- All field combinations work
"""

from __future__ import annotations

import pytest

from noticias.pipeline.options import PipelineOptions


class TestPipelineOptionsDefaults:
    """PipelineOptions() produces expected defaults."""

    def test_default_blocked_keywords_is_none(self) -> None:
        opts = PipelineOptions()
        assert opts.blocked_keywords is None

    def test_default_topics_is_empty(self) -> None:
        opts = PipelineOptions()
        assert opts.topics == []

    def test_default_no_filter_is_false(self) -> None:
        opts = PipelineOptions()
        assert opts.no_filter is False

    def test_default_no_topics_is_false(self) -> None:
        opts = PipelineOptions()
        assert opts.no_topics is False

    def test_default_max_topics_is_10(self) -> None:
        opts = PipelineOptions()
        assert opts.max_topics == 10


class TestPipelineOptionsSemantics:
    """Semantic interpretation of field values matches design intent."""

    def test_blocked_keywords_none_means_use_defaults(self) -> None:
        """``None`` signals 'use module-level default list' to the filter."""
        opts = PipelineOptions(blocked_keywords=None)
        assert opts.blocked_keywords is None

    def test_topics_empty_means_no_filter(self) -> None:
        """Empty list signals 'no topic filter applied'."""
        opts = PipelineOptions(topics=[])
        assert opts.topics == []

    def test_no_filter_false_means_filter_active(self) -> None:
        """``False`` means the content filter runs normally."""
        opts = PipelineOptions(no_filter=False)
        assert opts.no_filter is False

    def test_no_topics_false_means_filter_active(self) -> None:
        """``False`` means the topic filter may run (depends on topics)."""
        opts = PipelineOptions(no_topics=False)
        assert opts.no_topics is False


class TestPipelineOptionsFrozen:
    """Frozen dataclass prevents accidental mutation."""

    def test_cannot_set_blocked_keywords(self) -> None:
        opts = PipelineOptions()
        with pytest.raises(Exception):
            opts.blocked_keywords = ["foo"]  # type: ignore[misc]

    def test_cannot_set_topics(self) -> None:
        opts = PipelineOptions()
        with pytest.raises(Exception):
            opts.topics = ["foo"]  # type: ignore[misc]

    def test_cannot_set_no_filter(self) -> None:
        opts = PipelineOptions()
        with pytest.raises(Exception):
            opts.no_filter = True  # type: ignore[misc]

    def test_cannot_set_no_topics(self) -> None:
        opts = PipelineOptions()
        with pytest.raises(Exception):
            opts.no_topics = True  # type: ignore[misc]


class TestPipelineOptionsFieldCombinations:
    """All field combinations construct without error."""

    def test_all_defaults(self) -> None:
        opts = PipelineOptions()
        assert opts.blocked_keywords is None
        assert opts.topics == []
        assert opts.no_filter is False
        assert opts.no_topics is False
        assert opts.max_topics == 10

    def test_explicit_blocked_keywords(self) -> None:
        opts = PipelineOptions(blocked_keywords=["foo", "bar"])
        assert opts.blocked_keywords == ["foo", "bar"]

    def test_explicit_topics(self) -> None:
        opts = PipelineOptions(topics=["economía", "fútbol"])
        assert opts.topics == ["economía", "fútbol"]

    def test_no_filter_true(self) -> None:
        opts = PipelineOptions(no_filter=True)
        assert opts.no_filter is True

    def test_no_topics_true(self) -> None:
        opts = PipelineOptions(no_topics=True)
        assert opts.no_topics is True

    def test_custom_max_topics(self) -> None:
        opts = PipelineOptions(max_topics=5)
        assert opts.max_topics == 5

    def test_all_fields_explicit(self) -> None:
        opts = PipelineOptions(
            blocked_keywords=["horóscopo"],
            topics=["política"],
            no_filter=True,
            no_topics=True,
            max_topics=3,
        )
        assert opts.blocked_keywords == ["horóscopo"]
        assert opts.topics == ["política"]
        assert opts.no_filter is True
        assert opts.no_topics is True
        assert opts.max_topics == 3

    def test_multiple_instances_independent(self) -> None:
        """Each instance has its own field values (no shared state)."""
        a = PipelineOptions(topics=["economía"])
        b = PipelineOptions(topics=["fútbol"])
        assert a.topics == ["economía"]
        assert b.topics == ["fútbol"]
        assert a.topics is not b.topics
