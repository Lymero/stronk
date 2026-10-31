"""The pipeline from crawl to WPA through the command registry, on a replayed recording."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from riot_builders import fake_ladder
from riot_server import FakeRiot, source

from stronk_pipeline.adapters.recording import RecordingTransport, Scrubber
from stronk_pipeline.cli import build_registry
from stronk_pipeline.config import Settings
from stronk_pipeline.domain.result import Ok

GAMES = 40


@pytest.fixture(scope="module")
def recording(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """What `crawl.run` with `record` would save from a live crawl of a fake ladder."""
    directory = tmp_path_factory.mktemp("recording")
    riot = FakeRiot(fake_ladder(GAMES))
    transport = RecordingTransport(httpx.MockTransport(riot), directory, Scrubber(b"s"))

    async def walk() -> None:
        src = source(transport)
        players = await src.players("CHALLENGER", "I", 1)
        assert isinstance(players, Ok)
        for player in players.value:
            ids = await src.match_ids(player, 20)  # crawl.run default
            assert isinstance(ids, Ok)
            for match_id in ids.value:
                await src.fetch(match_id, lambda _: None)
        await src.static_data("16.20")
        await src.close()

    asyncio.run(walk())
    return directory


def test_crawl_extract_estimate(recording: Path, tmp_path: Path) -> None:
    registry = build_registry(Settings.model_construct(riot_api_key=None))
    crawl_dir, out = tmp_path / "crawl", tmp_path / "extract"
    crawl = registry.dispatch(
        "crawl.run",
        {
            "replay": str(recording),
            "out": str(crawl_dir),
            "max_matches": 1000,
            "tiers": ["CHALLENGER"],
        },
    )
    assert isinstance(crawl, Ok), crawl
    assert json.loads(crawl.value.model_dump_json())["stored"] == GAMES

    extract = registry.dispatch("extract.run", {"crawl": str(crawl_dir), "out": str(out)})
    assert isinstance(extract, Ok), extract
    assert (out / "report.json").is_file()

    wpa = registry.dispatch(
        "wpa.estimate", {"decisions": str(out / "decisions.parquet"), "bootstrap_samples": 10}
    )
    assert isinstance(wpa, Ok), wpa
    options = {
        (e["slot"], e["option"]) for e in json.loads(wpa.value.model_dump_json())["estimates"]
    }
    assert {(1, "3071"), (1, "6333"), (1, "3031")} <= options


def test_replay_of_a_missing_recording_is_not_found(tmp_path: Path) -> None:
    registry = build_registry(Settings.model_construct(riot_api_key=None))
    result = registry.dispatch("crawl.run", {"replay": str(tmp_path / "nope")})
    assert not isinstance(result, Ok)
    assert result.error.code == "not_found"


def test_live_crawl_without_a_key_is_refused(tmp_path: Path) -> None:
    registry = build_registry(Settings.model_construct(riot_api_key=None))
    result = registry.dispatch("crawl.run", {"out": str(tmp_path)})
    assert not isinstance(result, Ok)
    assert result.error.code == "unauthorized"
    assert "RIOT_API_KEY" in result.error.message
