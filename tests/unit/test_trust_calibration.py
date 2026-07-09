"""Tests for the trust threshold calibration (v3.2 hotfix)."""
from __future__ import annotations

from noticias.models.cluster import Cluster
from noticias.models.item import NewsItem
from noticias.trust.label import TrustLabel, compute_trust


def make_cluster(n_sources: int, div: float, distinct_leans: int = 2) -> Cluster:
    """Build a synthetic cluster with the given shape for trust testing."""
    # Map distinct_leans to actual lean values
    lean_pool = ["center", "right", "left"]
    selected = lean_pool[:distinct_leans]
    items = []
    for i in range(n_sources):
        # Cycle through selected leans
        lean = selected[i % distinct_leans]
        items.append(
            NewsItem(
                title=f"Story item {i}",
                url=f"https://example.com/{i}",
                source=f"src-{i}",
                lean=lean,
                body=f"body content for item {i} " * 20,
                published_at=None,
            )
        )
    sources = list({it.source for it in items})
    return Cluster(items=items, sources=sources, divergence_ratio=div)


class TestTrustThresholdCalibration:
    def test_single_source_still_baja(self) -> None:
        """1 source = BAJA regardless of divergence (no verification possible)."""
        cluster = make_cluster(n_sources=1, div=0.0)
        label, _ = compute_trust(cluster)
        assert label == TrustLabel.BAJA

    def test_five_sources_high_divergence_is_alta(self) -> None:
        """5 sources with high editorial divergence (~0.96) → ALTA.

        This is the Milei cluster case. With the calibrated threshold
        of 0.97, the BAJA rule only fires for truly degenerate cases
        (every source tells a different story). Editorial differences
        in normal news coverage are correctly classified as ALTA.
        """
        cluster = make_cluster(n_sources=5, div=0.96, distinct_leans=2)
        label, _ = compute_trust(cluster)
        assert label == TrustLabel.ALTA, (
            f"5 sources with div 0.96 should be ALTA (Milei cluster case), got {label}"
        )

    def test_three_sources_low_divergence_is_alta(self) -> None:
        """3+ sources, 2+ leans, low div → ALTA (Rule 3 unchanged)."""
        cluster = make_cluster(n_sources=3, div=0.1, distinct_leans=2)
        label, _ = compute_trust(cluster)
        assert label == TrustLabel.ALTA

    def test_extremely_high_divergence_still_baja(self) -> None:
        """Edge case: div >= 0.97 should still be BAJA (sources completely different)."""
        cluster = make_cluster(n_sources=3, div=0.99, distinct_leans=2)
        label, _ = compute_trust(cluster)
        assert label == TrustLabel.BAJA, (
            f"div 0.99 should still trigger BAJA (degenerate case), got {label}"
        )

    def test_two_sources_is_media(self) -> None:
        """2 sources = MEDIA (moderate verification)."""
        cluster = make_cluster(n_sources=2, div=0.3, distinct_leans=2)
        label, _ = compute_trust(cluster)
        assert label == TrustLabel.MEDIA
