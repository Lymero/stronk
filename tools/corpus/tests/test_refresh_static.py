import asyncio
from dataclasses import replace
from pathlib import Path

from refresh_static import refresh
from riot_builders import domain_static

from stronk_pipeline.adapters.match_store import FileMatchStore
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.static import StaticData
from stronk_pipeline.ports import SourceError

FRESH = domain_static()


def unfingerprinted(static: StaticData) -> StaticData:
    return replace(static, items={i: replace(it, fingerprint="") for i, it in static.items.items()})


async def fetch(patch: str) -> Result[StaticData, SourceError]:
    if patch == "16.20":
        return Ok(FRESH)
    return Err(SourceError("not_found", f"no Data Dragon version for patch {patch}"))


def test_only_game_data_without_fingerprints_is_fetched_again(tmp_path: Path) -> None:
    store = FileMatchStore(tmp_path)
    store.put_static("16.20", unfingerprinted(FRESH))
    store.put_static("9.1", unfingerprinted(replace(FRESH, version="9.1.1")))
    lines = asyncio.run(refresh(tmp_path, fetch))
    assert lines == [
        f"{tmp_path} 16.20: refreshed ({FRESH.version})",
        f"{tmp_path} 9.1: not refreshed: no Data Dragon version for patch 9.1",
    ]
    statics = store.read_static()
    assert isinstance(statics, Ok)
    assert statics.value["16.20"] == FRESH
    assert asyncio.run(refresh(tmp_path, fetch))[0] == f"{tmp_path} 16.20: already has fingerprints"


def test_another_version_is_not_written(tmp_path: Path) -> None:
    store = FileMatchStore(tmp_path)
    older = unfingerprinted(replace(FRESH, version="16.20.0"))
    store.put_static("16.20", older)
    served = f"Data Dragon serves {FRESH.version}, the crawl has 16.20.0"
    assert asyncio.run(refresh(tmp_path, fetch)) == [f"{tmp_path} 16.20: not refreshed: {served}"]
    assert store.read_static() == Ok({"16.20": older})
