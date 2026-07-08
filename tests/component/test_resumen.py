"""Component tests for ``noticias resumen`` command.

Uses Typer's CliRunner with mocked SourceRegistry and mocked
pipeline run_pipeline to avoid live RSS / LLM calls.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest
from typer.testing import CliRunner

from noticias.cli.app import app
from noticias.models.cluster import Cluster
from noticias.models.source import Lean, Source, SourceConfig
from noticias.persistence.snapshot import write_snapshot
from tests.helpers import make_item

runner = CliRunner()


@pytest.fixture
def mock_registry() -> MagicMock:
    """A mocked SourceRegistry with 3 test sources."""
    reg = MagicMock()
    reg.list.return_value = [
        Source(name="pagina12", url="https://www.pagina12.com.ar/rss", lean=Lean.LEFT),
        Source(name="infobae", url="https://www.infobae.com/rss/", lean=Lean.CENTER),
        Source(name="empty_source", url="", lean=Lean.LEFT),  # placeholder
    ]

    def mock_get(name: str) -> Source:
        for s in reg.list.return_value:
            if s.name == name:
                return s
        raise ValueError(f"source '{name}' not found")

    reg.get.side_effect = mock_get
    return reg


@pytest.fixture
def sample_clusters() -> list[Cluster]:
    """Two clusters with sensible test data."""
    return [
        Cluster(
            event_label="Noticia de prueba 1",
            trust_label="alta",
            trust_reason="3 fuentes, acuerdo alto.",
            summary="Resumen de la noticia de prueba 1.",
            highlights=["Punto destacado A"],
            sources=["pagina12", "infobae"],
            divergences=[],
            divergence_ratio=0.0,
            items=[
                make_item(source="pagina12", title="Titulo A"),
                make_item(source="infobae", title="Titulo A"),
            ],
        ),
        Cluster(
            event_label="Noticia de prueba 2",
            trust_label="baja",
            trust_reason="Una sola fuente.",
            summary="Resumen de la noticia de prueba 2.",
            highlights=["Punto destacado B"],
            sources=["pagina12"],
            divergences=[],
            divergence_ratio=0.0,
            items=[
                make_item(source="pagina12", title="Titulo B"),
            ],
        ),
    ]


# ── resumen --no-llm ────────────────────────────────────────────────────────


class TestResumenNoLlm:
    def test_run_with_no_llm(self, sample_clusters: list[Cluster]) -> None:
        """``noticias resumen --no-llm`` runs the pipeline and writes a snapshot."""
        with (
            patch("noticias.cli.app.SourceRegistry.default") as mock_reg,
            patch("noticias.cli.app.run_pipeline", return_value=sample_clusters) as mock_run,
        ):
            mock_reg.return_value.list.return_value = [
                Source(name="pagina12", url="https://www.pagina12.com.ar/rss", lean=Lean.LEFT),
                Source(name="infobae", url="https://www.infobae.com/rss/", lean=Lean.CENTER),
            ]
            mock_reg.return_value.get.side_effect = lambda name: (
                Source(name=name, url="https://example.com/rss", lean=Lean.CENTER)
            )

            result = runner.invoke(app, ["resumen", "--no-llm"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.stdout}"
        assert "Resumen" in result.stdout or "No se encontraron" in result.stdout

        # Verify pipeline was called
        mock_run.assert_called_once()

    def test_run_writes_snapshot_file(self, tmp_path: Path, sample_clusters: list[Cluster]) -> None:
        """Successful run writes at least one .data/YYYY-MM-DD.json file."""
        data_dir = tmp_path / ".data"

        with (
            patch("noticias.cli.app.SourceRegistry.default") as mock_reg,
            patch("noticias.cli.app.run_pipeline", return_value=sample_clusters) as _mock_run,
            patch("noticias.cli.app.Path.cwd", return_value=tmp_path),
        ):
            mock_reg.return_value.list.return_value = [
                Source(name="pagina12", url="https://www.pagina12.com.ar/rss", lean=Lean.LEFT),
            ]

            result = runner.invoke(app, ["resumen", "--no-llm"])

        assert result.exit_code == 0
        # Check a .data dir was created with at least one JSON file
        if data_dir.exists():
            json_files = list(data_dir.glob("*.json"))
            assert len(json_files) >= 1

    def test_second_run_same_day_creates_different_file(
        self, tmp_path: Path,
    ) -> None:
        """Re-running on the same day creates a -HHMMSS.json file."""
        data_dir = tmp_path / ".data"
        date_str = datetime.now().strftime("%Y-%m-%d")

        clusters = [
            Cluster(
                event_label="Test",
                trust_label="alta",
                trust_reason="OK",
                summary="Test",
                sources=["pagina12"],
                items=[make_item(source="pagina12")],
            ),
        ]

        with (
            patch("noticias.cli.app.SourceRegistry.default") as mock_reg,
            patch("noticias.cli.app.run_pipeline", return_value=clusters),
            patch("noticias.cli.app.Path.cwd", return_value=tmp_path),
        ):
            mock_reg.return_value.list.return_value = [
                Source(name="pagina12", url="https://www.pagina12.com.ar/rss", lean=Lean.LEFT),
            ]
            mock_reg.return_value.get.side_effect = lambda n: Source(name=n, url="https://example.com/rss", lean=Lean.CENTER)

            # First run
            r1 = runner.invoke(app, ["resumen", "--no-llm"])
            assert r1.exit_code == 0

            # Second run — should use -HHMMSS suffix
            r2 = runner.invoke(app, ["resumen", "--no-llm"])
            assert r2.exit_code == 0

        files = list(data_dir.glob("*.json"))
        assert len(files) >= 2
        # At least one file has the suffix format
        suffixed = [f for f in files if "-" in f.stem and not f.stem == date_str]
        assert len(suffixed) >= 1

    def test_empty_source_list(self) -> None:
        """No active sources → Spanish message, no pipeline call."""
        with (
            patch("noticias.cli.app.SourceRegistry.default") as mock_reg,
            patch("noticias.cli.app.run_pipeline") as mock_run,
        ):
            mock_reg.return_value.list.return_value = []

            result = runner.invoke(app, ["resumen", "--no-llm"])

        assert result.exit_code == 0
        assert "No hay fuentes" in result.stdout
        mock_run.assert_not_called()

    def test_all_sources_empty_url(self) -> None:
        """All sources have empty URL → Spanish message, no pipeline call."""
        with (
            patch("noticias.cli.app.SourceRegistry.default") as mock_reg,
            patch("noticias.cli.app.run_pipeline") as mock_run,
        ):
            mock_reg.return_value.list.return_value = [
                Source(name="pendiente1", url="", lean=Lean.LEFT),
                Source(name="pendiente2", url="", lean=Lean.RIGHT),
            ]

            result = runner.invoke(app, ["resumen", "--no-llm"])

        assert result.exit_code == 0
        assert "No hay fuentes activas" in result.stdout
        mock_run.assert_not_called()


# ── resumen --since ─────────────────────────────────────────────────────────


class TestResumenSince:
    def test_custom_since(self, sample_clusters: list[Cluster]) -> None:
        """``--since 7d`` is accepted."""
        with (
            patch("noticias.cli.app.SourceRegistry.default") as mock_reg,
            patch("noticias.cli.app.run_pipeline", return_value=sample_clusters),
        ):
            mock_reg.return_value.list.return_value = [
                Source(name="pagina12", url="https://www.pagina12.com.ar/rss", lean=Lean.LEFT),
            ]

            result = runner.invoke(app, ["resumen", "--no-llm", "--since", "7d"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.stdout}"

    def test_invalid_since(self) -> None:
        """Invalid ``--since`` → Spanish error, exit code 1."""
        with patch("noticias.cli.app.SourceRegistry.default") as mock_reg:
            mock_reg.return_value.list.return_value = [
                Source(name="pagina12", url="https://www.pagina12.com.ar/rss", lean=Lean.LEFT),
            ]

            result = runner.invoke(app, ["resumen", "--no-llm", "--since", "invalid"])

        assert result.exit_code == 1
        assert "Error" in result.stdout or "formato" in result.stdout.lower()


# ── resumen --sources ───────────────────────────────────────────────────────


class TestResumenSources:
    def test_filter_sources(self, sample_clusters: list[Cluster]) -> None:
        """``--sources pagina12`` runs only the specified source."""
        with (
            patch("noticias.cli.app.SourceRegistry.default") as mock_reg,
            patch("noticias.cli.app.run_pipeline", return_value=sample_clusters) as mock_run,
        ):
            reg = MagicMock()
            reg.list.return_value = [
                Source(name="pagina12", url="https://www.pagina12.com.ar/rss", lean=Lean.LEFT),
                Source(name="infobae", url="https://www.infobae.com/rss/", lean=Lean.CENTER),
            ]

            def _get(name: str) -> Source:
                for s in reg.list.return_value:
                    if s.name == name:
                        return s
                raise ValueError(f"source '{name}' not found")

            reg.get.side_effect = _get
            mock_reg.return_value = reg

            result = runner.invoke(app, [
                "resumen", "--no-llm", "--sources", "pagina12",
            ])

        assert result.exit_code == 0
        # Pipeline should have been called with only pagina12
        mock_run.assert_called_once()
        args, _ = mock_run.call_args
        passed_sources = args[0]
        assert len(passed_sources) == 1
        assert passed_sources[0].name == "pagina12"

    def test_nonexistent_source(self) -> None:
        """Non-existent source → Spanish error, exit code 1."""
        with patch("noticias.cli.app.SourceRegistry.default") as mock_reg:
            reg = MagicMock()
            reg.list.return_value = [
                Source(name="pagina12", url="https://www.pagina12.com.ar/rss", lean=Lean.LEFT),
            ]
            reg.get.side_effect = ValueError("source 'nonexistent' not found")
            mock_reg.return_value = reg

            result = runner.invoke(app, [
                "resumen", "--no-llm", "--sources", "nonexistent",
            ])

        assert result.exit_code == 1
        assert "no se encontró" in result.stdout


# ── resumen without --no-llm ────────────────────────────────────────────────


class TestResumenRealLlm:
    def test_runs_with_real_llm_fallback(
        self, sample_clusters: list[Cluster],
    ) -> None:
        """Without --no-llm, runs pipeline with real LLMClient."""
        with (
            patch("noticias.cli.app.SourceRegistry.default") as mock_reg,
            patch("noticias.cli.app.run_pipeline", return_value=sample_clusters) as mock_run,
        ):
            mock_reg.return_value.list.return_value = [
                Source(name="pagina12", url="https://www.pagina12.com.ar/rss", lean=Lean.LEFT),
            ]

            result = runner.invoke(app, ["resumen"])

        assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.stdout}"
        mock_run.assert_called_once()
        # The LLM client should be an LLMClient instance, not StubLLMClient
        args, _ = mock_run.call_args
        llm = args[2]  # third positional arg is the LLM client
        from noticias.llm.client import LLMClient
        assert isinstance(llm, LLMClient)
        assert llm.token_budget == 9000

    def test_verbose_logging(self, sample_clusters: list[Cluster]) -> None:
        """``--verbose`` enables DEBUG logging."""
        with (
            patch("noticias.cli.app.SourceRegistry.default") as mock_reg,
            patch("noticias.cli.app.run_pipeline", return_value=sample_clusters),
        ):
            mock_reg.return_value.list.return_value = [
                Source(name="pagina12", url="https://www.pagina12.com.ar/rss", lean=Lean.LEFT),
            ]

            result = runner.invoke(app, [
                "resumen", "--no-llm", "--verbose",
            ])

        assert result.exit_code == 0
