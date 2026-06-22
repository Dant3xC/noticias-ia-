"""Component tests for `noticias fuentes add` and `noticias fuentes remove`.

Uses Typer's CliRunner with mocked SourceRegistry.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from noticias.cli.app import app
from noticias.models.source import Lean, Source
from noticias.sources.registry import SourceRegistry

runner = CliRunner()


@pytest.fixture
def registry_with_sources() -> SourceRegistry:
    """A registry with a pre-existing source for remove/duplicate tests."""
    reg = SourceRegistry()
    reg.add(Source(name="pagina12", url="https://www.pagina12.com.ar/rss/portada", lean=Lean.LEFT))
    reg.add(Source(name="infobae", url="https://www.infobae.com/rss/", lean=Lean.CENTER))
    return reg


# ── fuentes add ────────────────────────────────────────────────────────────


class TestFuentesAdd:
    def test_add_valid_source(self) -> None:
        reg = SourceRegistry()
        with patch("noticias.cli.app.SourceRegistry.default", return_value=reg):
            result = runner.invoke(app, [
                "fuentes", "add", "clarin",
                "https://www.clarin.com/rss/lo-mas-visto/",
                "--lean", "right",
            ])

        assert result.exit_code == 0
        assert "agregada" in result.stdout
        # Registry should now have 1 source
        assert len(reg.list()) == 1
        assert reg.get("clarin").lean == Lean.RIGHT

    def test_add_invalid_url_scheme(self) -> None:
        reg = SourceRegistry()
        with patch("noticias.cli.app.SourceRegistry.default", return_value=reg):
            result = runner.invoke(app, [
                "fuentes", "add", "bad",
                "ftp://example.com/rss",
                "--lean", "center",
            ])

        assert result.exit_code == 1
        assert "http" in result.stdout.lower() or "Error" in result.stdout
        assert len(reg.list()) == 0  # nothing persisted

    def test_add_invalid_lean(self) -> None:
        reg = SourceRegistry()
        with patch("noticias.cli.app.SourceRegistry.default", return_value=reg):
            result = runner.invoke(app, [
                "fuentes", "add", "test",
                "https://example.com/rss",
                "--lean", "farleft",
            ])

        assert result.exit_code == 1
        assert "lean" in result.stdout.lower() or "Error" in result.stdout
        assert len(reg.list()) == 0

    def test_add_duplicate_name(self, registry_with_sources: SourceRegistry) -> None:
        with patch("noticias.cli.app.SourceRegistry.default", return_value=registry_with_sources):
            result = runner.invoke(app, [
                "fuentes", "add", "pagina12",
                "https://www.pagina12.com.ar/rss/portada",
                "--lean", "left",
            ])

        assert result.exit_code == 1
        assert "ya existe" in result.stdout


# ── fuentes remove ─────────────────────────────────────────────────────────


class TestFuentesRemove:
    def test_remove_existing(self, registry_with_sources: SourceRegistry) -> None:
        with patch("noticias.cli.app.SourceRegistry.default", return_value=registry_with_sources):
            result = runner.invoke(app, ["fuentes", "remove", "pagina12"])

        assert result.exit_code == 0
        assert "quitada" in result.stdout
        assert len(registry_with_sources.list()) == 1

    def test_remove_not_found(self, registry_with_sources: SourceRegistry) -> None:
        with patch("noticias.cli.app.SourceRegistry.default", return_value=registry_with_sources):
            result = runner.invoke(app, ["fuentes", "remove", "nonexistent"])

        assert result.exit_code == 1
        assert "no se encontró" in result.stdout
        assert len(registry_with_sources.list()) == 2  # unchanged
