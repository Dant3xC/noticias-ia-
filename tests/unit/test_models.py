"""Unit tests for all msgspec data models.

Covers:
- Enum construction for Lean
- Encode / decode round-trips for all 9+ Structs
- Field defaults applied correctly on decode (backward tolerance for Snapshot)
"""

from __future__ import annotations

from datetime import datetime, timezone

import msgspec
import pytest

from noticias.models.cluster import (
    Cluster,
    FamilyFormatPayload,
    FamilyFormatSource,
    LLMResponse,
    PerSourceEntry,
)
from noticias.models.item import NewsItem
from noticias.models.snapshot import Snapshot, SnapshotCluster
from noticias.models.source import Lean, Source, SourceConfig

# ── Lean enum ──────────────────────────────────────────────────────────────


class TestLean:
    def test_values(self) -> None:
        assert Lean.LEFT.value == "left"
        assert Lean.CENTER.value == "center"
        assert Lean.RIGHT.value == "right"

    def test_from_string(self) -> None:
        assert Lean("left") is Lean.LEFT
        assert Lean("center") is Lean.CENTER
        assert Lean("right") is Lean.RIGHT

    def test_invalid_value(self) -> None:
        with pytest.raises(ValueError, match="'farleft' is not a valid Lean"):
            Lean("farleft")


# ── Source ─────────────────────────────────────────────────────────────────


class TestSource:
    def test_default_fields(self) -> None:
        s = Source(name="test", url="https://example.com/rss", lean=Lean.CENTER)
        assert s.last_fetched_status == "never"
        assert s.last_fetched_at is None

    def test_frozen(self) -> None:
        s = Source(name="test", url="https://example.com/rss", lean=Lean.LEFT)
        with pytest.raises(AttributeError):
            s.name = "changed"  # type: ignore[misc]

    def _roundtrip(self, source: Source) -> None:
        data = msgspec.json.encode(source)
        decoded = msgspec.json.decode(data, type=Source)
        assert decoded == source

    def test_encode_decode_basic(self) -> None:
        self._roundtrip(Source(name="test", url="https://x.com/rss", lean=Lean.LEFT))

    def test_encode_decode_with_dates(self) -> None:
        s = Source(
            name="test",
            url="https://x.com/rss",
            lean=Lean.RIGHT,
            last_fetched_status="ok",
            last_fetched_at=datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc),
        )
        self._roundtrip(s)


# ── SourceConfig ────────────────────────────────────────────────────────────


class TestSourceConfig:
    def test_default_sources(self) -> None:
        cfg = SourceConfig()
        assert cfg.sources == []
        assert cfg.version == 1

    def test_encode_decode(self) -> None:
        cfg = SourceConfig(
            sources=[
                Source(name="a", url="https://a.com/rss", lean=Lean.LEFT),
                Source(name="b", url="https://b.com/rss", lean=Lean.RIGHT),
            ],
        )
        data = msgspec.json.encode(cfg)
        decoded = msgspec.json.decode(data, type=SourceConfig)
        assert decoded == cfg
        assert len(decoded.sources) == 2


# ── NewsItem ────────────────────────────────────────────────────────────────


class TestNewsItem:
    def test_frozen(self) -> None:
        item = NewsItem(
            title="T", url="https://x.com", source="s", lean="left", body="body"
        )
        with pytest.raises(AttributeError):
            item.title = "other"  # type: ignore[misc]

    def test_encode_decode(self, sample_news_item: NewsItem) -> None:
        data = msgspec.json.encode(sample_news_item)
        decoded = msgspec.json.decode(data, type=NewsItem)
        assert decoded == sample_news_item

    def test_published_at_none(self) -> None:
        item = NewsItem(
            title="T", url="https://x.com", source="s", lean="left", body="body"
        )
        assert item.published_at is None


# ── Cluster models ──────────────────────────────────────────────────────────


class TestFamilyFormatSource:
    def test_encode_decode(self) -> None:
        obj = FamilyFormatSource(name="clarin", lean="right")
        data = msgspec.json.encode(obj)
        decoded = msgspec.json.decode(data, type=FamilyFormatSource)
        assert decoded == obj
        assert decoded.lean == "right"


class TestPerSourceEntry:
    def test_encode_decode(self) -> None:
        obj = PerSourceEntry(
            source="clarin",
            headline="Headline",
            body_excerpt="Excerpt of the body",
            published_at="2026-06-21T12:00:00+00:00",
        )
        data = msgspec.json.encode(obj)
        decoded = msgspec.json.decode(data, type=PerSourceEntry)
        assert decoded == obj


class TestFamilyFormatPayload:
    def test_encode_decode(self) -> None:
        obj = FamilyFormatPayload(
            event_label="Test event",
            sources=[
                FamilyFormatSource(name="a", lean="left"),
                FamilyFormatSource(name="b", lean="right"),
            ],
            per_source=[
                PerSourceEntry(
                    source="a",
                    headline="H1",
                    body_excerpt="Ex1",
                    published_at="2026-06-21T12:00:00+00:00",
                ),
            ],
            common_facts=["fact1"],
            divergences=["div1"],
        )
        data = msgspec.json.encode(obj)
        decoded = msgspec.json.decode(data, type=FamilyFormatPayload)
        assert decoded == obj


class TestLLMResponse:
    def test_default_highlights(self) -> None:
        resp = LLMResponse(cluster_id="c1", summary="Summary text")
        assert resp.highlights == []

    def test_encode_decode(self) -> None:
        resp = LLMResponse(
            cluster_id="c1",
            summary="Summary text",
            highlights=["point 1", "point 2"],
        )
        data = msgspec.json.encode(resp)
        decoded = msgspec.json.decode(data, type=LLMResponse)
        assert decoded == resp

    def test_decode_missing_highlights(self) -> None:
        """Backward tolerance: missing highlights defaults to []."""
        raw = b'{"cluster_id":"c1","summary":"Summary text"}'
        decoded = msgspec.json.decode(raw, type=LLMResponse)
        assert decoded.highlights == []


class TestCluster:
    def test_defaults(self) -> None:
        c = Cluster()
        assert c.event_label == ""
        assert c.items == []
        assert c.sources == []
        assert c.divergence_ratio == 0.0

    def test_encode_decode(self) -> None:
        c = Cluster(
            event_label="Event",
            sources=["a", "b"],
            divergence_ratio=0.15,
        )
        data = msgspec.json.encode(c)
        decoded = msgspec.json.decode(data, type=Cluster)
        assert decoded.event_label == "Event"
        assert decoded.sources == ["a", "b"]
        assert decoded.divergence_ratio == 0.15


# ── Snapshot models ─────────────────────────────────────────────────────────


class TestSnapshotCluster:
    def test_default_highlights(self) -> None:
        sc = SnapshotCluster(
            event_label="E", trust_label="alta", summary="Sum"
        )
        assert sc.highlights == []

    def test_encode_decode(self) -> None:
        sc = SnapshotCluster(
            event_label="Event",
            trust_label="alta",
            trust_reason="3 fuentes diversas",
            summary="Summary",
            sources=["a", "b"],
            highlights=["hl1"],
        )
        data = msgspec.json.encode(sc)
        decoded = msgspec.json.decode(data, type=SnapshotCluster)
        assert decoded == sc


class TestSnapshot:
    def test_default_clusters(self) -> None:
        snap = Snapshot(
            date="2026-06-21",
            generated_at=datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc),
            sources_used=["pagina12"],
        )
        assert snap.version == 1
        assert snap.clusters == []
        assert snap.fetch_failures == []

    def test_encode_decode(self) -> None:
        snap = Snapshot(
            date="2026-06-21",
            generated_at=datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc),
            sources_used=["a", "b"],
            clusters=[
                SnapshotCluster(
                    event_label="Event",
                    trust_label="alta",
                    summary="Summary",
                ),
            ],
        )
        data = msgspec.json.encode(snap)
        decoded = msgspec.json.decode(data, type=Snapshot)
        assert decoded == snap

    def test_decode_missing_highlights(self) -> None:
        """Backward tolerance: missing highlights on cluster defaults to []."""
        raw = (
            b'{"date":"2026-06-21",'
            b'"generated_at":"2026-06-21T12:00:00+00:00",'
            b'"sources_used":["a"],'
            b'"clusters":[{"event_label":"E","trust_label":"alta","summary":"S"}]}'
        )
        decoded = msgspec.json.decode(raw, type=Snapshot)
        assert len(decoded.clusters) == 1
        assert decoded.clusters[0].highlights == []

    def test_decode_missing_trust_reason(self) -> None:
        """Backward tolerance: missing trust_reason defaults to ''."""
        raw = (
            b'{"date":"2026-06-21",'
            b'"generated_at":"2026-06-21T12:00:00+00:00",'
            b'"sources_used":["a"],'
            b'"clusters":[{"event_label":"E","trust_label":"alta","summary":"S"}]}'
        )
        decoded = msgspec.json.decode(raw, type=Snapshot)
        assert decoded.clusters[0].trust_reason == ""
