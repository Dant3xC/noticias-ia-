"""Unit tests for story clustering (pipeline/cluster.py).

Covers:
- Title-similarity clustering (>0.55)
- Body token overlap clustering
- URL / domain + slug matching (>0.40)
- No-match → single-item clusters
- Single-item input
- Identical titles with different bodies
- Multiple items from same source
- Empty list
"""

from __future__ import annotations

from noticias.pipeline.cluster import cluster
from tests.helpers import make_item


class TestCluster:

    def test_single_item_single_cluster(self) -> None:
        items = [make_item("Solo story")]
        result = cluster(items)
        assert len(result) == 1
        assert len(result[0].items) == 1

    def test_title_similarity_clusters(self) -> None:
        """Three items with similar titles should form one cluster."""
        items = [
            make_item(
                "Gobierno anuncia nuevo plan economico nacional para Argentina",
                url="https://a.com/1",
                source="a",
            ),
            make_item(
                "Gobierno anuncia nuevo plan economico nacional en Argentina",
                url="https://b.com/2",
                source="b",
            ),
            make_item(
                "Gobierno anuncia nuevo plan economico nacional desde Argentina",
                url="https://c.com/3",
                source="c",
            ),
        ]
        result = cluster(items)
        assert len(result) == 1
        assert len(result[0].items) == 3
        assert len(result[0].sources) == 3

    def test_no_cluster_independent_stories(self) -> None:
        """Unrelated stories should each form their own cluster."""
        items = [
            make_item(
                "El gobierno anunció un nuevo plan económico",
                url="https://a.com/1",
                source="a",
                body="a",
            ),
            make_item(
                "La selección argentina ganó el partido inaugural",
                url="https://b.com/2",
                source="b",
                body="b",
            ),
            make_item(
                "Nuevo récord de temperatura en la Antártida",
                url="https://c.com/3",
                source="c",
                body="c",
            ),
        ]
        result = cluster(items)
        assert len(result) == 3
        for c in result:
            assert len(c.items) == 1

    def test_same_domain_and_slug_clusters(self) -> None:
        """Items on same domain with overlapping slugs should cluster."""
        items = [
            make_item(
                "Título A diferente",
                url="https://ejemplo.com/politica/jubilaciones-nuevas-medidas",
                source="a",
            ),
            make_item(
                "Título B diferente",
                url="https://ejemplo.com/politica/jubilaciones-reforma",
                source="b",
            ),
        ]
        result = cluster(items)
        assert len(result) == 1
        assert len(result[0].items) == 2

    def test_identical_titles_different_bodies(self) -> None:
        """Same title from different sources → cluster (title threshold exceeded)."""
        items = [
            make_item("Corte Suprema falla a favor de la libertad de expresión", source="a",
                       url="https://a.com/story"),
            make_item("Corte Suprema falla a favor de la libertad de expresión", source="b",
                       url="https://b.com/story"),
        ]
        result = cluster(items)
        assert len(result) == 1
        assert len(result[0].items) == 2

    def test_multiple_items_from_same_source(self) -> None:
        """Multiple items from the same source form separate clusters if unrelated."""
        items = [
            make_item("Economic policy announced today", source="pagina12", url="https://p12.com/a",
                       body="a"),
            make_item("Sports championship final results", source="pagina12", url="https://p12.com/b",
                       body="b"),
            make_item("Weather forecast for the week ahead", source="infobae", url="https://infobae.com/c",
                       body="c"),
        ]
        result = cluster(items)
        # Three unrelated stories → 3 clusters
        assert len(result) == 3

    def test_chain_clustering(self) -> None:
        """A matches B, B matches C → all three cluster together."""
        items = [
            make_item("El gobierno anuncia medidas economicas nacionales", source="a", url="https://a.com/1"),
            make_item("Gobierno anuncia medidas economicas en todo el pais", source="b", url="https://b.com/2"),
            make_item("El gobierno anuncia medidas economicas importantes hoy", source="c", url="https://c.com/3"),
        ]
        result = cluster(items)
        assert len(result) == 1
        assert len(result[0].items) == 3

    def test_body_token_overlap_clusters(self) -> None:
        """Items with different titles but high body token overlap should cluster.

        With the calibrated body Jaccard threshold of 0.50, the two bodies
        need substantial token overlap (above 50%) to cluster via body
        signal. These two bodies are near-paraphrases of the same news
        event — they share the core vocabulary (presidente, plan, economico,
        nacional, reformas, fiscales, laborales, economia) plus context.
        """
        items = [
            make_item(
                "Gobierno presenta nuevo plan economico nacional",
                url="https://fuente-a.com/articulo-1",
                source="a",
                body=(
                    "El presidente anuncio hoy un nuevo plan economico nacional "
                    "que incluye reformas fiscales y laborales importantes "
                    "para reactivar la economia del pais y mejorar las condiciones "
                    "de los trabajadores"
                ),
            ),
            make_item(
                "Congreso debatira nuevo plan economico del gobierno",
                url="https://fuente-b.com/articulo-2",
                source="b",
                body=(
                    "El presidente anuncio hoy un nuevo plan economico nacional "
                    "que incluye reformas fiscales y laborales para reactivar "
                    "la economia del pais y mejorar la situacion de los trabajadores"
                ),
            ),
        ]
        result = cluster(items)
        assert len(result) == 1
        assert len(result[0].items) == 2
        assert len(result[0].sources) == 2

    def test_title_threshold_lowered_to_0_55(self) -> None:
        """Titles with ratio > 0.65 should cluster."""
        items = [
            make_item(
                "Anuncian plan economico en el congreso nacional hoy",
                url="https://a.com/articulo-1",
                source="a",
                body="Texto unico para el primer articulo economico",
            ),
            make_item(
                "Anuncian plan economico en el congreso nacional ayer",
                url="https://b.com/articulo-2",
                source="b",
                body="Texto completamente diferente para el segundo articulo",
            ),
        ]
        result = cluster(items)
        assert len(result) == 1
        assert len(result[0].items) == 2

    def test_title_threshold_calibrated_to_0_65_rejects_lower(self) -> None:
        """Titles with ratio ~0.59 should NOT cluster (between old 0.55 and new 0.65).

        This is the calibration guard against over-aggregation. The pair
        "Argentina recibira millonaria inversion extranjera" / "Millonaria
        inversion extranjera llega a la Argentina" gives a measured
        title ratio of 0.588 — above the old 0.55 threshold (would have
        clustered) but below the new 0.65 threshold (must not cluster).
        """
        items = [
            make_item(
                "Argentina recibira millonaria inversion extranjera",
                url="https://a.com/articulo-1",
                source="a",
                body=(
                    "El gobierno anuncio que una empresa extranjera invertira "
                    "mil millones de dolares en el pais durante el proximo ano"
                ),
            ),
            make_item(
                "Millonaria inversion extranjera llega a la Argentina",
                url="https://b.com/articulo-2",
                source="b",
                body=(
                    "Una compania internacional anuncio una inversion de "
                    "mil millones de dolares para construir una nueva planta "
                    "en la provincia de buenos aires"
                ),
            ),
        ]
        result = cluster(items)
        # Measured title ratio: 0.588. Above 0.55, below 0.65.
        # Body Jaccard: low (different vocabulary, different focus).
        assert len(result) == 2, (
            f"Expected 2 clusters (calibration guard), got {len(result)}: "
            f"thresholds may be over-aggregating"
        )

    def test_body_jaccard_threshold_calibrated_to_0_5_rejects_lower(self) -> None:
        """Body Jaccard ~0.43 should NOT cluster when title signal doesn't fire.

        The measured Jaccard for the two bodies below is 0.429 — above the
        old 0.3 threshold (would have clustered) but below the new 0.5
        threshold (must not cluster). The titles are deliberately
        dissimilar (low rapidfuzz ratio) so the title signal does not
        fire and the body Jaccard is the only candidate signal.
        """
        items = [
            make_item(
                "Informacion importante del dia",
                url="https://a.com/articulo-1",
                source="a",
                body=(
                    "El gobierno argentino anuncio hoy nuevas medidas economicas "
                    "para hacer frente a la crisis que afecta al pais"
                ),
            ),
            make_item(
                "Anuncio relevante para los ciudadanos",
                url="https://b.com/articulo-2",
                source="b",
                body=(
                    "El presidente anuncio que el gobierno tomara nuevas medidas "
                    "frente a la crisis"
                ),
            ),
        ]
        result = cluster(items)
        # Title ratio: low (deliberately different vocab)
        # Body Jaccard: measured 0.429 (above old 0.3, below new 0.5)
        # URLs: different domains, so slug signal does not fire
        assert len(result) == 2, (
            f"Expected 2 clusters (calibration guard), got {len(result)}: "
            f"body Jaccard threshold may be over-aggregating"
        )

    def test_slug_threshold_lowered_to_0_4(self) -> None:
        """Same-domain items with high slug overlap should cluster."""
        items = [
            make_item(
                "Reforma del sistema de jubilaciones",
                url="https://ejemplo.com/politica/reforma-jubilaciones-2026",
                source="a",
                body="Contenido sobre reforma del sistema previsional",
            ),
            make_item(
                "Nueva reforma del sistema de jubilaciones",
                url="https://ejemplo.com/politica/reforma-jubilaciones-aprobada",
                source="b",
                body="Texto diferente sobre la nueva reforma aprobada",
            ),
        ]
        result = cluster(items)
        assert len(result) == 1
        assert len(result[0].items) == 2
