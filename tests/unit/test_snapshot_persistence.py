"""Unit tests for snapshot persistence (persistence/snapshot.py).

Covers:
- write_snapshot creates the data directory if missing
- write_snapshot on a new day uses ``YYYY-MM-DD.json``
- write_snapshot on a day with existing file uses ``-HHMMSS`` suffix
- read_snapshot round-trips a Snapshot
- read_snapshot tolerates older schema (missing fields → defaults)
- list_snapshots returns files sorted by name descending
- list_snapshots returns empty list for non-existent dir
- Path traversal blocked by read_snapshot
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import msgspec
import pytest

from noticias.models.snapshot import Snapshot, SnapshotCluster
from noticias.persistence.snapshot import (
    list_snapshots,
    read_snapshot,
    write_snapshot,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_snapshot() -> Snapshot:
    """A minimal Snapshot for persistence tests."""
    return Snapshot(
        date="2026-06-21",
        generated_at=datetime(2026, 6, 21, 12, 0, 0),
        sources_used=["pagina12", "infobae"],
        clusters=[
            SnapshotCluster(
                event_label="Noticia de prueba",
                trust_label="alta",
                trust_reason="3 fuentes, acuerdo alto.",
                summary="Resumen de prueba.",
                sources=["pagina12", "infobae"],
                highlights=["Punto destacado 1"],
            ),
        ],
    )


# ── write_snapshot ──────────────────────────────────────────────────────────


class TestWriteSnapshot:
    def test_creates_data_dir(self, tmp_path: Path, sample_snapshot: Snapshot) -> None:
        """write_snapshot creates the target directory if it doesn't exist."""
        target = tmp_path / "nonexistent"
        assert not target.exists()

        written = write_snapshot(sample_snapshot, target)

        assert target.exists()
        assert written.exists()
        assert written.parent == target

    def test_first_run_uses_date_name(
        self, tmp_path: Path, sample_snapshot: Snapshot,
    ) -> None:
        """First write of the day uses YYYY-MM-DD.json."""
        written = write_snapshot(sample_snapshot, tmp_path)
        assert written.name == "2026-06-21.json"

    def test_second_run_uses_timestamp_suffix(
        self, tmp_path: Path, sample_snapshot: Snapshot,
    ) -> None:
        """Second write on the same day uses YYYY-MM-DD-HHMMSS.json."""
        p1 = write_snapshot(sample_snapshot, tmp_path)
        assert p1.name == "2026-06-21.json"

        p2 = write_snapshot(sample_snapshot, tmp_path)
        assert p2.name != p1.name
        assert p2.name.startswith("2026-06-21-")
        assert p2.name.endswith(".json")
        assert len(p2.stem) > len("2026-06-21")  # has suffix

    def test_first_file_not_overwritten(
        self, tmp_path: Path, sample_snapshot: Snapshot,
    ) -> None:
        """Original file is not modified when a second file is written."""
        p1 = write_snapshot(sample_snapshot, tmp_path)
        content_before = p1.read_bytes()

        write_snapshot(sample_snapshot, tmp_path)

        content_after = p1.read_bytes()
        assert content_before == content_after

    def test_returns_path_to_written_file(
        self, tmp_path: Path, sample_snapshot: Snapshot,
    ) -> None:
        """Return value is the actual path that was written."""
        written = write_snapshot(sample_snapshot, tmp_path)
        assert written.is_file()


# ── read_snapshot ───────────────────────────────────────────────────────────


class TestReadSnapshot:
    def test_round_trip(self, tmp_path: Path, sample_snapshot: Snapshot) -> None:
        """read_snapshot returns an equivalent Snapshot after write."""
        written = write_snapshot(sample_snapshot, tmp_path)
        loaded = read_snapshot(written)

        assert loaded.date == sample_snapshot.date
        assert loaded.sources_used == sample_snapshot.sources_used
        assert len(loaded.clusters) == len(sample_snapshot.clusters)
        assert loaded.clusters[0].event_label == "Noticia de prueba"
        assert loaded.clusters[0].trust_label == "alta"
        assert loaded.clusters[0].summary == "Resumen de prueba."

    def test_file_not_found(self, tmp_path: Path) -> None:
        """read_snapshot raises FileNotFoundError for missing file."""
        missing = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError):
            read_snapshot(missing)

    def test_backward_tolerance_missing_highlights(
        self, tmp_path: Path, sample_snapshot: Snapshot,
    ) -> None:
        """Reading a snapshot without highlights defaults to []."""
        # Write a snapshot manually without highlights for cluster.
        data = {
            "date": "2026-06-21",
            "generated_at": "2026-06-21T12:00:00",
            "sources_used": ["pagina12"],
            "clusters": [
                {
                    "event_label": "Test",
                    "trust_label": "alta",
                    "trust_reason": "",
                    "summary": "Test",
                    "sources": ["pagina12"],
                    # highlights intentionally absent
                },
            ],
        }
        path = tmp_path / "2026-06-21.json"
        path.write_bytes(msgspec.json.encode(data))

        loaded = read_snapshot(path)
        assert len(loaded.clusters) == 1
        assert loaded.clusters[0].highlights == []  # default

    def test_backward_tolerance_missing_trust_reason(
        self, tmp_path: Path, sample_snapshot: Snapshot,
    ) -> None:
        """Reading a snapshot without trust_reason defaults to ''."""
        data = {
            "date": "2026-06-21",
            "generated_at": "2026-06-21T12:00:00",
            "sources_used": ["pagina12"],
            "clusters": [
                {
                    "event_label": "Test",
                    "trust_label": "alta",
                    # trust_reason intentionally absent
                    "summary": "Test",
                    "sources": ["pagina12"],
                },
            ],
        }
        path = tmp_path / "2026-06-21.json"
        path.write_bytes(msgspec.json.encode(data))

        loaded = read_snapshot(path)
        assert loaded.clusters[0].trust_reason == ""

    def test_path_traversal_blocked(self) -> None:
        """read_snapshot raises ValueError on paths with '..'."""
        bad_path = Path.home() / ".ssh" / ".." / ".." / "etc" / "passwd"
        # The ".." check looks at .parts, and Path("..") in parts triggers it.
        trav_path = Path("../etc/passwd")
        with pytest.raises(ValueError, match="Path traversal blocked"):
            read_snapshot(trav_path)


# ── list_snapshots ──────────────────────────────────────────────────────────


class TestListSnapshots:
    def test_empty_dir(self, tmp_path: Path) -> None:
        """list_snapshots returns empty list for empty directory."""
        assert list_snapshots(tmp_path) == []

    def test_nonexistent_dir(self) -> None:
        """list_snapshots returns empty list for non-existent directory."""
        result = list_snapshots(Path("/nonexistent/path/that/does/not/exist"))
        assert result == []

    def test_returns_only_json_files(
        self, tmp_path: Path, sample_snapshot: Snapshot,
    ) -> None:
        """list_snapshots only returns .json files."""
        write_snapshot(sample_snapshot, tmp_path)
        # Create a non-JSON file.
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "data.csv").write_text("a,b,c")

        results = list_snapshots(tmp_path)
        assert all(p.suffix == ".json" for p in results)

    def test_sorted_descending(
        self, tmp_path: Path, sample_snapshot: Snapshot,
    ) -> None:
        """list_snapshots sorts files by name descending (newest first)."""
        # Create snapshots for different dates.
        snap1 = Snapshot(
            date="2026-06-20", generated_at=datetime(2026, 6, 20, 12, 0, 0),
            sources_used=[], clusters=[],
        )
        snap2 = Snapshot(
            date="2026-06-22", generated_at=datetime(2026, 6, 22, 12, 0, 0),
            sources_used=[], clusters=[],
        )
        snap3 = Snapshot(
            date="2026-06-21", generated_at=datetime(2026, 6, 21, 12, 0, 0),
            sources_used=[], clusters=[],
        )
        write_snapshot(snap2, tmp_path)
        write_snapshot(snap1, tmp_path)
        write_snapshot(snap3, tmp_path)

        results = list_snapshots(tmp_path)
        names = [p.name for p in results]
        # Descending: 2026-06-22, 2026-06-21, 2026-06-20
        assert names == ["2026-06-22.json", "2026-06-21.json", "2026-06-20.json"]
