"""The real Rust core (`stronk-core`) against lcu-mock and the signed fixture data, end to end:
the session is stepped through and the core's view checked at each step.

Needs the binary: `just core-e2e` builds it and sets STRONK_CORE_BIN (part of `just check`).
"""

import json
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from lcu_mock import Mock, start

ROOT = Path(__file__).resolve().parents[3]
SESSION = ROOT / "tools/lcu_mock/sessions/ranked-jungle-leesin.json"
BINARY = os.environ.get("STRONK_CORE_BIN")

pytestmark = pytest.mark.skipif(BINARY is None, reason="run through `just core-e2e`")


@pytest.fixture
def mock(tmp_path: Path) -> Iterator[Mock]:
    running = start(SESSION, tmp_path)
    yield running
    running.server.shutdown()


def core(mock: Mock, command: str, params: object = None) -> tuple[int, Any]:
    env = {
        **os.environ,
        "STRONK_LCU_LOCKFILE": str(mock.lockfile),
        "STRONK_LCU_CERT": str(mock.root),
        "STRONK_DATA_DIR": str(ROOT / "fixtures/data"),
        "STRONK_DATA_KEY": str(ROOT / "fixtures/data.pub"),
    }
    done = subprocess.run(  # noqa: S603 (our own binary)
        [str(BINARY), "run", command, "--params", json.dumps(params or {})],
        capture_output=True, text=True, env=env, timeout=30, check=False,
    )  # fmt: skip
    return done.returncode, json.loads(done.stdout if done.returncode == 0 else done.stderr)


def step(mock: Mock) -> None:
    mock.replay.advance()


def test_follows_champion_select(mock: Mock) -> None:
    assert core(mock, "champselect.state") == (0, {"session": None, "champion": None, "role": None})
    step(mock)
    _, planning = core(mock, "champselect.state")
    assert (planning["champion"], planning["role"]) == ("Graves", "JUNGLE")
    assert planning["session"]["locked"] is False
    step(mock)
    _, hovering = core(mock, "champselect.state")
    assert hovering["champion"] == "LeeSin"
    assert hovering["session"]["phase"] == "BAN_PICK"
    step(mock)
    _, locked = core(mock, "champselect.state")
    assert locked["session"]["locked"] is True


def test_locked_champion_gets_its_verified_build(mock: Mock) -> None:
    for _ in range(3):
        step(mock)
    _, state = core(mock, "champselect.state")
    status, build = core(mock, "build.get", {"champion": state["champion"], "role": state["role"]})
    assert status == 0
    assert (build["champion"], build["role"], build["patch"]) == ("LeeSin", "JUNGLE", "16.20")


def test_a_wrong_password_is_an_error_not_a_crash(mock: Mock) -> None:
    text = mock.lockfile.read_text().rsplit(":", 2)
    mock.lockfile.write_text(f"{text[0]}:not-the-password:{text[2]}")
    status, error = core(mock, "champselect.state")
    assert status == 1
    assert error["code"] == "unavailable"
