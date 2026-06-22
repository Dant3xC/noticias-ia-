"""Typer CLI application entry point.

PR2: adds ``fuentes add``, ``fuentes remove``, and ``health`` subcommands
on top of the PR1 foundation (``--version``, ``fuentes list``).
"""

from __future__ import annotations

from typing import Annotated

import typer

from noticias import __version__
from noticias.cli.health import health as _health_command
from noticias.sources.registry import SourceRegistry

app = typer.Typer(
    name="noticias",
    help="Agregador CLI de noticias para fuentes RSS argentinas",
    rich_markup_mode="rich",
)

fuentes_app = typer.Typer(name="fuentes", help="Administrar las fuentes de noticias")
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
        help="Mostrar la versión y salir",
    ),
) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


# ── fuentes list ──────────────────────────────────────────────────────────


@fuentes_app.command("list", help="Listar todas las fuentes configuradas.")
def fuentes_list_command() -> None:
    """List all configured news sources."""
    registry = SourceRegistry.default()
    from noticias.cli.fuentes import fuentes_list as _fuentes_list

    _fuentes_list(registry)


# ── fuentes add ───────────────────────────────────────────────────────────


@fuentes_app.command("add", help="Agregar una nueva fuente RSS.")
def fuentes_add_command(
    name: Annotated[str, typer.Argument(help="Nombre de la fuente")],
    url: Annotated[str, typer.Argument(help="URL del feed RSS")],
    lean: Annotated[
        str,
        typer.Option("--lean", "-l", help="Línea ideológica: left, center o right"),
    ] = "center",
) -> None:
    """Add a new RSS news source."""
    registry = SourceRegistry.default()
    from noticias.cli.fuentes import fuentes_add as _fuentes_add

    _fuentes_add(registry, name, url, lean)


# ── fuentes remove ────────────────────────────────────────────────────────


@fuentes_app.command("remove", help="Quitar una fuente RSS.")
def fuentes_remove_command(
    name: Annotated[str, typer.Argument(help="Nombre de la fuente a quitar")],
) -> None:
    """Remove an existing RSS news source."""
    registry = SourceRegistry.default()
    from noticias.cli.fuentes import fuentes_remove as _fuentes_remove

    _fuentes_remove(registry, name)


# ── health ────────────────────────────────────────────────────────────────


@app.command("health", help="Verificar el estado de las fuentes configuradas.")
def health_command() -> None:
    """Check HTTP reachability of all configured sources."""
    registry = SourceRegistry.default()
    _health_command(registry)
