"""CLI logic for `noticias fuentes` subcommands.

Provides ``list``, ``add``, and ``remove`` operations backed by
``SourceRegistry``.  CLI strings are in neutral Spanish (per PR1 i18n
convention); docstrings are in English (code contract).
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import typer
from rich.console import Console
from rich.table import Table

from noticias.models.source import Lean, Source
from noticias.sources.registry import SourceRegistry

_CONFIG_PATH = Path.home() / ".config" / "noticias" / "config.json"


def _save(registry: SourceRegistry) -> None:
    """Persist the registry to the default config path."""
    registry.save(_CONFIG_PATH)


def fuentes_list(registry: SourceRegistry) -> None:
    """Print the list of configured sources or an empty-state message."""
    console = Console()
    sources = registry.list()

    if not sources:
        console.print(
            "[yellow]No hay fuentes configuradas. "
            "Use `noticias fuentes add` para agregar una.[/yellow]",
        )
        return

    table = Table(title="Fuentes configuradas")
    table.add_column("Nombre", style="cyan")
    table.add_column("URL", style="green")
    table.add_column("Lean", style="magenta")
    table.add_column("Estado", style="white")

    for source in sources:
        table.add_row(
            source.name,
            source.url or "[dim]pendiente[/dim]",
            source.lean.value,
            source.last_fetched_status,
        )

    console.print(table)


def fuentes_add(
    registry: SourceRegistry,
    name: str,
    url: str,
    lean: str,
) -> None:
    """Add a new news source and persist the registry.

    Args:
        registry: The source registry.
        name: Source name (must be unique).
        url: RSS feed URL.
        lean: Ideological lean (left/center/right).

    Exits with code 1 on validation failure; prints Spanish error messages.
    """
    console = Console()

    # Validate URL scheme.
    try:
        parsed = urlparse(url)
    except Exception:
        console.print("[red]Error: la URL no es válida.[/red]")
        raise typer.Exit(code=1)

    if parsed.scheme not in ("http", "https"):
        console.print(
            "[red]Error: la URL debe comenzar con http:// o https://.[/red]",
        )
        raise typer.Exit(code=1)

    if not parsed.netloc:
        console.print("[red]Error: la URL no es válida.[/red]")
        raise typer.Exit(code=1)

    # Validate lean.
    try:
        lean_enum = Lean(lean)
    except ValueError:
        console.print(
            "[red]Error: el lean debe ser 'left', 'center' o 'right'.[/red]",
        )
        raise typer.Exit(code=1)

    # Add source (registry validates duplicate name).
    source = Source(name=name, url=url, lean=lean_enum)
    try:
        registry.add(source)
    except ValueError:
        console.print(
            f"[red]Error: ya existe una fuente llamada '{name}'.[/red]",
        )
        raise typer.Exit(code=1)

    _save(registry)
    console.print(f"[green]Fuente '{name}' agregada.[/green]")


def fuentes_remove(registry: SourceRegistry, name: str) -> None:
    """Remove a news source by name and persist the registry.

    Args:
        registry: The source registry.
        name: Source name to remove.

    Exits with code 1 if the source is not found.
    """
    console = Console()

    try:
        registry.remove(name)
    except ValueError:
        console.print(
            f"[red]Error: no se encontró una fuente llamada '{name}'.[/red]",
        )
        raise typer.Exit(code=1)

    _save(registry)
    console.print(f"[green]Fuente '{name}' quitada.[/green]")
