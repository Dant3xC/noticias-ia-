"""Typer CLI application entry point.

PR2: adds ``fuentes add``, ``fuentes remove``, and ``health`` subcommands
on top of the PR1 foundation (``--version``, ``fuentes list``).
PR4: adds ``resumen`` command and ``snapshot`` subcommands.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from noticias import __version__
from noticias.cli.health import health as _health_command
from noticias.llm.client import LLMClient, StubLLMClient
from noticias.models.snapshot import Snapshot, SnapshotCluster
from noticias.models.source import SourceConfig
from noticias.persistence.snapshot import (
    list_snapshots,
    read_snapshot,
    write_snapshot,
)
from noticias.pipeline.orchestrator import run_pipeline
from noticias.pipeline.window import parse_since
from noticias.render.console import render, render_snapshot
from noticias.sources.registry import SourceRegistry

logger = logging.getLogger(__name__)

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


# ── resumen ────────────────────────────────────────────────────────────────


@app.command(
    "resumen",
    help="Ejecutar el pipeline y obtener el resumen del día.",
)
def resumen_command(
    since: str = typer.Option(
        "24h",
        "--since",
        help="Ventana temporal (ej: 24h, 7d, 30m)",
    ),
    sources: str = typer.Option(
        None,
        "--sources",
        help="Nombres de fuentes separados por coma (default: todas)",
    ),
    no_llm: bool = typer.Option(
        False,
        "--no-llm",
        help="Saltar el LLM y usar resúmenes plantilla",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Activar logging DEBUG",
    ),
) -> None:
    """Run the full pipeline and persist + render the daily summary.

    All user-facing output is in neutral Spanish (no voseo).
    """
    console = Console()

    # ── Logging setup ──────────────────────────────────────────────────
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # ── Load sources ───────────────────────────────────────────────────
    registry = SourceRegistry.default()
    all_sources = registry.list()

    if not all_sources:
        console.print(
            "[yellow]No hay fuentes configuradas. "
            "Agregue al menos una con `noticias fuentes add`.[/yellow]",
        )
        raise typer.Exit(code=0)

    # ── Parse --since ───────────────────────────────────────────────────
    try:
        window = parse_since(since)
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1)

    # ── Filter sources by name ─────────────────────────────────────────
    source_names: list[str] | None = None
    if sources:
        source_names = [s.strip() for s in sources.split(",") if s.strip()]

    if source_names:
        selected: list = []
        for name in source_names:
            try:
                selected.append(registry.get(name))
            except ValueError:
                console.print(
                    f"[red]Error: no se encontró una fuente llamada "
                    f"'{name}'.[/red]",
                )
                raise typer.Exit(code=1)
        all_sources = selected

    # ── Skip sources with empty URL (placeholders) ─────────────────────
    active_sources = [s for s in all_sources if s.url and s.url.strip()]

    if not active_sources:
        console.print(
            "[yellow]No hay fuentes activas. "
            "Agregue al menos una con `noticias fuentes add`.[/yellow]",
        )
        raise typer.Exit(code=0)

    # ── Build LLM client ───────────────────────────────────────────────
    config = SourceConfig()
    if no_llm:
        llm: LLMClient = StubLLMClient()
    else:
        llm = LLMClient(model=config.model, token_budget=config.token_budget)

    # ── Run pipeline ───────────────────────────────────────────────────
    clusters = run_pipeline(active_sources, window, llm, config)

    # ── Build snapshot ─────────────────────────────────────────────────
    local_date_str = datetime.now().strftime("%Y-%m-%d")
    snapshot_clusters = [
        SnapshotCluster(
            event_label=c.event_label,
            trust_label=c.trust_label,
            trust_reason=c.trust_reason,
            summary=c.summary,
            sources=c.sources,
            highlights=c.highlights,
        )
        for c in clusters
    ]
    snapshot = Snapshot(
        date=local_date_str,
        generated_at=datetime.now(),
        sources_used=[s.name for s in active_sources],
        clusters=snapshot_clusters,
        fetch_failures=[],  # not available from orchestrator return
    )

    # ── Persist ────────────────────────────────────────────────────────
    data_dir = Path.cwd() / ".data"
    written = write_snapshot(snapshot, data_dir)
    console.print(f"[dim]Instantánea guardada en: {written}[/dim]")
    console.print("")

    # ── Render ─────────────────────────────────────────────────────────
    render(clusters, [], console)


# ── snapshot subcommands ───────────────────────────────────────────────────


snapshot_app = typer.Typer(
    name="snapshot",
    help="Administrar las instantáneas diarias guardadas.",
)
app.add_typer(snapshot_app)


@snapshot_app.command("list", help="Listar todas las instantáneas guardadas.")
def snapshot_list_command() -> None:
    """List all saved daily snapshots in a Rich table, newest first."""
    console = Console()
    data_dir = Path.cwd() / ".data"
    files = list_snapshots(data_dir)

    if not files:
        console.print(
            "[yellow]No hay instantáneas todavía. "
            "Ejecute `noticias resumen` para crear la primera.[/yellow]",
        )
        raise typer.Exit(code=0)

    table = Table(title="Instantáneas guardadas")
    table.add_column("Archivo", style="cyan")
    table.add_column("Fecha", style="white")
    table.add_column("Grupos", style="magenta")
    table.add_column("Generado", style="dim")

    for f in files:
        try:
            snap = read_snapshot(f)
        except Exception:  # noqa: BLE001
            # Skip files that can't be read as snapshots
            continue

        date_part = snap.date
        generated_str = snap.generated_at.strftime("%Y-%m-%d %H:%M:%S")
        table.add_row(
            f.name,
            date_part,
            str(len(snap.clusters)),
            generated_str,
        )

    console.print(table)


@snapshot_app.command("show", help="Mostrar una instantánea guardada.")
def snapshot_show_command(
    file: str = typer.Argument(
        help="Nombre o ruta del archivo de instantánea "
        "(ej: 2026-06-21.json o ruta completa)",
    ),
) -> None:
    """Re-render a stored snapshot via the Rich renderer.

    Accepts a basename (looked up in ``.data/``) or a full path.  Path
    traversal outside ``.data/`` is rejected.
    """
    console = Console()
    data_dir = Path.cwd() / ".data"

    # Determine path: basename → look in .data/
    path = Path(file)
    if not path.is_absolute() and path.parent == Path(""):
        path = data_dir / file

    # Resolve for traversal check.
    try:
        resolved = path.resolve()
    except OSError:
        console.print(f"[red]Error: la ruta '{file}' no es válida.[/red]")
        raise typer.Exit(code=1)

    # Path traversal protection.
    try:
        data_resolved = data_dir.resolve()
    except OSError:
        console.print("[red]Error: no se puede acceder al directorio .data/.[/red]")
        raise typer.Exit(code=1)

    if data_resolved not in resolved.parents and resolved.parent != data_resolved:
        console.print(
            f"[red]Error: la ruta '{file}' está fuera del "
            f"directorio .data/.[/red]",
        )
        raise typer.Exit(code=1)

    if not resolved.exists():
        console.print(
            f"[red]Error: no se encontró el archivo '{resolved.name}' "
            f"en .data/.[/red]",
        )
        raise typer.Exit(code=1)

    # Read and render.
    try:
        snapshot = read_snapshot(resolved)
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1)
    except FileNotFoundError:
        console.print(
            f"[red]Error: no se encontró el archivo "
            f"'{resolved.name}'.[/red]",
        )
        raise typer.Exit(code=1)

    render_snapshot(snapshot, console)
