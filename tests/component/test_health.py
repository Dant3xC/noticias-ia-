"""Component tests for `noticias health` command.

Uses Typer's CliRunner with mocked SourceRegistry and respx for HTTP mocking.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import respx
from httpx import Response
from typer.testing import CliRunner

from noticias.cli.app import app
from noticias.models.source import Lean, Source
from noticias.sources.registry import SourceRegistry

runner = CliRunner()


@pytest.fixture
def registry_with_sources() -> SourceRegistry:
    """A registry with 3 sources: two with URLs, one empty."""
    reg = SourceRegistry()
    reg.add(Source(name="pagina12", url="https://www.pagina12.com.ar/rss/portada", lean=Lean.LEFT))
    reg.add(Source(name="infobae", url="https://www.infobae.com/rss/", lean=Lean.CENTER))
    reg.add(Source(name="laizquierdadiario", url="", lean=Lean.LEFT))
    return reg


class TestHealth:
    def test_ok_and_pending(self, registry_with_sources: SourceRegistry) -> None:
        """Two OK sources, one pending (empty URL)."""
        with patch("noticias.cli.app.SourceRegistry.default", return_value=registry_with_sources):
            with respx.mock:
                respx.head("https://www.pagina12.com.ar/rss/portada").mock(
                    return_value=Response(200),
                )
                respx.head("https://www.infobae.com/rss/").mock(
                    return_value=Response(200),
                )

                result = runner.invoke(app, ["health"])

        assert result.exit_code == 0
        assert "OK" in result.stdout
        # Rich table truncates long values — check partial matches.
        assert "Pendi" in result.stdout
        assert "laizq" in result.stdout  # "laizquierdadiario" truncated

    def test_error_status(self, registry_with_sources: SourceRegistry) -> None:
        """One source returns an error; other sources must be mocked too."""
        with patch("noticias.cli.app.SourceRegistry.default", return_value=registry_with_sources):
            with respx.mock:
                respx.head("https://www.pagina12.com.ar/rss/portada").mock(
                    return_value=Response(500),
                )
                respx.head("https://www.infobae.com/rss/").mock(
                    return_value=Response(200),
                )

                result = runner.invoke(app, ["health"])

        assert result.exit_code == 0
        assert "Error" in result.stdout

    def test_empty_registry(self) -> None:
        """No sources → message about no configured sources."""
        empty_registry = SourceRegistry()
        with patch("noticias.cli.app.SourceRegistry.default", return_value=empty_registry):
            result = runner.invoke(app, ["health"])

        assert result.exit_code == 0
        assert "No hay fuentes configuradas" in result.stdout
