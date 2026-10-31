from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from riot_builders import domain_match, domain_static, puuid

from stronk_pipeline.adapters.match_store import FileMatchStore
from stronk_pipeline.application.crawl import CrawlParams, CrawlResult, crawl_command
from stronk_pipeline.application.registry import CommandError
from stronk_pipeline.domain.match import Match
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.static import StaticData
from stronk_pipeline.ports import (
    Division,
    MatchHeader,
    MatchSource,
    Rejected,
    Skipped,
    SourceError,
    SourceStats,
    Tier,
)


def game(match_id: str, patch: str = "16.20", queue: int = 420) -> Match:
    return replace(domain_match(match_id), patch=patch, queue=queue)


class FakeSource:
    def __init__(
        self,
        histories: dict[str, list[Match]],
        *,
        failures: dict[str, SourceError] | None = None,
        rejections: dict[str, Rejected] | None = None,
    ) -> None:
        self.histories = histories
        self.games = {g.match_id: g for gs in histories.values() for g in gs}
        self.failures = failures or {}
        self.rejections = rejections or {}
        self.fetched: list[str] = []
        self.timelines: list[str] = []
        self.static_calls: list[str] = []
        self.closed = False
        self.ladder: list[tuple[str, str, int]] = []
        self.diamond: dict[str, list[list[str]]] = {}
        """Diamond ladder pages by division; their players' games are in `histories`."""

    async def players(
        self, tier: Tier, division: Division, page: int
    ) -> Result[list[str], SourceError]:
        self.ladder.append((tier, division, page))
        if tier == "CHALLENGER" and page == 1:
            return Ok(list(self.histories))
        if tier == "DIAMOND" and page <= len(self.diamond.get(division, [])):
            return Ok(self.diamond[division][page - 1])
        return Ok([])

    async def match_ids(self, player: str, count: int) -> Result[list[str], SourceError]:
        return Ok([g.match_id for g in self.histories[player][:count]])

    async def fetch(
        self, match_id: str, wanted: Callable[[MatchHeader], str | None]
    ) -> Result[Match | Skipped | Rejected, SourceError]:
        self.fetched.append(match_id)
        if match_id in self.failures:
            return Err(self.failures[match_id])
        if match_id in self.rejections:
            return Ok(self.rejections[match_id])
        g = self.games[match_id]
        reason = wanted(MatchHeader(match_id, g.patch, g.queue, 11, remake=False))
        if reason is not None:
            return Ok(Skipped(reason))
        self.timelines.append(match_id)
        return Ok(g)

    async def static_data(self, patch: str) -> Result[StaticData, SourceError]:
        self.static_calls.append(patch)
        return Ok(domain_static())

    def stats(self) -> SourceStats:
        return SourceStats(len(self.fetched), 0, 0.0)

    async def close(self) -> None:
        self.closed = True


def crawl(source: FakeSource, out: Path, **params: object) -> Result[CrawlResult, CommandError]:
    def sources(_: CrawlParams) -> Result[MatchSource, CommandError]:
        return Ok(source)

    command = crawl_command(sources, FileMatchStore)
    return command.run(CrawlParams.model_validate({"out": str(out), **params}))


def two_players() -> FakeSource:
    return FakeSource(
        {
            puuid(1): [game("EUW1_5"), game("EUW1_4", queue=440), game("EUW1_3", "16.19")],
            puuid(2): [game("EUW1_5"), game("EUW1_2"), game("EUW1_1")],
        }
    )


def test_stores_games_of_the_target_patch(tmp_path: Path) -> None:
    source = two_players()
    result = crawl(source, tmp_path)
    assert isinstance(result, Ok)
    assert result.value.patch == "16.20"
    assert result.value.stored == 3
    assert result.value.total == 3
    assert result.value.skipped == {"older_patch": 1, "other_queue": 1}
    assert source.fetched.count("EUW1_5") == 1  # shared game fetched once
    assert source.static_calls == ["16.20"]
    assert source.closed


def test_stored_players_are_pseudonymous(tmp_path: Path) -> None:
    crawl(two_players(), tmp_path)
    matches = FileMatchStore(tmp_path).read_matches()
    assert isinstance(matches, Ok)
    stored = {p.player for m in matches.value[0] for p in m.participants}
    assert stored.isdisjoint({puuid(i) for i in range(1, 11)})


def test_an_older_game_ends_the_walk_of_that_player(tmp_path: Path) -> None:
    source = FakeSource({puuid(1): [game("EUW1_3", "16.19"), game("EUW1_2"), game("EUW1_1")]})
    crawl(source, tmp_path, patch="16.20")
    assert source.fetched == ["EUW1_3"]


def test_rerun_fetches_nothing_already_seen(tmp_path: Path) -> None:
    crawl(two_players(), tmp_path)
    again = two_players()
    result = crawl(again, tmp_path)
    assert isinstance(result, Ok)
    assert result.value.stored == 0
    assert result.value.total == 3
    assert again.fetched == []
    assert again.static_calls == []


def test_stops_at_max_matches_and_resumes(tmp_path: Path) -> None:
    first = crawl(two_players(), tmp_path, max_matches=1)
    assert isinstance(first, Ok)
    assert first.value.stored == 1
    second = crawl(two_players(), tmp_path)
    assert isinstance(second, Ok)
    assert second.value.stored == 2
    assert second.value.total == 3


def test_rejected_key_stops_with_progress_in_the_message(tmp_path: Path) -> None:
    failure = SourceError("unauthorized", "Riot rejected the API key")
    source = FakeSource({puuid(1): [game("EUW1_2"), game("EUW1_1")]}, failures={"EUW1_1": failure})
    result = crawl(source, tmp_path)
    assert isinstance(result, Err)
    assert result.error.code == "unauthorized"
    assert "1 new games" in result.error.message
    assert FileMatchStore(tmp_path).count() == 1
    assert source.closed


def test_unavailable_games_are_retried_next_run(tmp_path: Path) -> None:
    failures = {"EUW1_1": SourceError("unavailable", "503")}
    result = crawl(FakeSource({puuid(1): [game("EUW1_1")]}, failures=failures), tmp_path)
    assert isinstance(result, Ok)
    assert result.value.errors == 1
    again = FakeSource({puuid(1): [game("EUW1_1")]})
    crawl(again, tmp_path)
    assert again.fetched == ["EUW1_1"]


def test_invalid_games_are_remembered_as_skipped(tmp_path: Path) -> None:
    failures = {"EUW1_1": SourceError("invalid", "bad timeline")}
    result = crawl(FakeSource({puuid(1): [game("EUW1_1")]}, failures=failures), tmp_path)
    assert isinstance(result, Ok)
    assert result.value.skipped == {"invalid": 1}
    again = FakeSource({puuid(1): [game("EUW1_1")]})
    crawl(again, tmp_path)
    assert again.fetched == []


def test_rejected_games_are_quarantined_and_not_fetched_again(tmp_path: Path) -> None:
    rejected = Rejected("timeline: bad", {"match": {"metadata": {}}, "timeline": {"info": {}}})
    games = {puuid(1): [game("EUW1_1"), game("EUW1_2")]}
    result = crawl(FakeSource(games, rejections={"EUW1_1": rejected}), tmp_path)
    assert isinstance(result, Ok)
    assert result.value.skipped == {"quarantined": 1}
    assert result.value.stored == 1
    held = FileMatchStore(tmp_path).quarantined()
    assert isinstance(held, Ok)
    assert [(q.match_id, q.reason, q.payload) for q in held.value] == [
        ("EUW1_1", "timeline: bad", rejected.payload)
    ]
    again = FakeSource(games)
    crawl(again, tmp_path)
    assert again.fetched == []


def test_nothing_is_written_when_nothing_is_stored(tmp_path: Path) -> None:
    out = tmp_path / "crawl"
    result = crawl(FakeSource({}), out)
    assert isinstance(result, Ok)
    assert not out.exists()


def test_source_errors_from_the_factory_are_returned(tmp_path: Path) -> None:
    def sources(_: CrawlParams) -> Result[MatchSource, CommandError]:
        return Err(CommandError(code="unauthorized", message="RIOT_API_KEY is not set"))

    command = crawl_command(sources, FileMatchStore)
    result = command.run(CrawlParams(out=str(tmp_path)))
    assert isinstance(result, Err)
    assert result.error.code == "unauthorized"


def test_record_and_replay_are_exclusive() -> None:
    with pytest.raises(ValidationError, match="cannot be combined"):
        CrawlParams(record="a", replay="b")


def test_a_diamond_crawl_pages_through_every_division_and_says_so(tmp_path: Path) -> None:
    source = FakeSource({puuid(1): [game("EUW1_7")], puuid(2): [game("EUW1_8")]})
    source.diamond = {"I": [[puuid(1)]], "II": [[puuid(2)]]}
    result = crawl(source, tmp_path / "diamond", tiers=["DIAMOND"])
    assert isinstance(result, Ok)
    assert (result.value.bracket, result.value.stored) == ("diamond", 2)
    pages = [(d, p) for t, d, p in source.ladder if t == "DIAMOND"]
    assert pages == [("I", 1), ("I", 2), ("II", 1), ("II", 2), ("III", 1), ("IV", 1)]
    assert FileMatchStore(tmp_path / "diamond").bracket() == Ok("diamond")


def test_a_crawl_holds_one_bracket(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="crawl each bracket into its own directory"):
        CrawlParams.model_validate({"tiers": ["MASTER", "DIAMOND"]})
    # Master+ games already there: a Diamond crawl goes elsewhere.
    assert isinstance(crawl(two_players(), tmp_path), Ok)
    assert FileMatchStore(tmp_path).bracket() == Ok("master_plus")
    refused = crawl(two_players(), tmp_path, tiers=["DIAMOND"])
    assert isinstance(refused, Err)
    assert "holds master_plus games" in refused.error.message


def test_a_crawl_from_before_brackets_is_master_plus(tmp_path: Path) -> None:
    assert FileMatchStore(tmp_path).bracket() == Ok("master_plus")
