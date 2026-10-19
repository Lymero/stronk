"""The real Rust core (`stronk-core`) against lcu-mock and the signed fixture data, end to end:
the session is stepped through and the core's view checked at each step.

Needs the binary: `just core-e2e` builds it and sets STRONK_CORE_BIN (part of `just check`).
"""

import json
import os
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from lcu_mock import Mock, start
from serve_data import server

ROOT = Path(__file__).resolve().parents[3]
SESSION = ROOT / "tools/lcu_mock/sessions/ranked-jungle-leesin.json"
BINARY = os.environ.get("STRONK_CORE_BIN")

pytestmark = pytest.mark.skipif(BINARY is None, reason="run through `just core-e2e`")


@pytest.fixture
def mock(tmp_path: Path) -> Iterator[Mock]:
    running = start(SESSION, tmp_path)
    yield running
    running.server.shutdown()


def core(
    mock: Mock, command: str, params: object = None, data: dict[str, str] | None = None
) -> tuple[int, Any]:
    env = {
        **os.environ,
        "STRONK_LCU_LOCKFILE": str(mock.lockfile),
        "STRONK_LCU_CERT": str(mock.root),
        "STRONK_DATA_DIR": str(ROOT / "fixtures/data"),
        "STRONK_DATA_KEY": str(ROOT / "fixtures/data.pub"),
        **(data or {}),
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


def test_names_come_from_the_clients_game_data(mock: Mock) -> None:
    status, names = core(mock, "names.get")
    assert status == 0, names
    assert names["champions"]["64"] == "Lee Sin"
    assert names["rune_styles"]["8000"] == "Precision"
    assert names["runes"]["8010"] == "Conqueror"
    assert names["spells"]["11"] == "Smite"
    assert names["items"]["6692"] == "Eclipse"


def test_icons_come_from_the_clients_game_data(mock: Mock) -> None:
    params = {"champions": [64], "runes": [8010], "rune_styles": [8000], "spells": [4],
              "items": [6692, 999999]}  # fmt: skip
    status, icons = core(mock, "icons.get", params)
    assert status == 0, icons
    png = "data:image/png;base64,iVBORw0KGgo"  # the PNG signature
    for kind, id_ in [("champions", 64), ("runes", 8010), ("rune_styles", 8000), ("spells", 4),
                      ("items", 6692)]:  # fmt: skip
        assert icons[kind][str(id_)].startswith(png), kind
    assert "999999" not in icons["items"]  # unknown to the client: left out


def test_a_wrong_password_is_an_error_not_a_crash(mock: Mock) -> None:
    text = mock.lockfile.read_text().rsplit(":", 2)
    mock.lockfile.write_text(f"{text[0]}:not-the-password:{text[2]}")
    status, error = core(mock, "champselect.state")
    assert status == 1
    assert error["code"] == "unavailable"


RECORDED = ROOT / "tools/lcu_mock/sessions/custom-2026-10-19.json"


def test_follows_a_recorded_champion_select(tmp_path: Path) -> None:
    """A real client's champion select (custom game, recorded on Windows, scrubbed): the core
    sees the hover, then the lock-in, with the role the client assigned."""
    mock = start(RECORDED, tmp_path)
    try:
        seen: list[tuple[Any, Any, Any]] = []
        for _ in mock.replay.steps:
            status, state = core(mock, "champselect.state")
            assert status == 0, state
            session = state["session"]
            seen.append((state["champion"], state["role"], session and session["locked"]))
            mock.replay.advance()
    finally:
        mock.server.shutdown()
    assert seen == [
        (None, None, None),
        (None, "BOTTOM", False),
        ("Diana", "BOTTOM", False),
        ("Diana", "BOTTOM", True),
        ("Diana", "BOTTOM", True),
    ]


def test_data_over_http_from_serve_data_then_offline_from_the_cache(
    mock: Mock, tmp_path: Path
) -> None:
    httpd = server(ROOT / "fixtures/data", "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    data = {
        "STRONK_DATA_DIR": f"http://127.0.0.1:{httpd.server_port}",
        "STRONK_CACHE_DIR": str(tmp_path / "cache"),
    }
    leesin = {"champion": "LeeSin", "role": "JUNGLE"}
    try:
        status, online = core(mock, "data.status", data=data)
        assert (status, online["patch"]) == (0, "16.20")
        assert core(mock, "build.get", leesin, data=data)[0] == 0
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert core(mock, "data.status", data=data) == (0, online)
    status, build = core(mock, "build.get", leesin, data=data)
    assert (status, build["champion"], build["patch"]) == (0, "LeeSin", "16.20")
