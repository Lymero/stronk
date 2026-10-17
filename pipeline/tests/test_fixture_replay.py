"""The pipeline on the committed recording of a live crawl (`fixtures/riot/euw1`, 2026-10-17).

Unlike `test_pipeline_offline`, these payloads come from the real Riot API, so this guards the
parsers against the live response shape: a field Riot changes or a value it adds shows up here.
"""

import json
from pathlib import Path

import pytest

from stronk_pipeline.cli import build_registry
from stronk_pipeline.config import Settings
from stronk_pipeline.domain.result import Ok

RECORDING = Path(__file__).resolve().parents[2] / "fixtures" / "riot" / "euw1"
GAMES = 10
"""Recorded with `just pipeline-stage crawl` and these parameters; replay must match them."""
PARAMS = {"platform": "euw1", "max_matches": GAMES}


@pytest.fixture(scope="module")
def crawled(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, object]]:
    registry = build_registry(Settings.model_construct(riot_api_key=None))
    out = tmp_path_factory.mktemp("crawl")
    result = registry.dispatch("crawl.run", {**PARAMS, "replay": str(RECORDING), "out": str(out)})
    assert isinstance(result, Ok), result
    return out, json.loads(result.value.model_dump_json())


def test_every_recorded_game_is_stored(crawled: tuple[Path, dict[str, object]]) -> None:
    _, summary = crawled
    assert summary["stored"] == GAMES
    assert summary["errors"] == 0
    assert summary["skipped"] == {"older_patch": 1}  # a history walk stops at its first older game


def test_recorded_games_extract_and_estimate(
    crawled: tuple[Path, dict[str, object]], tmp_path: Path
) -> None:
    crawl_dir, _ = crawled
    registry = build_registry(Settings.model_construct(riot_api_key=None))
    extract = registry.dispatch("extract.run", {"crawl": str(crawl_dir), "out": str(tmp_path)})
    assert isinstance(extract, Ok), extract
    report = json.loads(extract.value.model_dump_json())
    assert report["matches"] == GAMES
    assert report["decisions"] > 0

    wpa = registry.dispatch(
        "wpa.estimate", {"decisions": str(tmp_path / "decisions.parquet"), "bootstrap_samples": 10}
    )
    assert isinstance(wpa, Ok), wpa
