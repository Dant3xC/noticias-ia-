"""CLI logic for `noticias fuentes` subcommands.

PR1 implements only `fuentes list`. `fuentes add` and `fuentes remove`
are added in a later PR.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from noticias.sources.registry import SourceRegistry


def fuentes_list(registry: SourceRegistry) -> None:
    """Print the list of configured sources or an empty-state message."""
    console = Console()
    sources = registry.list()

    if not sources:
        console.print(
            "[yellow]No hay fuentes configuradas. "
            "Usá `noticias fuentes add` para agregar una.[/yellow]"
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
