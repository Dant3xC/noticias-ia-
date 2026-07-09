"""LLM response parser with JSON extraction and stub fallback.

Attempts standard JSON parsing first. If that fails, extracts a JSON
object from surrounding prose using regex. On total failure, returns a
stub ``LLMResponse``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from noticias.models.cluster import Cluster, LLMResponse

logger = logging.getLogger(__name__)



def parse_batch_llm_response(raw: str) -> dict[str, LLMResponse]:
    """Parse a batch LLM response into a dict of ``{cluster_id: LLMResponse}``.

    Expects the batch format:
    ``{"clusters": [{"cluster_id": "...", "summary": "...", "highlights": [...]}, ...]}``

    Strategy:
        1. ``json.loads`` on the raw string.
        2. If that fails, extract a JSON object via regex.
        3. Expect the parsed dict to have a ``"clusters"`` key with a list
           of cluster entries.
        4. On any failure returns ``{}`` — the caller falls back to stubs.

    Args:
        raw: The raw response content from the LLM.

    Returns:
        A dict mapping ``cluster_id`` to ``LLMResponse``. Empty if parsing
        or structure validation fails.
    """
    data: dict[str, Any] | None = None

    # Attempt 1: standard JSON parse.
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Attempt 2: extract JSON object from surrounding text.
    if data is None:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    if not isinstance(data, dict):
        logger.warning("Could not parse batch LLM response (no JSON found)")
        return {}

    clusters_raw = data.get("clusters")
    if not isinstance(clusters_raw, list):
        logger.warning(
            "Batch LLM response missing 'clusters' list (got %r)",
            type(clusters_raw).__name__,
        )
        return {}

    result: dict[str, LLMResponse] = {}
    for entry in clusters_raw:
        if not isinstance(entry, dict):
            continue
        cid = entry.get("cluster_id")
        if not isinstance(cid, str) or not cid:
            continue
        summary = entry.get("summary", "Resumen no disponible")
        if not isinstance(summary, str):
            summary = "Resumen no disponible"
        highlights = entry.get("highlights") or []
        if not isinstance(highlights, list):
            highlights = []
        result[cid] = LLMResponse(
            cluster_id=cid,
            summary=summary,
            highlights=highlights,
        )

    return result


def stub_summary(cluster: Cluster) -> LLMResponse:
    """Return a stub ``LLMResponse`` when the LLM is not configured.

    Uses neutral Spanish — no voseo.

    Args:
        cluster: The cluster to generate a stub summary for.

    Returns:
        An ``LLMResponse`` with a neutral Spanish stub message and
        empty highlights.
    """
    return LLMResponse(
        cluster_id=cluster.event_label,
        summary="Resumen no disponible (sin LLM configurado).",
        highlights=[],
    )
