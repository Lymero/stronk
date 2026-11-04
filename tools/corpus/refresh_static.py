"""Fetch again the Data Dragon game data of crawls stored before item fingerprints were kept,
so their patches can be pooled with others (ADR-088). Data Dragon is public: no API key.

    uv run python tools/corpus/refresh_static.py runs/crawl/euw1-16.21 runs/crawl/kr-16.21 …

Only game data without fingerprints is fetched, and written only if Data Dragon serves the same
version as the one stored (16.21.1), so nothing else about the crawl changes.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from stronk_pipeline.adapters.match_store import FileMatchStore
from stronk_pipeline.adapters.riot.client import RiotApiSource
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.static import StaticData
from stronk_pipeline.ports import SourceError

type Fetch = Callable[[str], Awaitable[Result[StaticData, SourceError]]]


async def refresh(crawl: Path, fetch: Fetch) -> list[str]:
    """What happened to each patch of `crawl`'s game data, one line each."""
    store = FileMatchStore(crawl)
    match store.read_static():
        case Err(error=e):
            return [f"{crawl}: {e.message}"]
        case Ok(value=statics):
            pass
    lines: list[str] = []
    for patch, stored in sorted(statics.items()):
        if all(i.fingerprint for i in stored.items.values()):
            lines.append(f"{crawl} {patch}: already has fingerprints")
            continue
        match await fetch(patch):
            case Err(error=e):
                lines.append(f"{crawl} {patch}: not refreshed: {e.message}")
                continue
            case Ok(value=fresh):
                pass
        if fresh.version != stored.version:
            lines.append(
                f"{crawl} {patch}: not refreshed: Data Dragon serves {fresh.version}, "
                f"the crawl has {stored.version}"
            )
            continue
        match store.put_static(patch, fresh):
            case Err(error=e):
                lines.append(f"{crawl} {patch}: not refreshed: {e.message}")
            case Ok():
                lines.append(f"{crawl} {patch}: refreshed ({fresh.version})")
    return lines


async def _main(crawls: list[Path]) -> int:
    client = httpx.AsyncClient(timeout=30)
    source = RiotApiSource(client=client, platform="euw1", api_key="", limiter=None)
    cache: dict[str, Result[StaticData, SourceError]] = {}

    async def fetch(patch: str) -> Result[StaticData, SourceError]:
        if patch not in cache:
            cache[patch] = await source.static_data(patch)
        return cache[patch]

    try:
        lines = [line for crawl in crawls for line in await refresh(crawl, fetch)]
    finally:
        await source.close()
    print("\n".join(lines))
    return int(any("not refreshed" in line or "cannot" in line for line in lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("crawls", nargs="+", type=Path)
    return asyncio.run(_main(parser.parse_args().crawls))


if __name__ == "__main__":
    sys.exit(main())
