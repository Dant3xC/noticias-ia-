"""Unit tests for story clustering (pipeline/cluster.py).

Covers:
- Title-similarity clustering (>0.75)
- URL / domain + slug matching
- No-match → single-item clusters
- Single-item input
- Identical titles with different bodies
- Multiple items from same source
- Empty list
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from noticias.pipeline.cluster import cluster
from tests.helpers import make_item


class TestCluster:
    def test_empty_list(self) -> None:
        assert cluster([]) == []

    def test_embedder_called_once_with_all_titles(self) -> None:
        """Embedder.embed() is called exactly once with the full title list."""
        items = [
            make_item("Climate summit begins in Rio", source="a", url="https://a.com/1"),
            make_item("World leaders meet for climate summit in Rio", source="b", url="https://b.com/2"),
            make_item("Sports results from the weekend", source="c", url="https://c.com/3"),
        ]
        mock_embedder = MagicMock()
        # Return fake embeddings: one per item, same dimension.
        mock_embedder.embed.return_value = np.array([
            [0.1, 0.2, 0.3],
            [0.1, 0.2, 0.3],
            [0.9, 0.8, 0.7],
        ])

        cluster(items, embedder=mock_embedder)

        # embed must be called exactly once with ALL titles (not per-item).
        mock_embedder.embed.assert_called_once_with(
            [item.title for item in items],
        )

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
            make_item("El gobierno anunció un nuevo plan económico", url="https://a.com/1", source="a"),
            make_item("La selección argentina ganó el partido inaugural", url="https://b.com/2", source="b"),
            make_item("Nuevo récord de temperatura en la Antártida", url="https://c.com/3", source="c"),
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
            make_item("Story one about economics", source="pagina12", url="https://p12.com/a"),
            make_item("Story two about sports", source="pagina12", url="https://p12.com/b"),
            make_item("Story three about weather", source="infobae", url="https://infobae.com/c"),
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
