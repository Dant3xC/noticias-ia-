"""Pipeline orchestrator that chains all stages end-to-end.

Stages run in order:

    1. **Fetch** — async RSS/Atom fetch via ``fetch_all_sources``.
    2. **Window** — time-window filter via ``filter_by_window``.
    3. **Dedup** — near-duplicate removal via ``dedup``.
    4. **Cluster** — story clustering via ``cluster``.
    5. **Family format + Trust** — per-cluster payload building
       (``build_family_format``) and algorithmic trust labelling
       (``compute_trust``).
    6. **LLM summary** — per-cluster LLM summary generation with
       budget enforcement and stub fallback.

The orchestrator returns clusters in memory. It does **not** write to
disk (persistence is PR4) and does **not** print to console (rendering
is PR4).

Two entry points:
    - ``run_pipeline_async``: async version for tests and advanced usage.
    - ``run_pipeline``: sync wrapper using ``asyncio.run``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import msgspec

from noticias.llm.client import LLMClient
from noticias.llm.parser import parse_llm_response, stub_summary
from noticias.llm.prompt import build_prompt
from noticias.models.cluster import Cluster
from noticias.models.source import Source, SourceConfig
from noticias.pipeline.cluster import cluster as _cluster
from noticias.pipeline.dedup import dedup as _dedup
from noticias.pipeline.family import build_family_format
from noticias.pipeline.fetch import fetch_all_sources
from noticias.pipeline.window import filter_by_window
from noticias.trust.label import compute_trust

logger = logging.getLogger(__name__)


async def run_pipeline_async(
    sources: list[Source],
    window: timedelta,
    llm: LLMClient,
    config: SourceConfig,
) -> list[Cluster]:
    """Run the full analysis pipeline asynchronously.

    Args:
        sources: The list of sources to fetch.
        window: The time window for filtering (e.g. ``timedelta(hours=24)``).
        llm: An ``LLMClient`` instance for summary generation.
        config: Pipeline configuration (timeout, concurrency, etc.).

    Returns:
        A list of ``Cluster`` objects with summary, trust_label,
        trust_reason, and divergence_ratio populated. Returns an empty
        list if no items were fetched within the window.
    """
    # ── Stage 1: Fetch ─────────────────────────────────────────────────
    fetch_result = await fetch_all_sources(
        sources,
        window_h=int(window.total_seconds() // 3600),
        timeout_s=config.fetch_timeout_s,
        max_concurrent=config.max_concurrent_sources,
        rate_limit_s=config.rate_limit_s,
    )

    # ── Stage 2: Time window filter ────────────────────────────────────
    items = filter_by_window(fetch_result.items, window)

    # ── Stage 3: Dedup ─────────────────────────────────────────────────
    deduped = _dedup(items)

    # ── Stage 4: Cluster ───────────────────────────────────────────────
    clusters = _cluster(deduped)
    if not clusters:
        logger.info("Pipeline produced zero clusters (no items in window)")
        return clusters

    # ── Stage 5: Family format + Trust ─────────────────────────────────
    payloads: list = []
    for cluster in clusters:
        payload = build_family_format(cluster)
        payloads.append(payload)
        trust_label, trust_reason = compute_trust(cluster)
        cluster.trust_label = trust_label.value
        cluster.trust_reason = trust_reason

    # ── Stage 6: LLM summaries ─────────────────────────────────────────
    for cluster, payload in zip(clusters, payloads):
        payload_json = msgspec.json.encode(payload)
        tokens = llm.estimate_tokens(
            payload_json.decode("utf-8", errors="replace"),
        )

        # Budget check
        if llm.tokens_used + tokens > llm.token_budget:
            logger.warning(
                "Token budget exceeded: %d used + %d estimated > %d budget. "
                "Skipping LLM for cluster '%s'",
                llm.tokens_used,
                tokens,
                llm.token_budget,
                cluster.event_label,
            )
            stub = stub_summary(cluster)
            cluster.summary = stub.summary
            cluster.highlights = stub.highlights
            continue

        # Build prompt and call LLM
        prompt = build_prompt(payload)
        response_content = await llm.complete(prompt, json_mode=True)

        if response_content is None:
            logger.warning(
                "LLM returned no response for cluster '%s'. "
                "Using stub summary.",
                cluster.event_label,
            )
            stub = stub_summary(cluster)
            cluster.summary = stub.summary
            cluster.highlights = stub.highlights
            continue

        # Parse LLM response
        llm_response = parse_llm_response(
            response_content,
            cluster_id=cluster.event_label,
        )
        cluster.summary = llm_response.summary
        cluster.highlights = llm_response.highlights

    return clusters


def run_pipeline(
    sources: list[Source],
    window: timedelta,
    llm: LLMClient,
    config: SourceConfig,
) -> list[Cluster]:
    """Sync wrapper around ``run_pipeline_async``.

    Args:
        sources: The list of sources to fetch.
        window: The time window for filtering.
        llm: An ``LLMClient`` instance.
        config: Pipeline configuration.

    Returns:
        A list of ``Cluster`` objects with summary, trust_label,
        and trust_reason populated.
    """
    return asyncio.run(run_pipeline_async(sources, window, llm, config))
