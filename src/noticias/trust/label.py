"""Algorithmic trust label computation for story clusters.

Trust labels are 100% algorithmic. The LLM is NEVER involved in trust
determination. The computation uses only three signals:

- **Source count** (n_sources): how many distinct sources cover the event.
- **Ideological diversity** (distinct_leans): how many different lean
  values (left, center, right) appear in the cluster.
- **Divergence ratio**: token-level disagreement between sources.

Rules (evaluated in order — first match wins):

    | # | Condition | Label |
    |---|-----------|-------|
    | 1 | ``n_sources == 1`` **OR** ``divergence_ratio >= 0.5`` | ``baja`` |
    | 2 | ``n_sources == 2`` **OR** ``distinct_leans == 1`` **OR** ``0.2 <= divergence_ratio < 0.5`` | ``media`` |
    | 3 | ``n_sources >= 3`` **AND** ``distinct_leans >= 2`` **AND** ``divergence_ratio < 0.2`` | ``alta`` |

Edge case (explicit): A 3-source, 1-lean, low-divergence cluster is
``media`` (via rule 2 ``distinct_leans == 1``), NOT ``alta``. Rule 3
requires at least 2 distinct leans.
"""

from __future__ import annotations

from enum import Enum


class TrustLabel(str, Enum):
    """Trust label for a story cluster.

    Spanish values for direct display in console output.
    """

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


# Color mapping for Rich terminal output (used by PR4's renderer).
TRUST_COLORS: dict[TrustLabel, str] = {
    TrustLabel.ALTA: "green",
    TrustLabel.MEDIA: "yellow",
    TrustLabel.BAJA: "red",
}


def compute_trust(
    cluster: "Cluster",  # noqa: F821 — forward ref, lazy import below
) -> tuple[TrustLabel, str]:
    """Compute the algorithmic trust label for a cluster.

    The label is derived solely from source count, distinct lean count,
    and divergence ratio. The LLM is NEVER involved.

    Args:
        cluster: A story cluster whose ``sources``, ``items``, and
            ``divergence_ratio`` fields are populated (e.g. after a
            call to ``build_family_format``).

    Returns:
        A ``(TrustLabel, reason_string)`` tuple. The reason string is
        in neutral Spanish and is at most 120 characters.
    """
    from noticias.models.cluster import Cluster  # noqa: F811

    n = len(cluster.sources)
    distinct_leans = len({item.lean for item in cluster.items})
    div = cluster.divergence_ratio

    # Rule 1: BAJA
    if n == 1 or div >= 0.5:
        label = TrustLabel.BAJA
    # Rule 2: MEDIA
    elif n == 2 or distinct_leans == 1 or (0.2 <= div < 0.5):
        label = TrustLabel.MEDIA
    # Rule 3: ALTA
    else:
        label = TrustLabel.ALTA

    reason = _reason(label, n, distinct_leans, div)
    return label, reason


def _reason(label: TrustLabel, n: int, leans: int, div: float) -> str:
    """Generate a Spanish reason string for a trust label.

    Explains which rule fired and why. Truncated to 120 characters with
    ``"..."`` appended if longer.

    Args:
        label: The computed trust label.
        n: Number of distinct sources in the cluster.
        leans: Number of distinct ideological leans.
        div: Divergence ratio.

    Returns:
        A Spanish string ≤120 characters (or 123 with the ellipsis).
    """
    if label == TrustLabel.ALTA:
        reason = (
            f"{n} fuentes, {leans} líneas ideológicas distintas, "
            f"acuerdo alto (divergencia {div:.2f})."
        )
    elif label == TrustLabel.MEDIA:
        if n == 2:
            reason = (
                f"2 fuentes, acuerdo moderado (divergencia {div:.2f})."
            )
        elif leans == 1:
            reason = (
                f"{n} fuentes pero todas de la misma línea ideológica, "
                f"limitada diversidad."
            )
        else:
            reason = (
                f"{n} fuentes, {leans} líneas ideológicas, "
                f"divergencia moderada ({div:.2f})."
            )
    else:  # BAJA
        if n == 1:
            reason = "Una sola fuente: sin contraste posible."
        else:
            reason = (
                f"{n} fuentes pero divergencia alta ({div:.2f})."
            )

    if len(reason) > 120:
        reason = reason[:117] + "..."

    return reason
