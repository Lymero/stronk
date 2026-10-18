"""lcu-mock: lockfile, TLS chained to its root, auth, replay and recording."""

import base64
import json
import ssl
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from lcu_mock import Mock, start

SESSION = Path(__file__).resolve().parents[1] / "sessions" / "ranked-jungle-leesin.json"


@pytest.fixture
def mock(tmp_path: Path) -> Iterator[Mock]:
    running = start(SESSION, tmp_path)
    yield running
    running.server.shutdown()


def call(mock: Mock, path: str, method: str = "GET", body: object = None,
         credential: str | None = None) -> tuple[int, Any]:  # fmt: skip
    _, _, port, secret, _ = mock.lockfile.read_text().split(":")
    context = ssl.create_default_context(cafile=str(mock.root))  # trusts the mock's root only
    request = urllib.request.Request(
        f"https://127.0.0.1:{port}{path}",
        method=method,
        data=None if body is None else json.dumps(body).encode(),
    )
    token = base64.b64encode(f"riot:{credential or secret}".encode()).decode()
    request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request, context=context, timeout=5) as response:  # noqa: S310
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def test_writes_a_client_lockfile(mock: Mock) -> None:
    name, _, port, password, protocol = mock.lockfile.read_text().split(":")
    assert (name, int(port), protocol) == ("LeagueClient", mock.port, "https")
    assert len(password) >= 16


def test_needs_the_lockfile_password(mock: Mock) -> None:
    assert call(mock, "/mock/state", credential="wrong")[0] == 401


def test_replays_the_session_step_by_step(mock: Mock) -> None:
    assert call(mock, "/lol-champ-select/v1/session")[0] == 404  # lobby: not in champ select
    assert call(mock, "/mock/step", "POST")[1]["step"] == 1
    status, session = call(mock, "/lol-champ-select/v1/session")
    assert status == 200
    assert session["timer"]["phase"] == "PLANNING"
    for _ in range(5):
        call(mock, "/mock/step", "POST")  # stays on the last step
    assert call(mock, "/mock/state")[1]["name"] == "locked Lee Sin"


def test_serves_the_champion_summary(mock: Mock) -> None:
    _, champions = call(mock, "/lol-game-data/assets/v1/champion-summary.json")
    assert {"id": 64, "alias": "LeeSin", "name": "Lee Sin"} in champions


def test_records_what_the_app_writes(mock: Mock) -> None:
    page = {"name": "Stronk", "primaryStyleId": 8000}
    assert call(mock, "/lol-perks/v1/pages", "POST", page)[0] == 200
    assert call(mock, "/mock/recorded")[1] == [
        {"method": "POST", "path": "/lol-perks/v1/pages", "body": page}
    ]
