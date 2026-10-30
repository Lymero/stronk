"""The real icons for the site's screenshot (`just site-shot`, ADR-066).

    site_icons.py --session runs/e2e-real/session.json --data runs/real/data --out runs/site-icons

The fake client serves placeholders at the paths its game data names. For the screenshot, this
fetches the real images for the same ids from CommunityDragon, the public mirror of the League
client's game data, and saves each under the path the fake client serves, so lcu-mock can serve
it instead (`STRONK_LCU_ASSETS`). Fetched: the session's champions, every rune, shard and rune
tree, every summoner spell, and the items and starts of the picks' builds. Kept in `runs/`, never
committed; already fetched files are kept. Network: this is a tool, not a test.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

from lcu_mock import Replay

BASE = "https://raw.communitydragon.org/{patch}/plugins/rcp-be-lol-game-data/global/default/"
PREFIX = "/lol-game-data/assets/"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "stronk-site-shot"})  # noqa: S310 (https only)
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read()


def url(base: str, path: str) -> str:
    """CommunityDragon's address for a client path: the same path, lower-cased, under its base."""
    return base + path.removeprefix(PREFIX).lower()


def ids_in_builds(session: dict[str, Any], data: Path) -> set[int]:
    """The items any slot or start of the picks' builds lists."""
    patch = sorted(p for p in data.iterdir() if p.is_dir())[-1]
    items: set[int] = set()
    for pick in session["picks"]:
        champion, role = pick.split("/")
        build = json.loads((patch / "all" / "master_plus" / champion / f"{role}.json").read_text())
        items |= {o["item"] for o in build["items"]}
        items |= {i for o in build.get("starts", []) for i in o["items"]}
    return items


def wanted(replay: Replay, session: dict[str, Any], data: Path) -> dict[str, tuple[str, int]]:
    """Each path the fake client serves that the screenshot can show: its kind and id."""
    out: dict[str, tuple[str, int]] = {}
    game = replay.game_data
    for perk in game[PREFIX + "v1/perks.json"]:  # type: ignore[union-attr]
        out[perk["iconPath"]] = ("perks", perk["id"])
    for style in game[PREFIX + "v1/perkstyles.json"]["styles"]:  # type: ignore[index]
        out[style["iconPath"]] = ("perkstyles", style["id"])
    for spell in game[PREFIX + "v1/summoner-spells.json"]:  # type: ignore[union-attr]
        out[spell["iconPath"]] = ("spells", spell["id"])
    items = ids_in_builds(session, data)
    for item in game[PREFIX + "v1/items.json"]:  # type: ignore[union-attr]
        if item["id"] in items:
            out[item["iconPath"]] = ("items", item["id"])
    for champion in replay.champions:
        if champion["id"] > 0:
            out[champion["squarePortraitPath"]] = ("champions", champion["id"])
    return out


def real_paths(base: str) -> dict[str, dict[int, str]]:
    """The client's own icon path for each id, by kind, from CommunityDragon's game data."""
    styles = json.loads(fetch(base + "v1/perkstyles.json"))["styles"]
    return {
        "perks": {p["id"]: p["iconPath"] for p in json.loads(fetch(base + "v1/perks.json"))},
        "perkstyles": {s["id"]: s["iconPath"] for s in styles},
        "spells": {
            s["id"]: s["iconPath"] for s in json.loads(fetch(base + "v1/summoner-spells.json"))
        },
        "items": {i["id"]: i["iconPath"] for i in json.loads(fetch(base + "v1/items.json"))},
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Real icons for the site's screenshot")
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    session = json.loads(args.session.read_text())
    replay = Replay.load(args.session)
    patch = sorted(p.name for p in args.data.iterdir() if p.is_dir())[-1]
    base = BASE.format(patch=patch)
    try:
        real = real_paths(base)
    except OSError:
        base = BASE.format(patch="latest")
        real = real_paths(base)
    fetched = missing = 0
    for path, (kind, id_) in wanted(replay, session, args.data).items():
        target = args.out / path.lstrip("/")
        if target.exists():
            continue
        source = (
            real.get(kind, {}).get(id_)
            if kind != "champions"
            else f"{PREFIX}v1/champion-icons/{id_}.png"
        )
        if not source:
            missing += 1
            continue
        try:
            image = fetch(url(base, source))
        except OSError as e:
            print(f"site-icons: {kind} {id_}: {e}", file=sys.stderr)
            missing += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(image)
        fetched += 1
    print(f"site-icons: {fetched} fetched, {missing} missing, into {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
