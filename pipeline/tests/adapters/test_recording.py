import gzip
from pathlib import Path

import httpx
from riot_builders import league, match_payload, puuid, timeline_payload
from riot_server import FakeRiot, run, source

from stronk_pipeline.adapters.recording import (
    PUUID,
    PlaybackTransport,
    RecordingTransport,
    Scrubber,
    recording_key,
)
from stronk_pipeline.domain.match import Match
from stronk_pipeline.domain.result import Ok

CHALLENGER = "/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5"


def live() -> FakeRiot:
    return FakeRiot(
        {
            CHALLENGER: league([puuid(1)]),
            f"/lol/match/v5/matches/by-puuid/{puuid(1)}/ids": ["EUW1_1"],
            "/lol/match/v5/matches/EUW1_1": match_payload(),
            "/lol/match/v5/matches/EUW1_1/timeline": timeline_payload(minutes=3),
        }
    )


async def walk(src_transport: httpx.AsyncBaseTransport) -> tuple[list[str], Match]:
    src = source(src_transport)
    players = await src.players("CHALLENGER", "I", 1)
    assert isinstance(players, Ok)
    ids = await src.match_ids(players.value[0], 20)
    assert isinstance(ids, Ok)
    game = await src.fetch(ids.value[0], lambda _: None)
    assert isinstance(game, Ok)
    assert isinstance(game.value, Match)
    await src.close()
    return players.value, game.value


def record(directory: Path) -> None:
    run(walk(RecordingTransport(httpx.MockTransport(live()), directory, Scrubber(b"salt"))))


def test_playback_replays_a_recorded_walk(tmp_path: Path) -> None:
    record(tmp_path)
    players, game = run(walk(PlaybackTransport(tmp_path)))
    assert len(players) == 1
    assert players[0] != puuid(1)  # pseudonymised, and the walk still works
    assert game.match_id == "EUW1_1"
    assert {p.player for p in game.participants} != {puuid(i) for i in range(1, 11)}


def test_recordings_hold_no_identities_or_key(tmp_path: Path) -> None:
    record(tmp_path)
    contents = b"".join(gzip.decompress(f.read_bytes()) for f in tmp_path.glob("*.json.gz"))
    assert b"RGAPI" not in contents
    assert b"riotIdGameName" not in contents
    assert b"Player0" not in contents
    for i in range(1, 11):
        assert puuid(i).encode() not in contents


def test_pseudonyms_keep_the_shape_of_a_puuid() -> None:
    pseudonym = Scrubber(b"salt").pseudonym(puuid(1))
    assert PUUID.fullmatch(pseudonym)
    assert pseudonym == Scrubber(b"salt").pseudonym(puuid(1))
    assert pseudonym != Scrubber(b"other").pseudonym(puuid(1))


def test_unrecorded_requests_are_404(tmp_path: Path) -> None:
    result = run(source(PlaybackTransport(tmp_path)).players("CHALLENGER", "I", 1))
    assert not isinstance(result, Ok)


def test_key_ignores_query_order() -> None:
    a = httpx.URL("https://h/p?a=1&b=2")
    b = httpx.URL("https://h/p?b=2&a=1")
    assert recording_key(a) == recording_key(b)
    assert recording_key(a) != recording_key(httpx.URL("https://h/p?a=1&b=3"))
