import httpx
import pytest
from riot_builders import (
    DDRAGON_VERSION,
    buy,
    league,
    match_payload,
    monster,
    puuid,
    timeline_payload,
)
from riot_server import FakeClock, FakeRiot, run, source

from stronk_pipeline.domain.match import Match
from stronk_pipeline.domain.result import Err, Ok
from stronk_pipeline.ports import MatchHeader, Rejected, Skipped

MATCH = "/lol/match/v5/matches/EUW1_1"
CHALLENGER = "/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5"


def full_game() -> FakeRiot:
    return FakeRiot(
        {
            MATCH: match_payload(),
            f"{MATCH}/timeline": timeline_payload(events=[buy(300_000, 1, 1037)]),
        }
    )


def keep(_: MatchHeader) -> str | None:
    return None


def test_players_best_first() -> None:
    entries = league([puuid(1), puuid(2)])
    entries["entries"].reverse()
    result = run(source(FakeRiot({CHALLENGER: entries})).players("CHALLENGER", "I", 1))
    assert result == Ok([puuid(1), puuid(2)])


def test_diamond_players_come_from_league_entries() -> None:
    path = "/lol/league/v4/entries/RANKED_SOLO_5x5/DIAMOND/I"
    riot = FakeRiot({path: league([puuid(3)])["entries"]})
    assert run(source(riot).players("DIAMOND", "I", 1)) == Ok([puuid(3)])
    assert riot.requests[0].url.params["page"] == "1"


def test_diamond_pages_by_division_and_apex_leagues_come_whole() -> None:
    path = "/lol/league/v4/entries/RANKED_SOLO_5x5/DIAMOND/III"
    riot = FakeRiot({path: league([puuid(4)])["entries"]})
    assert run(source(riot).players("DIAMOND", "III", 7)) == Ok([puuid(4)])
    assert riot.requests[0].url.params["page"] == "7"
    # An apex league has no second page: nothing, and no request.
    assert run(source(riot).players("MASTER", "I", 2)) == Ok([])
    assert len(riot.requests) == 1


def test_match_ids_use_the_regional_host_and_ranked_solo() -> None:
    path = f"/lol/match/v5/matches/by-puuid/{puuid(1)}/ids"
    riot = FakeRiot({path: ["EUW1_2", "EUW1_1"]})
    assert run(source(riot).match_ids(puuid(1), 20)) == Ok(["EUW1_2", "EUW1_1"])
    request = riot.requests[0]
    assert request.url.host == "europe.api.riotgames.com"
    assert request.url.params["queue"] == "420"
    assert request.url.params["count"] == "20"


def test_fetch_builds_the_whole_game() -> None:
    result = run(source(full_game()).fetch("EUW1_1", keep))
    assert isinstance(result, Ok)
    game = result.value
    assert isinstance(game, Match)
    assert game.patch == "16.20"
    assert game.participants[0].player == puuid(1)
    assert game.items[0].item_id == 1037


def test_events_owned_by_participant_zero_are_dropped() -> None:
    skill = {"type": "SKILL_LEVEL_UP", "timestamp": 1_000, "participantId": 0, "skillSlot": 1}
    events = [buy(200_000, 0, 3865), skill, buy(300_000, 1, 1037)]
    riot = FakeRiot({MATCH: match_payload(), f"{MATCH}/timeline": timeline_payload(events=events)})
    result = run(source(riot).fetch("EUW1_1", keep))
    assert isinstance(result, Ok)
    game = result.value
    assert isinstance(game, Match)
    assert [e.item_id for e in game.items] == [1037]
    assert game.skills == ()


def test_event_owned_by_participant_eleven_is_rejected() -> None:
    events = [buy(300_000, 11, 1037)]
    riot = FakeRiot({MATCH: match_payload(), f"{MATCH}/timeline": timeline_payload(events=events)})
    result = run(source(riot).fetch("EUW1_1", keep))
    assert isinstance(result, Ok)
    assert isinstance(result.value, Rejected)


def test_monster_kills_by_the_neutral_team_are_dropped() -> None:
    events = [monster(500_000, 200, "HORDE"), monster(885_000, 300, "HORDE")]
    riot = FakeRiot({MATCH: match_payload(), f"{MATCH}/timeline": timeline_payload(events=events)})
    result = run(source(riot).fetch("EUW1_1", keep))
    assert isinstance(result, Ok)
    game = result.value
    assert isinstance(game, Match)
    assert [m.team for m in game.monsters] == [200]


def test_monster_kill_by_an_unknown_team_is_rejected() -> None:
    events = [monster(500_000, 400, "HORDE")]
    riot = FakeRiot({MATCH: match_payload(), f"{MATCH}/timeline": timeline_payload(events=events)})
    result = run(source(riot).fetch("EUW1_1", keep))
    assert isinstance(result, Ok)
    assert isinstance(result.value, Rejected)


def test_rejected_game_keeps_both_payloads() -> None:
    events = [monster(500_000, 400, "HORDE")]
    riot = FakeRiot({MATCH: match_payload(), f"{MATCH}/timeline": timeline_payload(events=events)})
    result = run(source(riot).fetch("EUW1_1", keep))
    assert isinstance(result, Ok)
    rejected = result.value
    assert isinstance(rejected, Rejected)
    assert (
        rejected.reason == "event.ELITE_MONSTER_KILL.killerTeamId.literal[100,200]: literal_error"
    )
    assert rejected.payload == {
        "match": match_payload(),
        "timeline": timeline_payload(events=events),
    }


def test_unreadable_match_is_rejected_without_fetching_its_timeline() -> None:
    payload = match_payload()
    del payload["info"]["gameVersion"]
    riot = FakeRiot({MATCH: payload, f"{MATCH}/timeline": timeline_payload()})
    result = run(source(riot).fetch("EUW1_1", keep))
    assert result == Ok(Rejected("info.gameVersion: missing", {"match": payload, "timeline": None}))
    assert riot.paths() == [MATCH]


def test_fetch_skips_the_timeline_of_unwanted_games() -> None:
    riot = full_game()
    result = run(source(riot).fetch("EUW1_1", lambda h: "nope" if h.queue == 420 else None))
    assert result == Ok(Skipped("nope"))
    assert riot.paths() == [MATCH]


def test_header_flags_remakes() -> None:
    riot = FakeRiot({MATCH: match_payload(early_surrender=True)})
    headers: list[MatchHeader] = []
    run(source(riot).fetch("EUW1_1", lambda h: headers.append(h) or "seen"))
    assert headers[0].remake


def test_inconsistent_game_is_rejected() -> None:
    payload = match_payload()
    payload["info"]["participants"][0]["teamPosition"] = ""
    riot = FakeRiot({MATCH: payload, f"{MATCH}/timeline": timeline_payload()})
    result = run(source(riot).fetch("EUW1_1", keep))
    assert isinstance(result, Ok)
    assert isinstance(result.value, Rejected)


def test_not_found() -> None:
    result = run(source(FakeRiot({})).fetch("EUW1_9", keep))
    assert isinstance(result, Err)
    assert result.error.kind == "not_found"


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_key_is_unauthorized_and_not_retried(status: int) -> None:
    riot = FakeRiot({MATCH: [httpx.Response(status, json={})]})
    result = run(source(riot).fetch("EUW1_1", keep))
    assert isinstance(result, Err)
    assert result.error.kind == "unauthorized"
    assert len(riot.requests) == 1


def test_429_waits_for_retry_after_then_succeeds() -> None:
    riot = FakeRiot(
        {
            CHALLENGER: [
                httpx.Response(429, headers={"Retry-After": "7"}),
                httpx.Response(200, json=league([puuid(1)])),
            ]
        }
    )
    clock = FakeClock()
    assert run(source(riot, clock).players("CHALLENGER", "I", 1)) == Ok([puuid(1)])
    assert clock.now >= 7


def test_server_errors_back_off_then_give_up() -> None:
    riot = FakeRiot({CHALLENGER: [httpx.Response(503)]})
    clock = FakeClock()
    src = source(riot, clock)
    result = run(src.players("CHALLENGER", "I", 1))
    assert isinstance(result, Err)
    assert result.error.kind == "unavailable"
    assert clock.slept == [2.0, 4.0, 8.0, 16.0, 32.0]
    assert src.stats().retries == 5


def test_transport_errors_are_retried() -> None:
    calls = 0

    def flaky(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(200, json=league([puuid(1)]))

    assert run(source(httpx.MockTransport(flaky)).players("CHALLENGER", "I", 1)) == Ok([puuid(1)])


def test_requests_respect_the_rate_limit() -> None:
    headers = {"X-App-Rate-Limit": "2:10", "X-App-Rate-Limit-Count": "1:10"}
    riot = FakeRiot({CHALLENGER: [httpx.Response(200, headers=headers, json=league([]))]})
    clock = FakeClock()
    src = source(riot, clock)
    for _ in range(3):
        run(src.players("CHALLENGER", "I", 1))
    assert clock.now >= 10


def test_key_goes_to_riot_only() -> None:
    riot = full_game()
    src = source(riot)
    run(src.fetch("EUW1_1", keep))
    run(src.static_data("16.20"))
    for request in riot.requests:
        riot_host = request.url.host.endswith("api.riotgames.com")
        assert ("x-riot-token" in request.headers) == riot_host


def test_static_data_for_the_patch() -> None:
    result = run(source(FakeRiot({})).static_data("16.20"))
    assert isinstance(result, Ok)
    assert result.value.version == DDRAGON_VERSION
    assert 3071 in result.value.completed_items


def test_static_data_for_an_unknown_patch() -> None:
    result = run(source(FakeRiot({})).static_data("9.1"))
    assert isinstance(result, Err)
    assert result.error.kind == "not_found"


def test_malformed_json_is_invalid() -> None:
    riot = FakeRiot({CHALLENGER: [httpx.Response(200, content=b"{not json")]})
    result = run(source(riot).players("CHALLENGER", "I", 1))
    assert isinstance(result, Err)
    assert result.error.kind == "invalid"
