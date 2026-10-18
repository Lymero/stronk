"""Every committed session recording is free of personal identifiers."""

import json
from pathlib import Path

import pytest
from scrubbed import identifiers

SESSIONS = sorted((Path(__file__).resolve().parents[1] / "sessions").glob("*.json"))


@pytest.mark.parametrize("session", SESSIONS, ids=[p.name for p in SESSIONS])
def test_recording_has_no_identifiers(session: Path) -> None:
    assert identifiers(json.loads(session.read_text())) == []


def test_the_rules_catch_what_the_client_sends() -> None:
    dirty = {
        "myTeam": [
            {"cellId": 1, "summonerId": 1, "puuid": "x", "gameName": "Me", "tagLine": "EUW"}
        ],
        "chatDetails": {"multiUserChatPassword": "pw"},
        "note": "Faker#KR1",
        "id": "2f1c0f1e-8c4b-4f3a-9a3c-1b2c3d4e5f60",
        "token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl",
    }
    assert set(identifiers(dirty)) >= {
        "/myTeam/0/summonerId", "/myTeam/0/puuid", "/myTeam/0/gameName", "/myTeam/0/tagLine",
        "/chatDetails", "/note", "/id", "/token",
    }  # fmt: skip
    assert identifiers({"timer": {"phase": "FINALIZATION"}, "assignedPosition": "utility"}) == []
