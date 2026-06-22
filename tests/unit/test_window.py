"""Unit tests for the time-window filter (pipeline/window.py).

Covers:
- parse_since: valid formats (24h, 7d, 30m), malformed input
- filter_by_window / apply_window: mixed dates, None dates, all-outside
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noticias.pipeline.window import apply_window, filter_by_window, parse_since
from tests.helpers import make_item


class TestParseSince:
    @pytest.mark.parametrize(
        ("input_str", "expected_minutes"),
        [
            ("30m", 30),
            ("1m", 1),
            ("60m", 60),
            ("24h", 24 * 60),
            ("1h", 60),
            ("7d", 7 * 24 * 60),
            ("1d", 24 * 60),
        ],
    )
    def test_valid_formats(self, input_str: str, expected_minutes: int) -> None:
        result = parse_since(input_str)
        assert result == timedelta(minutes=expected_minutes)

    @pytest.mark.parametrize(
        "invalid",
        ["", "abc", "1x", "24", "h", "  ", None],
    )
    def test_malformed_raises(self, invalid: str | None) -> None:
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_since(invalid)  # type: ignore[arg-type]


class TestFilterByWindow:
    def test_items_within_window_kept(self) -> None:
        now = datetime.now(tz=timezone.utc)
        item1 = make_item("Recent", published_at=now - timedelta(hours=1))
        item2 = make_item("Older", published_at=now - timedelta(hours=10))
        since = timedelta(hours=6)
        result = filter_by_window([item1, item2], since)
        assert len(result) == 1
        assert result[0].title == "Recent"

    def test_all_items_within_window(self) -> None:
        now = datetime.now(tz=timezone.utc)
        items = [
            make_item("A", published_at=now - timedelta(hours=1)),
            make_item("B", published_at=now - timedelta(hours=2)),
        ]
        result = filter_by_window(items, timedelta(hours=12))
        assert len(result) == 2

    def test_all_items_outside_window(self) -> None:
        now = datetime.now(tz=timezone.utc)
        items = [
            make_item("Old", published_at=now - timedelta(hours=48)),
            make_item("Older", published_at=now - timedelta(hours=72)),
        ]
        result = filter_by_window(items, timedelta(hours=24))
        assert result == []

    def test_none_date_excluded(self) -> None:
        """Items with published_at=None are always excluded."""
        item = make_item("No date", published_at=None)
        result = filter_by_window([item], timedelta(hours=24))
        assert result == []

    def test_mixed_dates(self) -> None:
        now = datetime.now(tz=timezone.utc)
        items = [
            make_item("In window", published_at=now - timedelta(hours=2)),
            make_item("Outside", published_at=now - timedelta(hours=48)),
            make_item("None date", published_at=None),
        ]
        result = filter_by_window(items, timedelta(hours=24))
        assert len(result) == 1
        assert result[0].title == "In window"


class TestApplyWindow:
    def test_apply_window_alias(self) -> None:
        """apply_window should behave identically to filter_by_window."""
        now = datetime.now(tz=timezone.utc)
        items = [make_item("Test item", published_at=now - timedelta(hours=1))]
        via_filter = filter_by_window(items, timedelta(hours=24))
        via_apply = apply_window(items, timedelta(hours=24))
        assert len(via_filter) == len(via_apply)
        assert via_filter[0].title == via_apply[0].title

    def test_empty_input(self) -> None:
        assert apply_window([], timedelta(hours=24)) == []
