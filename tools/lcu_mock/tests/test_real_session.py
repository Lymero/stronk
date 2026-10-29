import gzip
import json
from pathlib import Path
from typing import Any, cast

import pytest
from lcu_mock import Replay
from real_session import builds, session, sparsest


def data(tmp: Path) -> tuple[Path, Path]:
    folder = tmp / "data" / "16.20" / "all" / "master_plus"
    for alias, role, games in [("LeeSin", "JUNGLE", 4190), ("MonkeyKing", "TOP", 3)]:
        (folder / alias).mkdir(parents=True, exist_ok=True)
        (folder / alias / f"{role}.json").write_text(json.dumps({"games": games}))
    static = tmp / "16.20.json.gz"
    doc = {
        "champions": {
            "64": {"champion_id": 64, "name": "Lee Sin"},
            "62": {"champion_id": 62, "name": "Wukong"},
        },
        "items": {
            "3071": {"item_id": 3071, "name": "Black Cleaver"},
            "9999": {"item_id": 9999, "name": "New Item"},
        },
    }
    static.write_bytes(gzip.compress(json.dumps(doc).encode()))
    return tmp / "data", static


def test_one_locked_step_per_pick_after_a_lobby(tmp_path: Path) -> None:
    root, static = data(tmp_path)
    doc = session(root, static, ["LeeSin/JUNGLE", "MonkeyKing/TOP"])
    assert [s["name"] for s in doc["steps"]] == [
        "lobby",
        "locked LeeSin JUNGLE",
        "locked MonkeyKing TOP",
    ]
    team = doc["steps"][2]["session"]["myTeam"][0]
    assert (team["championId"], team["assignedPosition"]) == (62, "top")
    assert {"id": 62, "alias": "MonkeyKing", "name": "Wukong"} in doc["champions"]


def test_without_picks_the_popular_boards_and_the_sparsest(tmp_path: Path) -> None:
    root, static = data(tmp_path)
    assert sparsest(builds(root)) == "MonkeyKing/TOP"
    with pytest.raises(ValueError, match="Jinx/BOTTOM: no build"):  # not in this small data set
        session(root, static, None)


def test_lcu_mock_serves_every_item_the_session_names(tmp_path: Path) -> None:
    root, static = data(tmp_path)
    file = tmp_path / "session.json"
    file.write_text(json.dumps(session(root, static, ["LeeSin/JUNGLE"])))
    items = cast(
        list[dict[str, Any]], Replay.load(file).game_data["/lol-game-data/assets/v1/items.json"]
    )
    assert {
        "id": 9999,
        "name": "New Item",
        "iconPath": "/lol-game-data/assets/ASSETS/Items/Icons2D/9999.png",
    } in items
    assert any(i["id"] == 3071 for i in items)  # lcu-mock's own items stay
    assert "/lol-game-data/assets/v1/perks.json" in Replay.load(file).game_data
