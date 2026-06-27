"""Health-check subcommand for `noticias health`.

Performs a lightweight HTTP HEAD request against each configured source
and displays the results in a Rich table.

Sources with an empty URL are shown with status ``Pendiente`` and their
HEAD request is skipped entirely.
"""

from __future__ import annotations

import asyncio
import time

import httpx
from rich.console import Console
from rich.table import Table

from noticias.sources.registry import SourceRegistry


def health(registry: SourceRegistry) -> None:
    """Run a health check against all configured sources.

    Displays a Rich table with columns: Nombre, URL, Estado, Código HTTP,
    Tiempo (ms).

    Args:
        registry: The source registry to check.
    """
    console = Console()
    sources = registry.list()

    if not sources:
        console.print(
            "[yellow]No hay fuentes configuradas. "
            "Use `noticias fuentes add` para agregar una.[/yellow]",
        )
        return

    results = asyncio.run(_check_all(sources))

    table = Table(title="Estado de las fuentes")
    table.add_column("Nombre", style="cyan")
    table.add_column("URL", style="green", no_wrap=True)
    table.add_column("Estado", style="bold")
    table.add_column("Código", style="white")
    table.add_column("Tiempo (ms)", style="white")

    for name, url, status, code, elapsed_ms in results:
        status_style = {
            "OK": "green",
            "Error": "red",
            "Pendiente": "yellow",
        }.get(status, "white")
        url_display = url or "[dim]pendiente[/dim]"
        code_display = str(code) if code is not None else "—"
        time_display = f"{elapsed_ms:.0f}" if elapsed_ms >= 0 else "—"

        table.add_row(
            name,
            url_display,
            f"[{status_style}]{status}[/{status_style}]",
            code_display,
            time_display,
        )

    console.print(table)


async def _check_all(sources: list) -> list[tuple[str, str, str, int | None, float]]:
    """Check all sources concurrently and return per-source results.

    Uses the same browser-like headers as the fetch pipeline to
    avoid Cloudflare CDN challenges (e.g. ambito returning 403).
    """
    timeout = httpx.Timeout(10.0)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.5",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        tasks = [_check_one(source, client) for source in sources]
        return await asyncio.gather(*tasks)


async def _check_one(
    source,
    client: httpx.AsyncClient,
) -> tuple[str, str, str, int | None, float]:
    """Check a single source via HTTP HEAD."""
    if not source.url or not source.url.strip():
        return (source.name, source.url, "Pendiente", None, -1.0)

    start = time.monotonic()
    try:
        response = await client.head(source.url, follow_redirects=True)
        elapsed = (time.monotonic() - start) * 1000

        # 403 (CDN challenge) → retry once with Firefox UA
        if response.status_code == 403:
            try:
                alt_headers = dict(client.headers)
                alt_headers["User-Agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) "
                    "Gecko/20100101 Firefox/136.0"
                )
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(10.0),
                    headers=alt_headers,
                ) as alt_client:
                    start = time.monotonic()
                    response = await alt_client.head(source.url, follow_redirects=True)
                    elapsed = (time.monotonic() - start) * 1000
            except httpx.HTTPError:
                pass  # use original 403 result

        if response.is_success:
            return (source.name, source.url, "OK", response.status_code, elapsed)
        return (source.name, source.url, "Error", response.status_code, elapsed)
    except httpx.TimeoutException:
        elapsed = (time.monotonic() - start) * 1000
        return (source.name, source.url, "Error", None, elapsed)
    except httpx.HTTPError:
        elapsed = (time.monotonic() - start) * 1000
        return (source.name, source.url, "Error", None, elapsed)
