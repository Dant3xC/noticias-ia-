"""Unit tests for `noticias fuentes list` using Typer's CliRunner.

Covers:
- Empty registry → "No hay fuentes configuradas" message
- With sources → Rich table showing source names
"""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from noticias.cli.app import app
from noticias.models.source import Lean, Source
from noticias.sources.registry import SourceRegistry

runner = CliRunner()


def test_fuentes_list_empty() -> None:
    """Empty registry should print the 'no sources' message."""
    empty_registry = SourceRegistry()

    # The app calls SourceRegistry.default() in the command callback
    with patch("noticias.cli.app.SourceRegistry.default", return_value=empty_registry):
        result = runner.invoke(app, ["fuentes", "list"])

    assert result.exit_code == 0
    assert "No hay fuentes configuradas" in result.stdout


def test_fuentes_list_with_sources() -> None:
    """Registry with sources should print a table containing their names."""
    reg = SourceRegistry()
    reg.add(Source(name="pagina12", url="https://www.pagina12.com.ar/rss/portada", lean=Lean.LEFT))
    reg.add(Source(name="clarin", url="https://www.clarin.com/rss/lo-mas-visto/", lean=Lean.RIGHT))
    reg.add(Source(name="infobae", url="https://www.infobae.com/rss/", lean=Lean.CENTER))

    with patch("noticias.cli.app.SourceRegistry.default", return_value=reg):
        result = runner.invoke(app, ["fuentes", "list"])

    assert result.exit_code == 0
    assert "pagina12" in result.stdout
    assert "clarin" in result.stdout
    assert "infobae" in result.stdout
    assert "No hay fuentes configuradas" not in result.stdout
