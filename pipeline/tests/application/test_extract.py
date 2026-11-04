import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import polars as pl
import pytest
from riot_builders import buy, domain_match, domain_static, fake_ladder, match_payload, monster
from riot_server import FakeRiot, source

from stronk_pipeline.adapters.json_report import JsonReportWriter
from stronk_pipeline.adapters.match_store import FileMatchStore
from stronk_pipeline.adapters.parquet_store import ParquetDecisionStore, ParquetFrameStore
from stronk_pipeline.adapters.riot.payloads import parse_quarantined
from stronk_pipeline.application import extract as extract_module
from stronk_pipeline.application.crawl import CrawlParams, crawl_command
from stronk_pipeline.application.extract import ExtractParams, ExtractResult, extract_command
from stronk_pipeline.application.registry import CommandError
from stronk_pipeline.domain.extract.skill import GameHeader, prior_skill
from stronk_pipeline.domain.extract.tables import extract
from stronk_pipeline.domain.match import Match
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.ports import MatchSource, PayloadParser

MIN = 60_000


def run(
    crawl: Path | list[Path],
    out: Path,
    *,
    parse: PayloadParser = parse_quarantined,
    retry: bool = False,
) -> Result[ExtractResult, CommandError]:
    command = extract_command(
        FileMatchStore, parse, ParquetDecisionStore(), ParquetFrameStore(), JsonReportWriter()
    )
    crawls = [str(c) for c in crawl] if isinstance(crawl, list) else str(crawl)
    params = ExtractParams.model_validate(
        {"crawl": crawls, "out": str(out), "retry_quarantine": retry}
    )
    return command.run(params)


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
    runes = dict.fromkeys((81001, 81002, 81003, 83005, 50001, 50002, 50003), 20)
    assert result.value.decisions_by_slot == {0: 20, 1: 1, 60001: 1, 70000: 20, **runes}
    decisions = ParquetDecisionStore().read_decisions(tmp_path / "out" / "decisions.parquet")
    assert isinstance(decisions, Ok)
    # keystones and items, then the rest of each page, one first components, then the spells
    assert len(decisions.value) == 21 + 7 * 20 + 1 + 20
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


BAD_TIMELINE = "/lol/match/v5/matches/EUW1_1002/timeline"
BAD_REASON = "event.ELITE_MONSTER_KILL.killerTeamId.literal[100,200]: literal_error"


def crawl_with_one_bad_game(directory: Path) -> Path:
    """Four games through the real Riot client; one has a monster kill by team 400."""
    responses = fake_ladder(4, players=1)
    responses[BAD_TIMELINE]["info"]["frames"][10]["events"].append(monster(600_000, 400))

    def sources(_: CrawlParams) -> Result[MatchSource, CommandError]:
        return Ok(source(FakeRiot(responses)))

    command = crawl_command(sources, FileMatchStore)
    crawled = command.run(CrawlParams(out=str(directory), tiers=["CHALLENGER"]))
    assert isinstance(crawled, Ok), crawled
    assert crawled.value.skipped == {"quarantined": 1}
    return directory


def fixed(payload: object) -> Result[Match | None, str]:
    """Today's parser after a fix that drops monster kills by team 400."""
    entry = copy.deepcopy(cast("dict[str, Any]", payload))
    for frame in entry["timeline"]["info"]["frames"]:
        frame["events"] = [e for e in frame["events"] if e.get("killerTeamId") != 400]
    return parse_quarantined(entry)


def test_a_rejected_game_waits_in_quarantine_with_its_reason(tmp_path: Path) -> None:
    crawl = crawl_with_one_bad_game(tmp_path / "crawl")
    held = FileMatchStore(crawl).quarantined()
    assert isinstance(held, Ok)
    assert [(q.match_id, q.reason) for q in held.value] == [("EUW1_1002", BAD_REASON)]
    result = run(crawl, tmp_path / "out")
    assert isinstance(result, Ok)
    assert result.value.matches == 3
    assert result.value.quarantined == {BAD_REASON: 1}
    assert result.value.skip_rate == 0.25
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["result"]["quarantined"] == {BAD_REASON: 1}


def test_after_a_parser_fix_the_retry_extracts_and_clears_it(tmp_path: Path) -> None:
    crawl = crawl_with_one_bad_game(tmp_path / "crawl")
    unchanged = run(crawl, tmp_path / "before", retry=True)
    assert isinstance(unchanged, Ok)
    assert unchanged.value.retried is not None
    assert unchanged.value.retried.still_failing == 1

    result = run(crawl, tmp_path / "out", parse=fixed, retry=True)
    assert isinstance(result, Ok)
    assert result.value.retried is not None
    assert result.value.retried.stored == 1
    assert result.value.matches == 4
    assert result.value.quarantined == {}
    assert result.value.skip_rate == 0
    store = FileMatchStore(crawl)
    assert store.quarantined() == Ok([])
    games = store.read_matches()
    assert isinstance(games, Ok)
    owners = {g.participants[0].player for g in games.value[0]}
    assert len(owners) == 1  # the retried game kept the crawl's pseudonym for its owner


def test_a_kept_match_that_now_reads_is_released_to_be_crawled_again(tmp_path: Path) -> None:
    crawl = crawled(tmp_path / "crawl")
    store = FileMatchStore(crawl)
    store.quarantine("EUW1_9", "info.gameVersion: missing", {"match": match_payload("EUW1_9")})
    result = run(crawl, tmp_path / "out", retry=True)
    assert isinstance(result, Ok)
    assert result.value.retried is not None
    assert result.value.retried.recrawl == 1
    known = store.known()
    assert isinstance(known, Ok)
    assert "EUW1_9" not in known.value


def test_a_new_reason_replaces_the_old_one(tmp_path: Path) -> None:
    crawl = crawled(tmp_path / "crawl")
    store = FileMatchStore(crawl)
    store.quarantine("EUW1_9", "old reason", {"match": {"metadata": {}}, "timeline": None})
    run(crawl, tmp_path / "out", retry=True)
    held = store.quarantined()
    assert isinstance(held, Ok)
    assert [q.reason for q in held.value] == ["metadata.matchId: missing"]


def test_report_counts_skips_by_reason(tmp_path: Path) -> None:
    crawl = crawled(tmp_path / "crawl")
    store = FileMatchStore(crawl)
    for match_id, reason in [("EUW1_7", "older_patch"), ("EUW1_8", "older_patch")]:
        store.skip(match_id, reason)
    store.skip("EUW1_9", "remake")
    result = run(crawl, tmp_path / "out")
    assert isinstance(result, Ok)
    assert result.value.skipped == {"older_patch": 2, "remake": 1}
    assert result.value.skip_rate == 0  # passed over on purpose, not lost


def test_several_crawls_make_one_table(tmp_path: Path) -> None:
    first = crawled(tmp_path / "euw1")
    second = tmp_path / "kr"
    store = FileMatchStore(second)
    store.put_static("16.20", domain_static())
    store.put(domain_match("KR_1", minutes=21))
    store.put(domain_match("EUW1_1", minutes=20))  # also in the first crawl: counts once
    store.skip("KR_2", "remake")
    result = run([first, second], tmp_path / "out")
    assert isinstance(result, Ok)
    assert result.value.matches == 3
    assert result.value.frames == 2 * (20 + 22 + 21)
    assert result.value.skipped == {"remake": 1}
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["params"]["crawl"] == [str(first), str(second)]


def test_one_missing_crawl_fails_the_run(tmp_path: Path) -> None:
    result = run([crawled(tmp_path / "euw1"), tmp_path / "nope"], tmp_path / "out")
    assert isinstance(result, Err)
    assert result.error.code == "not_found"


def test_bands_extract_together_and_name_the_bracket_they_make(tmp_path: Path) -> None:
    master = crawled(tmp_path / "master")
    diamond = crawled(tmp_path / "diamond")  # the same two games: a lobby of both bands
    FileMatchStore(diamond).set_bracket("diamond")
    FileMatchStore(diamond).put(domain_match("EUW1_3", created=1_760_200_000_000))
    alone = run(diamond, tmp_path / "out")
    assert isinstance(alone, Ok)
    assert (alone.value.bands, alone.value.bracket) == (["diamond"], None)
    pooled = run([diamond, master], tmp_path / "out2")
    assert isinstance(pooled, Ok)
    assert (pooled.value.bands, pooled.value.bracket) == (
        ["master_plus", "diamond"],
        "diamond_plus",
    )
    assert pooled.value.matches == 3  # a game in both crawls counts once


def test_games_stream_to_the_same_tables(tmp_path: Path) -> None:
    """Extract reads games one at a time (ADR-079): the same tables as from every game at once."""
    crawl = crawled(tmp_path / "crawl")
    assert isinstance(run(crawl, tmp_path / "out"), Ok)
    store = FileMatchStore(crawl)
    matches, _ = cast(Ok[tuple[list[Match], int]], store.read_matches()).value
    statics = cast(Ok[dict[str, Any]], store.read_static()).value
    at_once = extract(matches, statics)
    streamed = extract(iter(matches), statics, prior_skill(GameHeader.of(m) for m in matches))
    assert np.array_equal(at_once.decisions.features, streamed.decisions.features)
    written = pl.read_parquet(tmp_path / "out" / "decisions.parquet")
    assert written.height == len(at_once.decisions.match_id)


def test_tables_are_written_a_chunk_of_games_at_a_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-080: one part per chunk of games, read back as one table, as when written whole."""
    crawl = crawled(tmp_path / "crawl")
    whole = run(crawl, tmp_path / "whole")
    monkeypatch.setattr(extract_module, "CHUNK_GAMES", 1)
    chunked = run(crawl, tmp_path / "chunked")
    assert isinstance(whole, Ok)
    assert isinstance(chunked, Ok)
    parts = sorted(p.name for p in (tmp_path / "chunked" / "decisions.parquet").iterdir())
    assert parts == ["part-00000.parquet", "part-00001.parquet"]
    # Decision tables sort canonically by each decision's identity, whole or a chunk at a time.
    identity = ["champion", "role", "slot", "match_id", "participant", "minute"]
    for table, order in (("decisions", identity), ("frames", [])):
        a, b = (pl.read_parquet(tmp_path / d / f"{table}.parquet") for d in ("whole", "chunked"))
        assert a.sort(order or a.columns).equals(b.sort(order or b.columns))
    assert whole.value.model_dump(exclude={"outputs"}) == chunked.value.model_dump(
        exclude={"outputs"}
    )


def two_patches(directory: Path, *, fingerprints: bool = True) -> Path:
    """`crawled` and a 16.19 game whose player 1 completes 6333, which changed in 16.20."""
    crawled(directory)
    old = domain_static()
    items = {
        i: replace(
            item, fingerprint="before" if i == 6333 or not fingerprints else item.fingerprint
        )
        for i, item in old.items.items()
    }
    if not fingerprints:
        items = {i: replace(item, fingerprint="") for i, item in items.items()}
    store = FileMatchStore(directory)
    store.put_static("16.19", replace(old, version="16.19.1", items=items))
    events = [buy(5 * MIN, 1, 1037), buy(8 * MIN, 1, 6333)]
    store.put(replace(domain_match("EUW1_3", events=events, minutes=20), patch="16.19"))
    return directory


def test_two_patches_pool_without_the_older_ones_changed_items(tmp_path: Path) -> None:
    result = run(two_patches(tmp_path / "crawl"), tmp_path / "out")
    assert isinstance(result, Ok)
    assert result.value.matches == 3
    assert result.value.dropped["changed_item_older_patch"] == 1  # 16.19's 6333; 16.20's stays
    assert result.value.decisions_by_slot[1] == 1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["patches"] == ["16.19", "16.20"]
    assert report["changed_items"] == {"16.19": [6333]}


def test_patches_dont_pool_without_item_fingerprints(tmp_path: Path) -> None:
    result = run(two_patches(tmp_path / "crawl", fingerprints=False), tmp_path / "out")
    assert isinstance(result, Err)
    assert "no item fingerprints" in result.error.message
