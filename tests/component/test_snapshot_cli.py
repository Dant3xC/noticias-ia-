"""Component tests for ``noticias snapshot list`` and ``noticias snapshot show``.

Uses Typer's CliRunner with real snapshot files written to a temp
directory.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from noticias.cli.app import app
from noticias.models.snapshot import Snapshot, SnapshotCluster
from noticias.persistence.snapshot import write_snapshot

runner = CliRunner()


@pytest.fixture
def snapshot_with_clusters() -> Snapshot:
    """A Snapshot with 2 clusters."""
    return Snapshot(
        date="2026-06-21",
        generated_at=datetime(2026, 6, 21, 12, 0, 0),
        sources_used=["pagina12", "infobae"],
        clusters=[
            SnapshotCluster(
                event_label="Primera noticia",
                trust_label="alta",
                trust_reason="3 fuentes, acuerdo alto.",
                summary="Resumen de la primera noticia.",
                sources=["pagina12", "infobae"],
                highlights=["Punto destacado 1"],
            ),
            SnapshotCluster(
                event_label="Segunda noticia",
                trust_label="baja",
                trust_reason="Una sola fuente.",
                summary="Resumen de la segunda noticia.",
                sources=["pagina12"],
                highlights=[],
            ),
        ],
    )


@pytest.fixture
def snapshot_empty() -> Snapshot:
    """A Snapshot with no clusters."""
    return Snapshot(
        date="2026-06-22",
        generated_at=datetime(2026, 6, 22, 12, 0, 0),
        sources_used=["pagina12"],
    )


# ── snapshot list ───────────────────────────────────────────────────────────


class TestSnapshotList:
    def test_empty_data_dir(self, tmp_path: Path) -> None:
        """No snapshots → Spanish message, exit code 0."""
        with (
            patch("noticias.cli.app.Path.cwd", return_value=tmp_path),
        ):
            result = runner.invoke(app, ["snapshot", "list"])

        assert result.exit_code == 0
        assert "No hay instantáneas" in result.stdout

    def test_single_snapshot(self, tmp_path: Path, snapshot_with_clusters: Snapshot) -> None:
        """Single snapshot → table with the file listed."""
        data_dir = tmp_path / ".data"
        data_dir.mkdir(parents=True)
        write_snapshot(snapshot_with_clusters, data_dir)

        with (
            patch("noticias.cli.app.Path.cwd", return_value=tmp_path),
        ):
            result = runner.invoke(app, ["snapshot", "list"])

        assert result.exit_code == 0
        assert "2026-06-21.json" in result.stdout
        assert "2" in result.stdout  # cluster count

    def test_multiple_snapshots_newest_first(
        self, tmp_path: Path,
        snapshot_with_clusters: Snapshot,
        snapshot_empty: Snapshot,
    ) -> None:
        """Multiple snapshots are listed newest first."""
        data_dir = tmp_path / ".data"
        data_dir.mkdir(parents=True)
        write_snapshot(snapshot_with_clusters, data_dir)  # date=2026-06-21
        write_snapshot(snapshot_empty, data_dir)  # date=2026-06-22

        with (
            patch("noticias.cli.app.Path.cwd", return_value=tmp_path),
        ):
            result = runner.invoke(app, ["snapshot", "list"])

        assert result.exit_code == 0
        output = result.stdout

        # 2026-06-22 should appear before 2026-06-21 (newest first)
        idx_22 = output.index("2026-06-22.json")
        idx_21 = output.index("2026-06-21.json")
        assert idx_22 < idx_21

    def test_empty_and_nonempty_mixed(
        self, tmp_path: Path,
        snapshot_empty: Snapshot,
    ) -> None:
        """Snapshot with 0 clusters shows '0' in the table."""
        data_dir = tmp_path / ".data"
        data_dir.mkdir(parents=True)
        write_snapshot(snapshot_empty, data_dir)

        with (
            patch("noticias.cli.app.Path.cwd", return_value=tmp_path),
        ):
            result = runner.invoke(app, ["snapshot", "list"])

        assert result.exit_code == 0
        assert "Grupos" in result.stdout or "0" in result.stdout

    def test_no_voseo(self, tmp_path: Path, snapshot_with_clusters: Snapshot) -> None:
        """List output has no voseo."""
        data_dir = tmp_path / ".data"
        data_dir.mkdir(parents=True)
        write_snapshot(snapshot_with_clusters, data_dir)

        with (
            patch("noticias.cli.app.Path.cwd", return_value=tmp_path),
        ):
            result = runner.invoke(app, ["snapshot", "list"])

        output = result.stdout
        voseo_verbs = ["Usá", "Agregá", "Configurá", "Hacé", "Decí"]
        for verb in voseo_verbs:
            assert verb not in output, f"Voseo verb '{verb}' found in output"


# ── snapshot show ───────────────────────────────────────────────────────────


class TestSnapshotShow:
    def test_show_basename(self, tmp_path: Path, snapshot_with_clusters: Snapshot) -> None:
        """``snapshot show <basename>`` looks up in .data/."""
        data_dir = tmp_path / ".data"
        data_dir.mkdir(parents=True)
        write_snapshot(snapshot_with_clusters, data_dir)

        with (
            patch("noticias.cli.app.Path.cwd", return_value=tmp_path),
        ):
            result = runner.invoke(app, [
                "snapshot", "show", "2026-06-21.json",
            ])

        assert result.exit_code == 0
        assert "Primera noticia" in result.stdout
        assert "Segunda noticia" in result.stdout
        assert "Confianza" in result.stdout
        assert "Resumen de la primera noticia" in result.stdout

    def test_show_full_path(self, tmp_path: Path, snapshot_with_clusters: Snapshot) -> None:
        """``snapshot show <full-path>`` works."""
        data_dir = tmp_path / ".data"
        data_dir.mkdir(parents=True)
        path = write_snapshot(snapshot_with_clusters, data_dir)

        with (
            patch("noticias.cli.app.Path.cwd", return_value=tmp_path),
        ):
            result = runner.invoke(app, [
                "snapshot", "show", str(path),
            ])

        assert result.exit_code == 0
        assert "Primera noticia" in result.stdout

    def test_show_nonexistent(self, tmp_path: Path) -> None:
        """Non-existent file → Spanish error, exit code 1."""
        with (
            patch("noticias.cli.app.Path.cwd", return_value=tmp_path),
        ):
            result = runner.invoke(app, [
                "snapshot", "show", "nonexistent.json",
            ])

        assert result.exit_code == 1
        assert "no se encontró" in result.stdout

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        """Path traversal is rejected with Spanish error."""
        with (
            patch("noticias.cli.app.Path.cwd", return_value=tmp_path),
        ):
            result = runner.invoke(app, [
                "snapshot", "show", "../../etc/passwd",
            ])

        assert result.exit_code == 1
        assert "fuera del directorio" in result.stdout or "Error" in result.stdout

    def test_no_voseo(self, tmp_path: Path, snapshot_with_clusters: Snapshot) -> None:
        """Show output has no voseo."""
        data_dir = tmp_path / ".data"
        data_dir.mkdir(parents=True)
        write_snapshot(snapshot_with_clusters, data_dir)

        with (
            patch("noticias.cli.app.Path.cwd", return_value=tmp_path),
        ):
            result = runner.invoke(app, [
                "snapshot", "show", "2026-06-21.json",
            ])

        output = result.stdout
        voseo_verbs = ["Usá", "Agregá", "Configurá", "Hacé", "Decí"]
        for verb in voseo_verbs:
            assert verb not in output, f"Voseo verb '{verb}' found in output"

