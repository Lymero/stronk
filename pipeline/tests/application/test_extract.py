import json
from pathlib import Path

import polars as pl
from riot_builders import buy, domain_match, domain_static

from stronk_pipeline.adapters.json_report import JsonReportWriter
from stronk_pipeline.adapters.match_store import FileMatchStore
from stronk_pipeline.adapters.parquet_store import ParquetDecisionStore, ParquetFrameStore
from stronk_pipeline.application.extract import ExtractParams, ExtractResult, extract_command
from stronk_pipeline.application.registry import CommandError
from stronk_pipeline.domain.result import Err, Ok, Result

MIN = 60_000


def run(crawl: Path, out: Path) -> Result[ExtractResult, CommandError]:
    command = extract_command(
        FileMatchStore, ParquetDecisionStore(), ParquetFrameStore(), JsonReportWriter()
    )
    return command.run(ExtractParams(crawl=str(crawl), out=str(out)))


def crawled(directory: Path) -> Path:
    store = FileMatchStore(directory)
    store.put_static("16.20", domain_static())
    events = [buy(5 * MIN, 1, 1037), buy(8 * MIN, 1, 6333)]
    store.put(domain_match("EUW1_1", events=events, minutes=20))
    store.put(domain_match("EUW1_2", created=1_760_100_000_000, minutes=22, winner=200))
    return directory


def test_writes_tables_and_report(tmp_path: Path) -> None:
    result = run(crawled(tmp_path / "crawl"), tmp_path / "out")
    assert isinstance(result, Ok)
    assert result.value.matches == 2
    assert result.value.frames == 2 * (20 + 22)
    assert result.value.decisions_by_slot == {0: 20, 1: 1}
    decisions = ParquetDecisionStore().read_decisions(tmp_path / "out" / "decisions.parquet")
    assert isinstance(decisions, Ok)
    assert len(decisions.value) == 21
    frames = pl.read_parquet(tmp_path / "out" / "frames.parquet")
    assert {"match_id", "team", "minute", "outcome", "f_gold_diff"} <= set(frames.columns)
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["stage"] == "extract"
    assert report["static_versions"] == {"16.20": "16.20.1"}
    assert report["inputs"]["matches"] == 2


def test_missing_crawl_is_not_found(tmp_path: Path) -> None:
    result = run(tmp_path / "nope", tmp_path / "out")
    assert isinstance(result, Err)
    assert result.error.code == "not_found"
    assert not (tmp_path / "out").exists()


def test_empty_crawl_is_invalid_input(tmp_path: Path) -> None:
    (tmp_path / "crawl").mkdir()
    result = run(tmp_path / "crawl", tmp_path / "out")
    assert isinstance(result, Err)
    assert result.error.code == "invalid_input"
