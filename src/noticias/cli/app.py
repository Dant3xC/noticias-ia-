"""Typer CLI application entry point.

PR1: minimal app with `--version`, `fuentes list`. More subcommands
(resumen, fuentes add/remove, health, snapshot) are added in later PRs.
"""

from __future__ import annotations

import typer

from noticias import __version__
from noticias.sources.registry import SourceRegistry

app = typer.Typer(
    name="noticias",
    help="Personal CLI news aggregator for Argentinian RSS sources",
    rich_markup_mode="rich",
)

fuentes_app = typer.Typer(name="fuentes", help="Manage news sources")
app.add_typer(fuentes_app)


def _version_callback(show_version: bool = False) -> None:
    if show_version:
        typer.echo(f"noticias-ia {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@fuentes_app.command("list")
def fuentes_list_command() -> None:
    """List all configured news sources."""
    registry = SourceRegistry.default()
    from noticias.cli.fuentes import fuentes_list as _fuentes_list

    _fuentes_list(registry)
