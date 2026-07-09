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
            make_item("Gobierno anuncia nuevo plan economico nacional para Argentina", url="https://a.com/1", source="a"),
            make_item("Gobierno anuncia nuevo plan economico nacional en Argentina", url="https://b.com/2", source="b"),
            make_item("Gobierno anuncia nuevo plan economico nacional desde Argentina", url="https://c.com/3", source="c"),
        ]
        result = cluster(items)
        assert len(result) == 1
        assert len(result[0].items) == 3
        assert len(result[0].sources) == 3

    def test_no_cluster_independent_stories(self) -> None:
        """Unrelated stories should each form their own cluster."""
        items = [
            make_item("El gobierno anunció un nuevo plan económico", url="https://a.com/1", source="a",
                       body="a"),
            make_item("La selección argentina ganó el partido inaugural", url="https://b.com/2", source="b",
                       body="b"),
            make_item("Nuevo récord de temperatura en la Antártida", url="https://c.com/3", source="c",
                       body="c"),
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
        """Items with different titles but overlapping body token content should cluster."""
        items = [
            make_item(
                "Gobierno anuncia nuevo plan economico nacional",
                url="https://fuente-a.com/articulo-1",
                source="a",
                body=(
                    "El presidente anuncio un nuevo plan economico que incluye medidas fiscales "
                    "reformas laborales y cambios en el sistema de jubilaciones Este plan busca "
                    "reactivar la economia nacional y mejorar las condiciones de vida de los ciudadanos"
                ),
            ),
            make_item(
                "Hoy se conoce una noticia importante en el congreso",
                url="https://fuente-b.com/articulo-2",
                source="b",
                body=(
                    "Las nuevas medidas economicas fueron anunciadas por el presidente incluyendo "
                    "reformas fiscales y laborales importantes El sistema de jubilaciones tambien "
                    "sera modificado como parte del paquete que busca reactivar la economia nacional"
                ),
            ),
        ]
        result = cluster(items)
        assert len(result) == 1
        assert len(result[0].items) == 2
        assert len(result[0].sources) == 2

    def test_title_threshold_lowered_to_0_55(self) -> None:
        """Titles with ratio ~0.65 should cluster with the lower 0.55 threshold."""
        items = [
            make_item(
                "Anuncian plan economico en el congreso nacional",
                url="https://a.com/articulo-1",
                source="a",
                body="Texto unico para el primer articulo economico",
            ),
            make_item(
                "Debaten el plan economico en sesion del congreso",
                url="https://b.com/articulo-2",
                source="b",
                body="Texto completamente diferente para el segundo articulo",
            ),
        ]
        result = cluster(items)
        assert len(result) == 1
        assert len(result[0].items) == 2

    def test_slug_threshold_lowered_to_0_4(self) -> None:
        """Same-domain items with slug ratio ~0.41 should cluster with the lower 0.4 threshold."""
        items = [
            make_item(
                "Reforma del sistema de jubilaciones",
                url="https://ejemplo.com/reforma-jubilaciones",
                source="a",
                body="Contenido sobre reforma del sistema previsional",
            ),
            make_item(
                "Nueva ley de bases aprobada en el congreso",
                url="https://ejemplo.com/ley-bases",
                source="b",
                body="Texto diferente sobre la nueva ley aprobada",
            ),
        ]
        result = cluster(items)
        assert len(result) == 1
        assert len(result[0].items) == 2
