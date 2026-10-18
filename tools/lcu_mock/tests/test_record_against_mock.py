"""`stronk-core record-champselect` against lcu-mock serving a session full of personal data:
the saved recording replays the same champion select and contains none of it.

Needs the binary: `just core-e2e` builds it and sets STRONK_CORE_BIN.
"""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from lcu_mock import start
from scrubbed import identifiers

ROOT = Path(__file__).resolve().parents[3]
SESSION = ROOT / "tools/lcu_mock/sessions/ranked-jungle-leesin.json"
BINARY = os.environ.get("STRONK_CORE_BIN")

pytestmark = pytest.mark.skipif(BINARY is None, reason="run through `just core-e2e`")


def with_personal_data(session: dict[str, Any]) -> dict[str, Any]:
    """What a real client adds: ids, PUUIDs, names, chat credentials, timers."""
    steps: list[dict[str, Any]] = []
    for step in session["steps"]:
        s: dict[str, Any] | None = step["session"]
        if s is not None:
            chat = {"multiUserChatId": "c1~abc", "multiUserChatPassword": "secret"}
            timer = {**s["timer"], "internalNowInEpochMs": 1760000000000}
            team = [
                {**m, "summonerId": 100 + i, "puuid": "2f1c0f1e-8c4b-4f3a-9a3c-1b2c3d4e5f60",
                 "gameName": f"Player{i}", "tagLine": "EUW"}
                for i, m in enumerate(s["myTeam"])
            ]  # fmt: skip
            s = {**s, "gameId": 7212345678, "chatDetails": chat, "timer": timer, "myTeam": team}
        steps.append({**step, "session": s})
    return {**session, "steps": steps}


def test_records_one_champion_select_without_personal_data(tmp_path: Path) -> None:
    dirty = tmp_path / "dirty.json"
    dirty.write_text(json.dumps(with_personal_data(json.loads(SESSION.read_text()))))
    assert identifiers(json.loads(dirty.read_text()))  # the served session is full of them
    mock = start(dirty, tmp_path / "mock")
    out = tmp_path / "recorded.json"
    env = {
        **os.environ,
        "STRONK_LCU_LOCKFILE": str(mock.lockfile),
        "STRONK_LCU_CERT": str(mock.root),
    }
    recorder = subprocess.Popen(  # noqa: S603 (our own binary)
        [str(BINARY), "record-champselect", "--out", str(out), "--timeout-minutes", "1"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )  # fmt: skip
    try:
        for _ in range(3):  # planning, hovering, locked
            time.sleep(1.2)
            mock.replay.advance()
        time.sleep(1.2)
        mock.replay.step = 0  # back in the lobby: champion select is over
        stdout, stderr = recorder.communicate(timeout=30)
    finally:
        recorder.kill()
        mock.server.shutdown()
    assert recorder.returncode == 0, stderr
    assert "saved" in stdout
    recorded = json.loads(out.read_text())
    assert identifiers(recorded) == []
    names = [step["name"] for step in recorded["steps"]]
    assert names[0] == "lobby"
    assert [n.split()[0] for n in names[1:]] == ["PLANNING", "BAN_PICK", "FINALIZATION"]
    assert {c["alias"] for c in recorded["champions"]} == {"LeeSin", "Graves", "Jinx", "Thresh"}
    last = recorded["steps"][-1]["session"]
    assert last["myTeam"][1] == {"cellId": 1, "championId": 64, "championPickIntent": 0,
                                 "assignedPosition": "jungle"}  # fmt: skip
