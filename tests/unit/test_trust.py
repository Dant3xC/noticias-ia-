"""Unit tests for algorithmic trust label computation (trust/label.py).

Covers all 8 spec scenarios from design Q4 plus:
- Reason string is in Spanish, ≤120 chars
- Color mapping returns the right colors
- Truncation at 120 chars
"""

from __future__ import annotations

from noticias.trust.label import TRUST_COLORS, TrustLabel, _reason, compute_trust
from tests.helpers import make_cluster, make_item


def _trust_cluster(
    n_sources: int = 1,
    leans: list[str] | None = None,
    divergence_ratio: float = 0.0,
) -> "Cluster":  # noqa: F821
    """Build a Cluster with the given trust-relevant properties.

    Args:
        n_sources: Number of distinct sources.
        leans: Lean values for each source. If shorter than n_sources,
            the last value is repeated. If None, defaults to ["left"].
        divergence_ratio: The divergence ratio to set on the cluster.

    Returns:
        A Cluster with ``sources``, ``items``, and ``divergence_ratio``
        populated.
    """
    if leans is None:
        leans = ["left"]
    # Pad or truncate leans to match n_sources
    padded_leans = [
        leans[i] if i < len(leans) else leans[-1]
        for i in range(n_sources)
    ]

    source_names = [f"source_{chr(97 + i)}" for i in range(n_sources)]
    items = [
        make_item(
            title=f"Event headline from {name}",
            source=name,
            lean=lean,
            body=f"This is the article body for {name} with enough words for tokenization.",
        )
        for i, (name, lean) in enumerate(zip(source_names, padded_leans))
    ]

    cluster = make_cluster(
        items=items,
        sources=source_names,
    )
    cluster.divergence_ratio = divergence_ratio
    return cluster


class TestComputeTrust:
    """All 8 spec scenarios from design Q4."""

    def test_alta_three_sources_three_leans_low_divergence(self) -> None:
        """3 sources, 3 distinct leans, div < 0.2 → alta."""
        cluster = _trust_cluster(
            n_sources=3,
            leans=["left", "center", "right"],
            divergence_ratio=0.15,
        )
        label, reason = compute_trust(cluster)
        assert label == TrustLabel.ALTA, f"Expected ALTA, got {label}: {reason}"
        assert label.value == "alta"

    def test_media_two_sources(self) -> None:
        """2 sources → media (regardless of leans or divergence)."""
        cluster = _trust_cluster(
            n_sources=2,
            leans=["left", "right"],
            divergence_ratio=0.10,
        )
        label, reason = compute_trust(cluster)
        assert label == TrustLabel.MEDIA, f"Expected MEDIA, got {label}: {reason}"

    def test_media_three_sources_one_lean(self) -> None:
        """3 sources, all same lean → media (rule 2: distinct_leans == 1)."""
        cluster = _trust_cluster(
            n_sources=3,
            leans=["right", "right", "right"],
            divergence_ratio=0.10,
        )
        label, reason = compute_trust(cluster)
        assert label == TrustLabel.MEDIA, f"Expected MEDIA, got {label}: {reason}"

    def test_media_three_sources_mid_divergence(self) -> None:
        """3 sources, 2 leans, div=0.35 → media (rule 2: 0.2 <= div < 0.5)."""
        cluster = _trust_cluster(
            n_sources=3,
            leans=["left", "right", "right"],
            divergence_ratio=0.35,
        )
        label, reason = compute_trust(cluster)
        assert label == TrustLabel.MEDIA, f"Expected MEDIA, got {label}: {reason}"

    def test_baja_single_source(self) -> None:
        """1 source → baja."""
        cluster = _trust_cluster(
            n_sources=1,
            leans=["right"],
            divergence_ratio=0.0,
        )
        label, reason = compute_trust(cluster)
        assert label == TrustLabel.BAJA, f"Expected BAJA, got {label}: {reason}"

    def test_baja_high_divergence(self) -> None:
        """3 sources, 2 leans, div=0.98 → baja (div >= 0.97 calibrated threshold)."""
        cluster = _trust_cluster(
            n_sources=3,
            leans=["left", "right", "right"],
            divergence_ratio=0.98,
        )
        label, reason = compute_trust(cluster)
        assert label == TrustLabel.BAJA, f"Expected BAJA, got {label}: {reason}"
        assert "0.98" in reason

    def test_boundary_divergence_0_2_is_media(self) -> None:
        """Boundary: div exactly 0.2 → media (not alta)."""
        cluster = _trust_cluster(
            n_sources=3,
            leans=["left", "center", "right"],
            divergence_ratio=0.20,
        )
        label, reason = compute_trust(cluster)
        assert label == TrustLabel.MEDIA, f"Expected MEDIA, got {label}: {reason}"

    def test_boundary_divergence_0_97_is_baja(self) -> None:
        """Boundary: div exactly 0.97 → baja (calibrated threshold, was 0.5)."""
        cluster = _trust_cluster(
            n_sources=3,
            leans=["left", "center", "right"],
            divergence_ratio=0.97,
        )
        label, reason = compute_trust(cluster)
        assert label == TrustLabel.BAJA, f"Expected BAJA, got {label}: {reason}"


class TestReasonString:
    """Reason string is in Spanish, ≤120 chars, contextual."""

    def test_alta_reason_spanish(self) -> None:
        label, reason = compute_trust(
            _trust_cluster(n_sources=3, leans=["left", "center", "right"], divergence_ratio=0.15),
        )
        assert label == TrustLabel.ALTA
        assert isinstance(reason, str)
        assert "fuentes" in reason
        assert "ideológicas" in reason
        assert len(reason) <= 120, f"Reason too long ({len(reason)}): {reason}"

    def test_media_two_sources_reason(self) -> None:
        label, reason = compute_trust(
            _trust_cluster(n_sources=2, leans=["left", "center"], divergence_ratio=0.10),
        )
        assert label == TrustLabel.MEDIA
        assert "2 fuentes" in reason
        assert len(reason) <= 120

    def test_media_one_lean_reason(self) -> None:
        label, reason = compute_trust(
            _trust_cluster(n_sources=3, leans=["right", "right", "right"], divergence_ratio=0.10),
        )
        assert label == TrustLabel.MEDIA
        assert "misma línea" in reason
        assert len(reason) <= 120

    def test_baja_single_source_reason(self) -> None:
        label, reason = compute_trust(
            _trust_cluster(n_sources=1, leans=["left"], divergence_ratio=0.0),
        )
        assert label == TrustLabel.BAJA
        assert "Una sola fuente" in reason
        assert len(reason) <= 120

    def test_baja_high_divergence_reason(self) -> None:
        label, reason = compute_trust(
            _trust_cluster(n_sources=3, leans=["left", "center", "right"], divergence_ratio=0.98),
        )
        assert label == TrustLabel.BAJA
        assert "divergencia alta" in reason
        assert len(reason) <= 120

    def test_reason_truncated_at_120(self) -> None:
        """Generate a reason that would exceed 120 chars."""
        reason = _reason(
            TrustLabel.MEDIA,
            n=10,
            leans=2,
            div=0.123456789,
        )
        assert len(reason) <= 123, f"Reason too long ({len(reason)}): {reason}"
        if len(reason) > 120:
            assert reason.endswith("...")


class TestTrustColorMapping:
    """Color mapping returns the right colors."""

    def test_alta_green(self) -> None:
        assert TRUST_COLORS[TrustLabel.ALTA] == "green"

    def test_media_yellow(self) -> None:
        assert TRUST_COLORS[TrustLabel.MEDIA] == "yellow"

    def test_baja_red(self) -> None:
        assert TRUST_COLORS[TrustLabel.BAJA] == "red"

    def test_all_labels_mapped(self) -> None:
        assert set(TRUST_COLORS.keys()) == {TrustLabel.ALTA, TrustLabel.MEDIA, TrustLabel.BAJA}


class TestTrustLabelEnum:
    """TrustLabel enum values are Spanish strings."""

    def test_values(self) -> None:
        assert TrustLabel.ALTA.value == "alta"
        assert TrustLabel.MEDIA.value == "media"
        assert TrustLabel.BAJA.value == "baja"

    def test_is_str_enum(self) -> None:
        """TrustLabel inherits from str, so .value returns the string."""
        assert isinstance(TrustLabel.ALTA.value, str)
        assert TrustLabel.ALTA.value == "alta"
        # members compare as strings
        assert TrustLabel.ALTA == "alta"
        assert TrustLabel.MEDIA == "media"
        assert TrustLabel.BAJA == "baja"
