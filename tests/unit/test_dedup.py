"""Unit tests for near-duplicate detection (pipeline/dedup.py).

Covers:
- Within-source duplicate removal
- Cross-source duplicate removal
- Similar-but-distinct items survive
- Keep-earliest published_at logic
- Edge cases: empty list, single item, None dates
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from noticias.pipeline.dedup import dedup
from tests.helpers import make_item


class TestDedup:
    def test_empty_list(self) -> None:
        assert dedup([]) == []

    def test_single_item(self) -> None:
        item = make_item("Solo")
        result = dedup([item])
        assert len(result) == 1
        assert result[0].title == "Solo"

    def test_identical_titles_within_source(self) -> None:
        """Same title in same source → duplicate (title ratio 1.0 > 0.85)."""
        now = datetime.now(tz=timezone.utc)
        early = make_item("Duplicate title", source="pagina12", published_at=now - timedelta(hours=2))
        late = make_item("Duplicate title", source="pagina12", published_at=now - timedelta(hours=1))
        result = dedup([early, late])
        assert len(result) == 1
        assert result[0].published_at == early.published_at  # keep earliest

    def test_identical_titles_across_sources(self) -> None:
        """Same title across different sources → cross-source duplicate."""
        now = datetime.now(tz=timezone.utc)
        a = make_item("Shared story", source="pagina12", published_at=now - timedelta(hours=3))
        b = make_item("Shared story", source="infobae", published_at=now - timedelta(hours=1))
        result = dedup([a, b])
        assert len(result) == 1
        assert result[0].source == "pagina12"  # earlier source kept

    def test_similar_titles_above_threshold(self) -> None:
        """Titles with fuzz ratio > 0.85 should be deduped."""
        a = make_item("El presidente anunció nuevas medidas económicas hoy")
        b = make_item("El presidente anuncia nuevas medidas económicas")
        result = dedup([a, b])
        assert len(result) == 1

    def test_similar_urls_above_threshold(self) -> None:
        """URLs with fuzz ratio > 0.9 should be deduped."""
        a = make_item("Title A", url="https://example.com/story/12345")
        b = make_item("Title B", url="https://example.com/story/12346")
        result = dedup([a, b])
        assert len(result) == 1

    def test_similar_but_distinct_survive(self) -> None:
        """Titles below threshold and URLs below threshold → both kept."""
        a = make_item(
            "Programming language Rust reaches version 50",
            url="https://rust-lang.org/blog/announcing-rust-50",
        )
        b = make_item(
            "NASA discovers water on Mars subsurface ocean",
            url="https://nasa.gov/mars/ocean-discovery-2026",
        )
        result = dedup([a, b])
        assert len(result) == 2

    def test_keep_earliest_with_none_date(self) -> None:
        """Item with None date is kept if the other has a date (the dated one wins)."""
        now = datetime.now(tz=timezone.utc)
        dated = make_item("Same title", source="pagina12", published_at=now - timedelta(hours=1))
        nodate = make_item("Same title", source="infobae", published_at=None)
        result = dedup([nodate, dated])
        assert len(result) == 1
        assert result[0].published_at is not None  # dated one wins

    def test_both_none_date_keeps_first(self) -> None:
        """Both None dates → keep first in iteration order."""
        a = make_item("Same title", source="pagina12", published_at=None)
        b = make_item("Same title", source="infobae", published_at=None)
        result = dedup([a, b])
        assert len(result) == 1
        assert result[0].source == "pagina12"  # first kept

    def test_multiple_duplicates_reduced_to_one(self) -> None:
        """Three identical titles → single item remains."""
        items = [
            make_item("Triple duplicate", source="a", published_at=datetime(2026, 6, 21, 10, 0, 0, tzinfo=timezone.utc)),
            make_item("Triple duplicate", source="b", published_at=datetime(2026, 6, 21, 11, 0, 0, tzinfo=timezone.utc)),
            make_item("Triple duplicate", source="c", published_at=datetime(2026, 6, 21, 9, 0, 0, tzinfo=timezone.utc)),
        ]
        result = dedup(items)
        assert len(result) == 1
        # Earliest (9:00) should survive
        assert result[0].source == "c"
