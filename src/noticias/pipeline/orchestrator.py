"""Pipeline orchestrator that chains all stages end-to-end.

Stages run in order:

    1. **Fetch** — async RSS/Atom fetch via ``fetch_all_sources``.
    2. **Content filter** — keyword-based noise removal via
       ``filter_content`` (skipped when ``options.no_filter`` is ``True``).
    3. **Topic filter** — topic-based allowlist via ``filter_topics``
       (skipped when ``options.no_topics`` is ``True`` or ``options.topics``
       is empty).
    4. **Window** — time-window filter via ``filter_by_window``.
    5. **Dedup** — near-duplicate removal via ``dedup``.
    6. **Cluster** — story clustering via ``cluster``.
    7. **Family format + Trust** — per-cluster payload building
       (``build_family_format``) and algorithmic trust labelling
       (``compute_trust``).
    8. **LLM summary** — per-cluster LLM summary generation with
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
from noticias.pipeline.content_filter import filter_content
from noticias.pipeline.dedup import dedup as _dedup
from noticias.pipeline.family import build_family_format
from noticias.pipeline.fetch import fetch_all_sources
from noticias.pipeline.options import PipelineOptions
from noticias.pipeline.topic_filter import filter_topics
from noticias.pipeline.window import filter_by_window
from noticias.trust.label import compute_trust

logger = logging.getLogger(__name__)


async def run_pipeline_async(
    sources: list[Source],
    window: timedelta,
    llm: LLMClient,
    config: SourceConfig,
    options: PipelineOptions | None = None,
) -> list[Cluster]:
    """Run the full analysis pipeline asynchronously.

    Args:
        sources: The list of sources to fetch.
        window: The time window for filtering (e.g. ``timedelta(hours=24)``).
        llm: An ``LLMClient`` instance for summary generation.
        config: Pipeline configuration (timeout, concurrency, etc.).
        options: Pipeline filter options. When ``None``, defaults to
            ``PipelineOptions()`` (no filters active).

    Returns:
        A list of ``Cluster`` objects with summary, trust_label,
        trust_reason, and divergence_ratio populated. Returns an empty
        list if no items survived the pipeline stages.
    """
    opts = options or PipelineOptions()

    # ── Stage 1: Fetch ─────────────────────────────────────────────────
    fetch_result = await fetch_all_sources(
        sources,
        window_h=int(window.total_seconds() // 3600),
        timeout_s=config.fetch_timeout_s,
        max_concurrent=config.max_concurrent_sources,
        rate_limit_s=config.rate_limit_s,
    )

    items = fetch_result.items
    if not items:
        logger.info("No se encontraron noticias (fetch returned no items).")
        return []

    # ── Stage 2: Content filter ─────────────────────────────────────────
    if not opts.no_filter:
        items = filter_content(items, blocked=opts.blocked_keywords)
        if not items:
            logger.info(
                "No se encontraron noticias que coincidan "
                "con los filtros configurados.",
            )
            return []

    # ── Stage 3: Topic filter ───────────────────────────────────────────
    active_topics = _resolve_topics(opts, config)
    if active_topics is not None:
        items = filter_topics(items, topics=active_topics)
        if not items:
            logger.info(
                "No se encontraron noticias que coincidan "
                "con los filtros configurados.",
            )
            return []

    # ── Stage 4: Time window filter ─────────────────────────────────────
    items = filter_by_window(items, window)

    # ── Stage 5: Dedup ──────────────────────────────────────────────────
    deduped = _dedup(items)

    # ── Stage 6: Cluster ────────────────────────────────────────────────
    clusters = _cluster(deduped)
    if not clusters:
        logger.info("Pipeline produced zero clusters (no items in window).")
        return clusters

    # ── Stage 7: Family format + Trust ──────────────────────────────────
    payloads: list = []
    for cluster in clusters:
        payload = build_family_format(cluster)
        payloads.append(payload)
        trust_label, trust_reason = compute_trust(cluster)
        cluster.trust_label = trust_label.value
        cluster.trust_reason = trust_reason

    # ── Stage 8: LLM summaries ─────────────────────────────────────────
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
    options: PipelineOptions | None = None,
) -> list[Cluster]:
    """Sync wrapper around ``run_pipeline_async``.

    Args:
        sources: The list of sources to fetch.
        window: The time window for filtering.
        llm: An ``LLMClient`` instance.
        config: Pipeline configuration.
        options: Pipeline filter options. When ``None``, defaults to
            ``PipelineOptions()`` (no filters active).

    Returns:
        A list of ``Cluster`` objects with summary, trust_label,
        and trust_reason populated.
    """
    return asyncio.run(run_pipeline_async(sources, window, llm, config, options))


def _resolve_topics(
    opts: PipelineOptions,
    config: SourceConfig,
) -> list[str] | None:
    """Return the effective topics list, or ``None`` if topic filter should be skipped.

    Returns ``None`` (skip filter) when:
    - ``opts.no_topics`` is ``True``, or
    - ``opts.topics`` is empty AND ``config.topics`` is empty.

    When ``opts.topics`` is non-empty, it overrides ``config.topics``.
    When only ``config.topics`` is non-empty, it is used.

    The returned list is capped at ``opts.max_topics`` items.
    """
    if opts.no_topics:
        return None

    # CLI topics override persistent topics when explicitly provided.
    effective = opts.topics if opts.topics else config.topics

    if not effective:
        return None

    # Cap at max topics.
    if len(effective) > opts.max_topics:
        logger.warning(
            "Topic count (%d) exceeds maximum (%d). Using first %d topics.",
            len(effective),
            opts.max_topics,
            opts.max_topics,
        )
        return effective[: opts.max_topics]

    return effective
