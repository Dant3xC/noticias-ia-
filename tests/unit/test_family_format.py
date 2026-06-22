"""Unit tests for family-format builder (pipeline/family.py).

Covers:
- build_family_format: multi-source, single-source, empty cluster
- common_facts / divergences computation with known inputs
- divergence_ratio formula correctness (no divergence → 0.0, all diverge → 1.0)
- truncate_payload: under limit, over limit
"""

from __future__ import annotations

from datetime import datetime, timezone

import msgspec
import pytest

from noticias.models.cluster import FamilyFormatPayload, PerSourceEntry
from noticias.pipeline.family import (
    _compute_facts_divergences,
    build_family_format,
    divergence_ratio,
    truncate_payload,
)
from tests.helpers import make_cluster, make_item

# ── build_family_format ────────────────────────────────────────────────────


class TestBuildFamilyFormat:
    def test_multi_source_cluster(self) -> None:
        items = [
            make_item(
                "Corte Suprema falla a favor de libertad",
                source="pagina12",
                lean="left",
                body="La Corte Suprema falló a favor de la libertad de expresión en un fallo histórico que sienta precedente.",
                url="https://p12.com/a",
            ),
            make_item(
                "Corte Suprema falla a favor de libertad",
                source="infobae",
                lean="center",
                body="La Corte Suprema de Argentina falló a favor de la libertad de expresión marcando un hito judicial.",
                url="https://infobae.com/b",
            ),
            make_item(
                "Fallan a favor de la libertad de expresión",
                source="clarin",
                lean="right",
                body="Corte Suprema falla a favor de la libertad de expresión en un fallo importante.",
                url="https://clarin.com/c",
            ),
        ]
        cluster_obj = make_cluster(items=items)

        payload = build_family_format(cluster_obj)

        # Payload structure
        assert payload.event_label  # non-empty
        assert len(payload.sources) == 3
        assert len(payload.per_source) == 3
        assert len(payload.common_facts) > 0
        assert len(payload.divergences) >= 0

        # Cluster mutated
        assert cluster_obj.event_label == payload.event_label
        assert len(cluster_obj.common_facts) > 0

    def test_single_source_cluster(self) -> None:
        items = [
            make_item("Solo story", source="pagina12", body="Just one source body."),
        ]
        cluster_obj = make_cluster(items=items)
        payload = build_family_format(cluster_obj)

        assert len(payload.sources) == 1
        assert len(payload.per_source) == 1
        assert len(payload.divergences) == 0  # single source → no divergences

    def test_empty_cluster(self) -> None:
        cluster_obj = make_cluster(items=[])
        payload = build_family_format(cluster_obj)

        assert payload.event_label == ""
        assert payload.sources == []
        assert payload.per_source == []
        assert payload.common_facts == []
        assert payload.divergences == []

    def test_per_source_body_excerpt_truncated(self) -> None:
        """Body excerpt should be truncated to 500 chars."""
        long_body = "word " * 200  # ~1000 chars
        items = [
            make_item("Title", body=long_body, source="a"),
        ]
        cluster_obj = make_cluster(items=items)
        payload = build_family_format(cluster_obj)

        assert len(payload.per_source[0].body_excerpt) <= 500

    def test_common_facts_above_seventy_percent(self) -> None:
        """Tokens present in >70% of bodies appear in common_facts."""
        bodies = [
            "apple banana cherry date",
            "apple banana cherry elderberry",
            "apple banana cherry fig",
        ]
        common, _ = _compute_facts_divergences(bodies)
        # apple, banana, cherry present in all 3 (100% > 70%)
        assert "apple" in common
        assert "banana" in common
        assert "cherry" in common

    def test_divergences_in_exactly_one(self) -> None:
        """Tokens present in exactly one body appear in divergences."""
        bodies = [
            "apple banana",
            "banana cherry",
            "banana date",
        ]
        _, divs = _compute_facts_divergences(bodies)
        # apple in only body 1, cherry in only body 2, date in only body 3
        assert "apple" in divs
        assert "cherry" in divs
        assert "date" in divs
        # banana is in all 3 → NOT a divergence
        assert "banana" not in divs


# ── divergence_ratio ────────────────────────────────────────────────────────


class TestDivergenceRatio:
    def test_no_divergence_returns_zero(self) -> None:
        """All bodies identical → divergence_ratio = 0.0."""
        items = [
            make_item("Title A", body="apple banana cherry", source="a"),
            make_item("Title B", body="apple banana cherry", source="b"),
            make_item("Title C", body="apple banana cherry", source="c"),
        ]
        cluster_obj = make_cluster(items=items)
        ratio = divergence_ratio(cluster_obj)
        assert ratio == 0.0
        assert cluster_obj.divergence_ratio == 0.0

    def test_all_diverge_returns_one(self) -> None:
        """No overlapping tokens → divergence_ratio = 1.0."""
        items = [
            make_item("Title A", body="apple banana", source="a"),
            make_item("Title B", body="cherry date", source="b"),
            make_item("Title C", body="elderberry fig", source="c"),
        ]
        cluster_obj = make_cluster(items=items)
        ratio = divergence_ratio(cluster_obj)
        assert ratio == 1.0
        assert cluster_obj.divergence_ratio == 1.0

    def test_empty_cluster_returns_zero(self) -> None:
        cluster_obj = make_cluster(items=[])
        ratio = divergence_ratio(cluster_obj)
        assert ratio == 0.0

    def test_single_source_returns_zero(self) -> None:
        """Single source → no divergence possible."""
        items = [make_item("Solo")]
        cluster_obj = make_cluster(items=items)
        ratio = divergence_ratio(cluster_obj)
        assert ratio == 0.0

    def test_partial_divergence(self) -> None:
        """Mix of shared and unique tokens → ratio between 0 and 1."""
        items = [
            make_item("A", body="apple banana cherry date", source="a"),
            make_item("B", body="apple banana cherry elderberry", source="b"),
        ]
        cluster_obj = make_cluster(items=items)
        ratio = divergence_ratio(cluster_obj)
        # Union: {apple, banana, cherry, date, elderberry} = 5 tokens
        # Divergences: {date} (in only a), {elderberry} (in only b) = 2
        # Ratio: 2/5 = 0.4
        assert ratio == pytest.approx(0.4, abs=0.05)


# ── truncate_payload ────────────────────────────────────────────────────────


class TestTruncatePayload:
    def test_under_limit_unchanged(self) -> None:
        payload = FamilyFormatPayload(
            event_label="Test",
            sources=[],
            per_source=[],
            common_facts=[],
            divergences=[],
        )
        result = truncate_payload(payload, max_chars=1000)
        assert result is payload  # same object returned

    def test_over_limit_truncates_body(self) -> None:
        """Large body excerpt should be truncated below the max_chars limit."""
        long_body = "A" * 2000
        payload = FamilyFormatPayload(
            event_label="Test",
            sources=[],
            per_source=[
                PerSourceEntry(
                    source="a",
                    headline="Headline",
                    body_excerpt=long_body,
                    published_at="2026-06-21T12:00:00+00:00",
                ),
            ],
            common_facts=[],
            divergences=[],
        )
        result = truncate_payload(payload, max_chars=200)
        encoded = msgspec.json.encode(result)
        assert len(encoded) <= 200
        # Body should be shorter than original (2000 chars)
        assert len(result.per_source[0].body_excerpt) < 2000

    def test_multiple_sources_truncated_evenly(self) -> None:
        """With multiple sources, all body excerpts are shortened."""
        long_body = "B" * 1500
        payload = FamilyFormatPayload(
            event_label="Event",
            sources=[],
            per_source=[
                PerSourceEntry(source="a", headline="H1", body_excerpt=long_body, published_at="2026-06-21T12:00:00+00:00"),
                PerSourceEntry(source="b", headline="H2", body_excerpt=long_body, published_at="2026-06-21T13:00:00+00:00"),
            ],
            common_facts=[],
            divergences=[],
        )
        result = truncate_payload(payload, max_chars=500)
        encoded = msgspec.json.encode(result)
        assert len(encoded) <= 500
        # Both excerpts should be shorter than original
        assert len(result.per_source[0].body_excerpt) < 1500
        assert len(result.per_source[1].body_excerpt) < 1500



