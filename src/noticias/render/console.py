"""Rich console rendering for clusters and snapshots.

Provides two entry points:
    - ``render()``: render live ``Cluster`` objects from the pipeline.
    - ``render_snapshot()``: re-render a stored ``Snapshot`` from disk.

All user-facing output is in **neutral Spanish** (no voseo).
All docstrings are in **English** (code contract).
"""

from __future__ import annotations

from noticias.models.cluster import Cluster
from noticias.models.snapshot import Snapshot, SnapshotCluster
from noticias.pipeline.fetch import FetchFailure
from noticias.trust.label import TRUST_COLORS, TrustLabel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def render(
    clusters: list[Cluster],
    failures: list[FetchFailure],
    console: Console,
) -> None:
    """Render clusters and fetch failures to the console.

    Args:
        clusters: The list of story clusters to render.
        failures: The list of fetch failures to report.
        console: A ``rich.console.Console`` instance.
    """
    # ── No clusters, no failures ───────────────────────────────────────
    if not clusters and not failures:
        console.print(
            "[yellow]No se encontraron noticias en la ventana temporal.[/yellow]",
        )
        return

    # ── Failures only ──────────────────────────────────────────────────
    if not clusters and failures:
        _render_failures_table(failures, console)
        console.print(
            "[yellow]No se encontraron noticias en la ventana temporal.[/yellow]",
        )
        return

    # ── Render clusters ────────────────────────────────────────────────
    for cluster in clusters:
        _render_cluster(cluster, console)

    # ── Render failures section if any ─────────────────────────────────
    if failures:
        _render_failures_table(failures, console)


def render_snapshot(snapshot: Snapshot, console: Console) -> None:
    """Re-render a stored snapshot — same visual output as ``render()``.

    Args:
        snapshot: The snapshot to render.
        console: A ``rich.console.Console`` instance.
    """
    if not snapshot.clusters and not snapshot.fetch_failures:
        console.print(
            "[yellow]No se encontraron noticias en la ventana temporal.[/yellow]",
        )
        return

    for sc in snapshot.clusters:
        _render_snapshot_cluster(sc, console)

    if snapshot.fetch_failures:
        _render_failures_from_dict(snapshot.fetch_failures, console)


# ── Internal helpers ──────────────────────────────────────────────────────


def _trust_color(label: str) -> str:
    """Map a trust label string to a Rich colour name.

    Args:
        label: One of ``"alta"``, ``"media"``, ``"baja"``, or empty.

    Returns:
        A Rich colour name (``"green"``, ``"yellow"``, ``"red"``,
        or ``"white"`` for unknown/empty).
    """
    try:
        return TRUST_COLORS.get(TrustLabel(label), "white")
    except ValueError:
        return "white"


def _render_cluster(cluster: Cluster, console: Console) -> None:
    """Render a single ``Cluster`` as a Rich Panel."""
    color = _trust_color(cluster.trust_label)
    badge = f"[{color}]{cluster.trust_label.upper()}[/{color}]"

    lines: list[str] = []
    lines.append(f"[bold]Confianza:[/bold] {badge}")
    if cluster.trust_reason:
        lines.append(f"[dim]{cluster.trust_reason}[/dim]")
    lines.append("")

    if cluster.summary:
        lines.append(cluster.summary)
        lines.append("")

    if cluster.highlights:
        lines.append("[bold]Destacados:[/bold]")
        for h in cluster.highlights:
            lines.append(f"  • {h}")
        lines.append("")

    if cluster.sources:
        sources_str = ", ".join(cluster.sources)
        lines.append(f"[dim]Fuentes: {sources_str}[/dim]")

    if cluster.divergence_ratio > 0 and cluster.divergences:
        lines.append(
            f"[yellow]Divergencias: {len(cluster.divergences)} tokens[/yellow]",
        )

    panel = Panel(
        "\n".join(lines).strip(),
        title=f"[bold]{cluster.event_label}[/bold]",
        border_style=color,
    )
    console.print(panel)


def _render_snapshot_cluster(sc: SnapshotCluster, console: Console) -> None:
    """Render a single ``SnapshotCluster`` as a Rich Panel."""
    color = _trust_color(sc.trust_label)
    badge = f"[{color}]{sc.trust_label.upper()}[/{color}]"

    lines: list[str] = []
    lines.append(f"[bold]Confianza:[/bold] {badge}")
    if sc.trust_reason:
        lines.append(f"[dim]{sc.trust_reason}[/dim]")
    lines.append("")

    if sc.summary:
        lines.append(sc.summary)
        lines.append("")

    if sc.highlights:
        lines.append("[bold]Destacados:[/bold]")
        for h in sc.highlights:
            lines.append(f"  • {h}")
        lines.append("")

    if sc.sources:
        sources_str = ", ".join(sc.sources)
        lines.append(f"[dim]Fuentes: {sources_str}[/dim]")

    panel = Panel(
        "\n".join(lines).strip(),
        title=f"[bold]{sc.event_label}[/bold]",
        border_style=color,
    )
    console.print(panel)


def _render_failures_table(failures: list[FetchFailure], console: Console) -> None:
    """Render fetch failures as a Rich table."""
    table = Table(title="Errores de obtención")
    table.add_column("Fuente", style="red")
    table.add_column("Motivo", style="yellow")

    for f in failures:
        table.add_row(f.source, f.reason)

    console.print(table)


def _render_failures_from_dict(failures: list[dict], console: Console) -> None:
    """Render fetch failures stored as dicts (from snapshot deserialisation)."""
    table = Table(title="Errores de obtención")
    table.add_column("Fuente", style="red")
    table.add_column("Motivo", style="yellow")

    for f in failures:
        source = f.get("source", "?")
        reason = f.get("reason", "?")
        table.add_row(source, reason)

    console.print(table)
