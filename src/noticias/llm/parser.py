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


def parse_llm_response(raw: str, cluster_id: str) -> LLMResponse:
    """Parse an LLM response string into a structured ``LLMResponse``.

    Strategy:
        1. Try ``json.loads`` on the raw string.
        2. If that fails, try to extract a JSON object with a regex
           (some LLMs add prose before/after the JSON).
        3. If all parsing fails, return a stub ``LLMResponse`` with
           ``summary="Resumen no disponible"``.

    Args:
        raw: The raw response content from the LLM.
        cluster_id: The cluster identifier (used as ``cluster_id`` in
            the response).

    Returns:
        A ``LLMResponse`` with best-effort field extraction. Missing
        ``summary`` defaults to ``"Resumen no disponible"``; missing
        ``highlights`` defaults to an empty list.
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

    if data is not None and isinstance(data, dict):
        summary = data.get("summary", "Resumen no disponible")
        if not isinstance(summary, str):
            summary = "Resumen no disponible"
        highlights = data.get("highlights") or []
        if not isinstance(highlights, list):
            highlights = []
        return LLMResponse(
            cluster_id=cluster_id,
            summary=summary,
            highlights=highlights,
        )

    logger.warning(
        "Could not parse LLM response for cluster '%s'", cluster_id,
    )
    return LLMResponse(
        cluster_id=cluster_id,
        summary="Resumen no disponible",
        highlights=[],
    )


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
