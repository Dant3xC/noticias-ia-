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

from noticias.llm.client import LLMClient, TokenBudgetExceeded
from noticias.llm.parser import parse_batch_llm_response, stub_summary
from noticias.llm.prompt import build_batch_prompt, build_cluster_block
from noticias.models.cluster import Cluster, FamilyFormatPayload
from noticias.models.source import Source, SourceConfig
from noticias.pipeline.cluster import cluster as _cluster
from noticias.pipeline.content_filter import filter_content
from noticias.pipeline.dedup import dedup as _dedup
from noticias.pipeline.embed import Embedder
from noticias.pipeline.family import build_family_format, truncate_payload
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
    embedder = Embedder()
    clusters = _cluster(deduped, embedder=embedder)
    if not clusters:
        logger.info("Pipeline produced zero clusters (no items in window).")
        return clusters

    # ── Stage 7: Family format + Trust ──────────────────────────────────
    payloads: list = []
    for cluster in clusters:
        payload = build_family_format(cluster)
        payloads.append(truncate_payload(payload))
        trust_label, trust_reason = compute_trust(cluster)
        cluster.trust_label = trust_label.value
        cluster.trust_reason = trust_reason

    # ── Stage 8: LLM summaries (per-cluster greedy budget) ────────────
    # Estimate tokens per cluster, sort largest-first, greedily fill
    # sub-batch. Clusters that don't fit the remaining budget get a stub
    # summary immediately. The happy path (all fit) stays a single call.
    per_cluster_estimates = [
        (cluster, payload, llm.estimate_tokens(build_cluster_block(payload)))
        for cluster, payload in zip(clusters, payloads)
    ]
    per_cluster_estimates.sort(key=lambda x: x[2], reverse=True)

    sub_batch: list[tuple[Cluster, FamilyFormatPayload, int]] = []
    remaining_budget = llm.token_budget - llm.tokens_used

    for cluster, payload, estimate in per_cluster_estimates:
        if estimate <= remaining_budget:
            sub_batch.append((cluster, payload, estimate))
            remaining_budget -= estimate
        else:
            stub = stub_summary(cluster)
            cluster.summary = stub.summary
            cluster.highlights = stub.highlights

    if not sub_batch:
        logger.warning(
            "Token budget too small for any cluster "
            "(%d used + min estimate > %d budget). All got stubs.",
            llm.tokens_used,
            llm.token_budget,
        )
        return clusters

    sub_batch_clusters = [c for c, _, _ in sub_batch]
    sub_batch_payloads = [p for _, p, _ in sub_batch]
    sub_batch_total = sum(est for _, _, est in sub_batch)
    batch_prompt = build_batch_prompt(sub_batch_payloads)

    logger.info(
        "Calling LLM batch — %d/%d clusters, ~%d total estimated tokens",
        len(sub_batch_clusters),
        len(clusters),
        sub_batch_total,
    )
    try:
        response_content = await llm.complete(batch_prompt, json_mode=True)
    except TokenBudgetExceeded:
        logger.warning(
            "Sub-batch prompt exceeded token budget (%d used + estimate > %d). "
            "All sub-batch clusters will use stub summaries.",
            llm.tokens_used,
            llm.token_budget,
        )
        for cluster, _, _ in sub_batch:
            stub = stub_summary(cluster)
            cluster.summary = stub.summary
            cluster.highlights = stub.highlights
        return clusters

    if response_content is None:
        logger.warning("LLM returned no response. Using stub summaries.")
        for cluster, _, _ in sub_batch:
            stub = stub_summary(cluster)
            cluster.summary = stub.summary
            cluster.highlights = stub.highlights
        return clusters

    # Parse the batch response and distribute summaries to sub-batch clusters.
    results = parse_batch_llm_response(response_content)
    matched = 0
    for cluster, _, _ in sub_batch:
        cid = cluster.event_label
        if cid in results:
            cluster.summary = results[cid].summary
            cluster.highlights = results[cid].highlights
            matched += 1
        else:
            stub = stub_summary(cluster)
            cluster.summary = stub.summary
            cluster.highlights = stub.highlights

    logger.info(
        "Batch LLM: %d/%d sub-batch clusters had matching IDs in response; "
        "%d got stub fallback.",
        matched,
        len(sub_batch_clusters),
        len(sub_batch_clusters) - matched,
    )

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
