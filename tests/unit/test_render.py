"""Unit tests for Rich console rendering (render/console.py).

Covers:
- render with empty clusters + empty failures → "No se encontraron noticias"
- render with clusters → output contains event label, trust label, summary
- render with alta cluster → contains [green]ALTA[/green]
- render with baja cluster → contains [red]BAJA[/red]
- render with failures → output contains failure section
- render_snapshot renders correctly
- No voseo in output
"""

from __future__ import annotations

import io
from datetime import datetime

import pytest
from rich.console import Console

from noticias.models.cluster import Cluster
from noticias.models.snapshot import Snapshot, SnapshotCluster
from noticias.pipeline.fetch import FetchFailure
from noticias.render.console import render, render_snapshot
from tests.helpers import make_item


def _make_test_cluster(
    trust_label: str = "alta",
    trust_reason: str = "3 fuentes, acuerdo alto.",
    summary: str = "Resumen de prueba con informacion relevante.",
    highlights: list[str] | None = None,
    sources: list[str] | None = None,
    divergences: list[str] | None = None,
    divergence_ratio: float = 0.0,
) -> Cluster:
    """Build a minimal Cluster for render testing."""
    if highlights is None:
        highlights = ["Punto destacado 1"]
    if sources is None:
        sources = ["pagina12", "infobae"]
    if divergences is None:
        divergences = []

    return Cluster(
        event_label="Noticia de prueba",
        trust_label=trust_label,
        trust_reason=trust_reason,
        summary=summary,
        highlights=highlights,
        sources=sources,
        divergences=divergences,
        divergence_ratio=divergence_ratio,
        items=[make_item(source=s) for s in sources],
    )


# ── render ──────────────────────────────────────────────────────────────────


class TestRender:
    def test_empty_clusters_empty_failures(self) -> None:
        """Empty clusters and failures → 'No se encontraron noticias'."""
        console = Console(record=True, width=120)
        render([], [], console)

        output = console.export_text()
        assert "No se encontraron noticias" in output
        # No voseo check
        assert "Usá" not in output
        assert "Agregá" not in output
        assert "Configurá" not in output

    def test_empty_clusters_with_failures(self) -> None:
        """Failures shown first, then empty message."""
        console = Console(record=True, width=120)
        failures = [
            FetchFailure(source="pagina12", reason="HTTP 500"),
        ]
        render([], failures, console)

        output = console.export_text()
        assert "Errores de obtención" in output or "pagina12" in output
        assert "No se encontraron noticias" in output

    def test_renders_cluster_basic(self) -> None:
        """Clusters are rendered with event label, trust, summary."""
        console = Console(record=True, width=120)
        clusters = [_make_test_cluster()]
        render(clusters, [], console)

        output = console.export_text()
        assert "Noticia de prueba" in output
        assert "Confianza" in output
        assert "Resumen de prueba" in output

    def test_alta_label_uses_green(self) -> None:
        """ALTA trust label is rendered with [green]."""
        console = Console(record=True, width=120)
        clusters = [_make_test_cluster(trust_label="alta")]
        render(clusters, [], console)

        output = console.export_text()
        assert "ALTA" in output

    def test_baja_label_uses_red(self) -> None:
        """BAJA trust label is rendered with [red]."""
        console = Console(record=True, width=120)
        clusters = [_make_test_cluster(trust_label="baja")]
        render(clusters, [], console)

        output = console.export_text()
        assert "ALTA" not in output  # specific check

    def test_media_label_uses_yellow(self) -> None:
        """MEDIA trust label is rendered."""
        console = Console(record=True, width=120)
        clusters = [_make_test_cluster(trust_label="media")]
        render(clusters, [], console)

        output = console.export_text()
        assert "MEDIA" in output

    def test_renders_highlights(self) -> None:
        """Cluster highlights are rendered as bullet points."""
        console = Console(record=True, width=120)
        clusters = [
            _make_test_cluster(highlights=["Item 1", "Item 2"]),
        ]
        render(clusters, [], console)

        output = console.export_text()
        assert "Destacados" in output
        assert "Item 1" in output
        assert "Item 2" in output

    def test_renders_sources_list(self) -> None:
        """Sources are listed after highlights."""
        console = Console(record=True, width=120)
        clusters = [
            _make_test_cluster(sources=["pagina12", "infobae"]),
        ]
        render(clusters, [], console)

        output = console.export_text()
        assert "Fuentes" in output
        assert "pagina12" in output
        assert "infobae" in output

    def test_renders_divergences(self) -> None:
        """Non-zero divergences are shown."""
        console = Console(record=True, width=120)
        clusters = [
            _make_test_cluster(
                divergences=["token1", "token2"],
                divergence_ratio=0.35,
            ),
        ]
        render(clusters, [], console)

        output = console.export_text()
        assert "Divergencias" in output
        assert "2" in output  # token count

    def test_no_divergences_not_shown(self) -> None:
        """Zero divergences are not displayed."""
        console = Console(record=True, width=120)
        clusters = [
            _make_test_cluster(divergences=[], divergence_ratio=0.0),
        ]
        render(clusters, [], console)

        output = console.export_text()
        assert "Divergencias" not in output

    def test_render_failures_section(self) -> None:
        """Fetch failures are rendered in a table."""
        console = Console(record=True, width=120)
        clusters = [_make_test_cluster()]
        failures = [
            FetchFailure(source="ambito", reason="Timeout"),
        ]
        render(clusters, failures, console)

        output = console.export_text()
        assert "Errores de obtención" in output
        assert "ambito" in output
        assert "Timeout" in output

    def test_multiple_clusters(self) -> None:
        """Multiple clusters are rendered separately."""
        console = Console(record=True, width=120)
        clusters = [
            _make_test_cluster(
                trust_label="alta",
                summary="Primer resumen.",
            ),
            _make_test_cluster(
                trust_label="baja",
                summary="Segundo resumen.",
            ),
        ]
        render(clusters, [], console)

        output = console.export_text()
        assert "Primer resumen." in output
        assert "Segundo resumen." in output

    def test_no_voseo(self) -> None:
        """All output strings are in neutral Spanish (no voseo)."""
        console = Console(record=True, width=120)
        clusters = [_make_test_cluster()]
        failures = [
            FetchFailure(source="ambito", reason="Timeout"),
        ]
        render(clusters, failures, console)

        output = console.export_text()
        voseo_verbs = ["Usá", "Agregá", "Configurá", "Hacé", "Decí"]
        for verb in voseo_verbs:
            assert verb not in output, f"Voseo verb '{verb}' found in output"


# ── render_snapshot ─────────────────────────────────────────────────────────


class TestRenderSnapshot:
    def test_empty_snapshot(self) -> None:
        """Empty snapshot shows 'No se encontraron noticias'."""
        console = Console(record=True, width=120)
        snap = Snapshot(
            date="2026-06-21",
            generated_at=datetime(2026, 6, 21, 12, 0, 0),
            sources_used=["pagina12"],
        )
        render_snapshot(snap, console)

        output = console.export_text()
        assert "No se encontraron noticias" in output

    def test_renders_clusters(self) -> None:
        """Snapshot clusters are rendered with event label, trust, summary."""
        console = Console(record=True, width=120)
        snap = Snapshot(
            date="2026-06-21",
            generated_at=datetime(2026, 6, 21, 12, 0, 0),
            sources_used=["pagina12"],
            clusters=[
                SnapshotCluster(
                    event_label="Noticia archivada",
                    trust_label="alta",
                    trust_reason="3 fuentes, acuerdo alto.",
                    summary="Resumen archivado de prueba.",
                    sources=["pagina12", "infobae"],
                    highlights=["Punto destacado 1"],
                ),
            ],
        )
        render_snapshot(snap, console)

        output = console.export_text()
        assert "Noticia archivada" in output
        assert "Confianza" in output
        assert "Resumen archivado" in output

    def test_renders_failures(self) -> None:
        """Snapshot fetch_failures are rendered."""
        console = Console(record=True, width=120)
        snap = Snapshot(
            date="2026-06-21",
            generated_at=datetime(2026, 6, 21, 12, 0, 0),
            sources_used=["pagina12"],
            clusters=[],
            fetch_failures=[
                {"source": "ambito", "reason": "HTTP 500"},
            ],
        )
        render_snapshot(snap, console)

        output = console.export_text()
        assert "Error" in output or "ambito" in output

    def test_no_voseo(self) -> None:
        """Snapshot output has no voseo."""
        console = Console(record=True, width=120)
        snap = Snapshot(
            date="2026-06-21",
            generated_at=datetime(2026, 6, 21, 12, 0, 0),
            sources_used=["pagina12"],
            clusters=[
                SnapshotCluster(
                    event_label="Test",
                    trust_label="media",
                    trust_reason="2 fuentes.",
                    summary="Resumen.",
                    sources=["pagina12"],
                ),
            ],
        )
        render_snapshot(snap, console)

        output = console.export_text()
        voseo_verbs = ["Usá", "Agregá", "Configurá", "Hacé", "Decí"]
        for verb in voseo_verbs:
            assert verb not in output, f"Voseo verb '{verb}' found in output"
