"""`build.import` from the real core into lcu-mock (ADR-043): a full Stronk rune page, an
existing Stronk page replaced, the player's pages and item sets untouched, Flash kept on the
player's key. The build is the signed fixture data's Lee Sin jungle.

Needs the binary: `just core-e2e` builds it and sets STRONK_CORE_BIN.
"""

import json
import os
import subprocess
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from lcu_mock import THEIR_SET, Mock, start

ROOT = Path(__file__).resolve().parents[3]
SESSION = ROOT / "tools/lcu_mock/sessions/ranked-jungle-leesin.json"
BUILD = json.loads((ROOT / "fixtures/data/16.20/all/master_plus/LeeSin/JUNGLE.json").read_text())
BINARY = os.environ.get("STRONK_CORE_BIN")
FLASH, SMITE, IGNITE = 4, 11, 14

pytestmark = pytest.mark.skipif(BINARY is None, reason="run through `just core-e2e`")


@pytest.fixture
def mock(tmp_path: Path) -> Iterator[Mock]:
    running = start(SESSION, tmp_path)
    for _ in range(3):
        running.replay.advance()  # Lee Sin locked in the jungle
    yield running
    running.server.shutdown()


def import_build(mock: Mock, backups: Path | None = None) -> dict[str, Any]:
    env = {
        **os.environ,
        "STRONK_BACKUP_DIR": str(backups or mock.lockfile.parent / "backups"),
        "STRONK_LCU_LOCKFILE": str(mock.lockfile),
        "STRONK_LCU_CERT": str(mock.root),
        "STRONK_DATA_DIR": str(ROOT / "fixtures/data"),
        "STRONK_DATA_KEY": str(ROOT / "fixtures/data.pub"),
    }
    done = subprocess.run(  # noqa: S603 (our own binary)
        [str(BINARY), "run", "build.import"], capture_output=True, text=True, env=env, timeout=30,
        check=False,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def stronk_pages(mock: Mock) -> list[dict[str, Any]]:
    return [p for p in mock.replay.pages if str(p.get("name", "")).startswith("Stronk: ")]


def test_imports_the_full_popular_rune_page(mock: Mock) -> None:
    result = import_build(mock)
    assert result["runes"] == {
        "status": "imported",
        "name": "Stronk: LeeSin JUNGLE",
        "label": "popular",
    }
    (page,) = stronk_pages(mock)
    expected = BUILD["runes"][0]["page"]
    assert page["selectedPerkIds"] == expected["perks"]  # all nine, not per-slot picks
    assert (page["primaryStyleId"], page["subStyleId"]) == (
        expected["primaryStyle"],
        expected["subStyle"],
    )
    assert page["current"] is True


def test_replaces_an_existing_stronk_page(mock: Mock) -> None:
    mock.replay.pages.append({"id": 150, "name": "Stronk: Graves JUNGLE", "isEditable": True})
    import_build(mock)
    assert [p["name"] for p in stronk_pages(mock)] == ["Stronk: LeeSin JUNGLE"]
    deletes = [r["path"] for r in mock.replay.recorded if r["method"] == "DELETE"]
    assert deletes == ["/lol-perks/v1/pages/150"]


def test_leaves_the_players_pages_alone(mock: Mock) -> None:
    theirs = deepcopy(mock.replay.pages)
    import_build(mock)
    assert [p for p in mock.replay.pages if p["id"] in (101, 102)] == theirs


def test_passes_the_players_item_sets_through_byte_for_byte(mock: Mock) -> None:
    result = import_build(mock)
    assert result["item_set"]["status"] == "imported"
    written = str(mock.replay.item_sets)
    # Unknown fields, spacing, `2.50` and the `\u00e9` escape arrive as the client sent them.
    assert written.startswith(f'{{"accountId":1,"itemSets":[{THEIR_SET},')
    assert written.endswith('],"timestamp":0}')
    assert [s["title"] for s in json.loads(written)["itemSets"]] == [
        "My Lee Sin",
        "Stronk: LeeSin JUNGLE",
    ]


def test_backs_up_the_players_item_sets_before_writing(mock: Mock, tmp_path: Path) -> None:
    original = str(mock.replay.item_sets)
    result = import_build(mock, backups=tmp_path / "backups")
    (backup,) = (tmp_path / "backups").glob("item-sets-*.json")
    assert backup.read_text() == original
    assert result["item_set_backup"] == str(backup)


def test_writes_no_item_set_when_reading_them_fails(mock: Mock) -> None:
    mock.replay.item_sets_fail = True
    original = str(mock.replay.item_sets)
    result = import_build(mock)
    assert result["item_set"]["status"] == "skipped"
    assert "nothing written" in result["item_set"]["reason"]
    assert str(mock.replay.item_sets) == original
    assert not [r for r in mock.replay.recorded if "/lol-item-sets/" in r["path"]]
    assert result["runes"]["status"] == "imported"  # the rest of the import still happens


def test_never_deletes_a_players_page_to_make_room(mock: Mock) -> None:
    mock.replay.page_capacity = 1  # the player's one editable page fills it
    theirs = deepcopy(mock.replay.pages)
    result = import_build(mock)
    assert result["runes"]["status"] == "skipped"
    assert mock.replay.pages == theirs
    assert not [r for r in mock.replay.recorded if "/lol-perks/" in r["path"]]


@pytest.mark.parametrize(
    ("current", "expected"),
    [((FLASH, IGNITE), (FLASH, SMITE)), ((IGNITE, FLASH), (SMITE, FLASH))],
    ids=["flash-on-D", "flash-on-F"],
)
def test_keeps_flash_on_the_players_key(
    mock: Mock, current: tuple[int, int], expected: tuple[int, int]
) -> None:
    assert sorted(BUILD["spells"][0]["spells"]) == [FLASH, SMITE]
    mock.replay.spells = current
    result = import_build(mock)
    assert mock.replay.spells == expected
    assert result["spells"]["status"] == "imported"
