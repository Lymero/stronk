"""`stronk-core watch-champselect` against lcu-mock's websocket (ADR-044): the real core
follows a whole champion select from pushed events, without polling, and picks the client up
when it starts after Stronk.

Needs the binary: `just core-e2e` builds it and sets STRONK_CORE_BIN.
"""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from lcu_mock import Mock, start

ROOT = Path(__file__).resolve().parents[3]
SESSION = ROOT / "tools/lcu_mock/sessions/ranked-jungle-leesin.json"
BINARY = os.environ.get("STRONK_CORE_BIN")

pytestmark = pytest.mark.skipif(BINARY is None, reason="run through `just core-e2e`")


def watcher(directory: Path, events: int) -> subprocess.Popen[str]:
    env = {
        **os.environ,
        "STRONK_LCU_LOCKFILE": str(directory / "lockfile"),
        "STRONK_LCU_CERT": str(directory / "root.pem"),
        "STRONK_DATA_DIR": str(ROOT / "fixtures/data"),
        "STRONK_DATA_KEY": str(ROOT / "fixtures/data.pub"),
    }
    return subprocess.Popen(  # noqa: S603 (our own binary)
        [str(BINARY), "watch-champselect", "--events", str(events)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )  # fmt: skip


def next_state(process: subprocess.Popen[str]) -> dict[str, Any]:
    assert process.stdout is not None
    line = process.stdout.readline()
    assert line, process.stderr.read() if process.stderr else "watcher ended"
    return json.loads(line)


def summary(state: dict[str, Any]) -> tuple[object, ...]:
    session = state["session"]
    return (state["champion"], session and session["phase"], session and session["locked"])


def follow(mock: Mock, process: subprocess.Popen[str]) -> list[tuple[object, ...]]:
    seen = [summary(next_state(process))]  # the state on connecting
    for _ in range(3):
        started = time.monotonic()
        mock.replay.advance()
        seen.append(summary(next_state(process)))
        assert time.monotonic() - started < 2.0  # pushed, not found by a slow poll
    return seen


EXPECTED = [
    (None, None, None),
    ("Graves", "PLANNING", False),
    ("LeeSin", "BAN_PICK", False),
    ("LeeSin", "FINALIZATION", True),
]


def test_follows_champion_select_from_pushed_events(tmp_path: Path) -> None:
    mock = start(SESSION, tmp_path)
    process = watcher(tmp_path, events=4)
    try:
        assert follow(mock, process) == EXPECTED
        assert process.wait(timeout=10) == 0
    finally:
        process.kill()
        mock.server.shutdown()


def test_picks_up_a_client_started_after_stronk(tmp_path: Path) -> None:
    process = watcher(tmp_path, events=4)  # no lockfile yet: the watcher retries
    time.sleep(1.5)
    assert process.poll() is None
    mock = start(SESSION, tmp_path)
    try:
        assert follow(mock, process) == EXPECTED
        assert process.wait(timeout=10) == 0
    finally:
        process.kill()
        mock.server.shutdown()
