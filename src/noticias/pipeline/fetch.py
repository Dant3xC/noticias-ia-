"""Async RSS/Atom fetcher with concurrency control and rate limiting.

The fetcher drives ``httpx.AsyncClient`` to fetch all configured sources
concurrently (capped by ``asyncio.Semaphore``), applies per-source rate
limiting (≥5 s between requests to the same source), and normalises each
feed via the RSS adapter into ``NewsItem`` objects.

Failure isolation is per-source: a failed source produces a
``FetchFailure`` record but does **not** abort other sources.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from noticias.models.item import NewsItem
from noticias.models.source import Source
from noticias.sources.adapters import get_adapter, normalize

logger = logging.getLogger(__name__)

# Rotated from Chrome/131 → 136 to reduce Cloudflare challenge frequency.
# See https://github.com/dante/noticias-ia/issues/ambito-403 for background.
_DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


# Fallback User-Agent used only when a 403 is received (to retry with a
# different browser profile that the CDN may not have fingerprinted yet).
_FALLBACK_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) "
    "Gecko/20100101 Firefox/136.0"
)

_DEFAULT_ACCEPT: str = "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"
_DEFAULT_ACCEPT_LANGUAGE: str = "es-AR,es;q=0.9,en;q=0.5"

# Browser-request headers (Sec-* family) to help pass Cloudflare challenges.
# These are added as defaults because some sources (notably ambito) use
# Cloudflare's JS / bot-detection layer that penalises clients lacking them.
_BROWSER_HEADERS: dict[str, str] = {
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def _resolve_user_agent() -> str:
    """Return the effective User-Agent string.

    Reads ``NOTICIAS_USER_AGENT`` from the environment. Falls back to
    ``_DEFAULT_USER_AGENT`` when the variable is unset or empty.
    """
    ua = os.environ.get("NOTICIAS_USER_AGENT")
    return ua if ua else _DEFAULT_USER_AGENT


@dataclass
class FetchFailure:
    """A record of a single source's fetch failure."""

    source: str
    reason: str


@dataclass
class FetchResult:
    """Aggregate result of fetching all sources."""

    items: list[NewsItem] = field(default_factory=list)
    failures: list[FetchFailure] = field(default_factory=list)


async def fetch_all_sources(
    sources: list[Source],
    window_h: int = 24,
    timeout_s: float = 15.0,
    max_concurrent: int = 5,
    rate_limit_s: int = 5,
) -> FetchResult:
    """Fetch RSS feeds from all sources concurrently.

    Args:
        sources: The list of sources to fetch.
        window_h: **Not used in this function** — passed through for
            pipeline signature compatibility.
        timeout_s: HTTP request timeout in seconds.
        max_concurrent: Maximum number of simultaneous HTTP requests.
        rate_limit_s: Minimum gap (in seconds) between requests to the
            same source.

    Returns:
        A ``FetchResult`` containing successfully fetched items and
        per-source failures.
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    rate_locks: dict[str, asyncio.Lock] = {}
    last_call: dict[str, float] = {}

    limits = httpx.Limits(
        max_keepalive_connections=max_concurrent,
        max_connections=max_concurrent,
    )
    ua = _resolve_user_agent()
    headers = {
        "User-Agent": ua,
        "Accept": _DEFAULT_ACCEPT,
        "Accept-Language": _DEFAULT_ACCEPT_LANGUAGE,
        **_BROWSER_HEADERS,
    }
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s),
        limits=limits,
        headers=headers,
    ) as client:
        tasks = [
            _fetch_one(source, client, semaphore, rate_locks, last_call, rate_limit_s)
            for source in sources
        ]
        results: list[list[NewsItem] | FetchFailure] = await asyncio.gather(*tasks)

    items: list[NewsItem] = []
    failures: list[FetchFailure] = []

    for result in results:
        if isinstance(result, FetchFailure):
            failures.append(result)
        elif result:  # non-empty list
            items.extend(result)

    return FetchResult(items=items, failures=failures)


async def _fetch_one(
    source: Source,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    rate_locks: dict[str, asyncio.Lock],
    last_call: dict[str, float],
    rate_limit_s: int,
) -> list[NewsItem] | FetchFailure:
    """Fetch and normalise a single source's RSS feed.

    Steps:
        1. Skip sources with empty / ``None`` URL.
        2. Acquire semaphore slot.
        3. Wait for per-source rate-limit gap.
        4. HTTP GET the feed.
        5. Parse via ``get_adapter`` (runs feedparser in a thread).
        6. Normalise each raw entry to ``NewsItem``.

    Returns a ``FetchFailure`` on any error — never raises.
    """
    # ── Skip sources with empty URL ────────────────────────────────────
    if not source.url or not source.url.strip():
        return FetchFailure(
            source=source.name,
            reason="URL no configurada — agrega la con `noticias fuentes add ...`",
        )

    async with semaphore:
        # ── Per-source rate limit ──────────────────────────────────────
        if source.name not in rate_locks:
            rate_locks[source.name] = asyncio.Lock()

        async with rate_locks[source.name]:
            now = _loop_time()
            last = last_call.get(source.name, 0.0)
            gap = now - last
            if gap < rate_limit_s:
                sleep_for = rate_limit_s - gap
                logger.debug(
                    "Rate limit: waiting %.1f s before fetching '%s'",
                    sleep_for,
                    source.name,
                )
                await asyncio.sleep(sleep_for)
            last_call[source.name] = _loop_time()

        # ── Fetch ─────────────────────────────────────────────────────
        logger.info("Fetching '%s' from %s", source.name, source.url)

        # We attempt the fetch and may retry once on 403 (CDN challenge).
        response = await _attempt_fetch(source, client)
        if response is None:
            # 403 — retry once with Firefox UA + fresh client
            logger.info(
                "Got 403 fetching '%s'; retrying with Firefox UA",
                source.name,
            )
            alt_headers = {
                "User-Agent": _FALLBACK_USER_AGENT,
                "Accept": _DEFAULT_ACCEPT,
                "Accept-Language": _DEFAULT_ACCEPT_LANGUAGE,
                **_BROWSER_HEADERS,
            }
            try:
                async with httpx.AsyncClient(
                    timeout=client.timeout,
                    headers=alt_headers,
                ) as alt_client:
                    response = await _attempt_fetch(source, alt_client)
            except httpx.HTTPError:
                response = None

        if response is None:
            return FetchFailure(
                source=source.name,
                reason="HTTP 403 (retried with alternative UA)",
            )
        if isinstance(response, FetchFailure):
            return response

    # ── Parse & normalise ──────────────────────────────────────────────
    adapter = get_adapter(source)

    try:
        raw_entries: list[dict[str, Any]] = await asyncio.to_thread(
            adapter.parse, response.content,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Feed parse error for '%s': %s", source.name, exc)
        return FetchFailure(source=source.name, reason=f"Parse error: {exc}")

    if not raw_entries:
        logger.info("Empty feed for '%s'", source.name)
        return []

    items: list[NewsItem] = []
    for raw_entry in raw_entries:
        try:
            items.append(normalize(raw_entry, source))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Normalize error for entry in '%s': %s", source.name, exc,
            )
            continue

    logger.info("Fetched %d items from '%s'", len(items), source.name)
    return items


async def _attempt_fetch(
    source: Source,
    client: httpx.AsyncClient,
) -> httpx.Response | FetchFailure | None:
    """Try a single GET request, returning the response or a failure reason.

    Returns:
        - ``httpx.Response`` on success.
        - ``FetchFailure`` on any non-403 error.
        - ``None`` on HTTP 403 (signals the caller to retry).
    """
    try:
        resp = await client.get(source.url)
        resp.raise_for_status()
        return resp
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            return None  # signal retry
        code = exc.response.status_code
        logger.warning("HTTP %s fetching '%s'", code, source.name)
        return FetchFailure(source=source.name, reason=f"HTTP {code}")
    except httpx.TimeoutException:
        logger.warning("Timeout fetching '%s'", source.name)
        return FetchFailure(source=source.name, reason="Timeout")
    except httpx.HTTPError as exc:
        logger.warning("HTTP error fetching '%s': %s", source.name, exc)
        return FetchFailure(source=source.name, reason=str(exc))


def _loop_time() -> float:
    """Return the event loop's monotonic clock time."""
    return asyncio.get_event_loop().time()
