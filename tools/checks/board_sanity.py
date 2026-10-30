"""What a player would see on every board of a data set, checked for things that must not show
(`just e2e-real`, ADR-061).

    board_sanity.py --core <stronk-core> --data runs/real/data --key runs/real/data.pub

Runs `build.plan` for every champion and role of the newest patch (one `stronk-core serve`)
and checks each slot the board draws: the runes, the spells, the start, the first components,
the boots, every item slot and rune row.

Failures (exit 1), each with up to five examples:
- `few-games-false`: "few games" under an option with at least 300 games, the pipeline's own
  `low_sample` line: it isn't short of games (Triumph read "few games" at 4,067).
- `almost-always-few-games`: "almost always" under an option with fewer than 300 games: on a
  thin board it means too little data, not that everyone takes it (Ahri jungle, 1 game).
- `baseline-not-first`: a "most played" or "almost always" row that isn't the slot's first.
- `clear-off-scale`: a clear result or a best bet not measured against the most played option.
- `no-pick`: a slot with options and nothing the import writes, or more than one.
- `choice-mismatch`: the plan's choice isn't the row marked chosen (for runes, the page of its
  keystone: the rows' best bets change the page itself, ADR-065).

Reported, not failed: rows with a number against another option than the most played, which
the board leaves blank (`off-scale`).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

ENOUGH_GAMES = 300
"""`WpaSettings`' `low_sample` line: below it an option really has few games."""
EXAMPLES = 5


def plans(core: Path, data: Path, key: Path) -> list[tuple[str, dict[str, Any]]]:
    """`build.plan` for every build file of the newest patch, labelled `Champion/ROLE`."""
    patch = sorted(p for p in data.iterdir() if p.is_dir())[-1]
    picks = sorted(
        (f.parent.name, f.stem) for f in (patch / "all" / "master_plus").glob("*/*.json")
    )
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "STRONK_DATA_DIR": str(data), "STRONK_DATA_KEY": str(key),
               "STRONK_CACHE_DIR": str(Path(tmp) / "cache")}  # fmt: skip
        lines = "".join(
            json.dumps({"id": "build.plan", "params": {"champion": c, "role": r}}) + "\n"
            for c, r in picks
        )
        done = subprocess.run(
            [str(core), "serve"], input=lines, capture_output=True, text=True, env=env, check=False
        )
    answers = [json.loads(line) for line in done.stdout.splitlines() if line.strip()]
    if len(answers) != len(picks):
        raise RuntimeError(
            f"stronk-core serve answered {len(answers)} of {len(picks)}: {done.stderr}"
        )
    out: list[tuple[str, dict[str, Any]]] = []
    for (c, r), answer in zip(picks, answers, strict=True):
        if not answer["ok"]:
            raise RuntimeError(f"{c}/{r}: {answer['error']}")
        out.append((f"{c}/{r}", answer["value"]))
    return out


def slots(plan: dict[str, Any]) -> list[tuple[str, dict[str, Any], Any]]:
    """Each slot the board draws: its name, its ranked rows, and the plan's choice if any."""
    alt = plan["alternatives"]
    choice = {i["slot"]: i["value"] for i in plan["items"]}
    out = [
        ("runes", alt["runes"], plan["runes"]["value"] if plan["runes"] else None),
        ("spells", alt["spells"], plan["spells"]["value"] if plan["spells"] else None),
        ("start", alt["start"], plan["start"]["value"] if plan.get("start") else None),
        (
            "components",
            alt["components"],
            plan["components"]["value"] if plan.get("components") else None,
        ),
        ("boots", alt["boots"], plan["boots"]["value"] if plan.get("boots") else None),
    ]
    out += [(f"item {s['slot']}", s, choice.get(s["slot"])) for s in alt["items"]]
    out += [
        (f"{r['kind']} {r.get('style') or ''} {r.get('row') or ''}".strip(), r, None)
        for r in alt["rune_rows"]
    ]
    return out


def check(
    labelled: list[tuple[str, dict[str, Any]]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    failures: dict[str, list[str]] = defaultdict(list)
    reported: dict[str, list[str]] = defaultdict(list)
    for label, plan in labelled:
        for name, slot, choice in slots(plan):
            rows = slot["rows"]
            where = f"{label} {name}"
            for i, row in enumerate(rows):
                what = f"{where}: {row['value']}"
                if row["confidence"] == "too_few_games" and row["played"] >= ENOUGH_GAMES:
                    failures["few-games-false"].append(f"{what}, {row['played']} games")
                if row["confidence"] == "almost_always" and row["played"] < ENOUGH_GAMES:
                    failures["almost-always-few-games"].append(f"{what}, {row['played']} games")
                if i > 0 and row["confidence"] in ("most_played", "almost_always"):
                    failures["baseline-not-first"].append(what)
                if (
                    row["confidence"] in ("clearly_better", "clearly_worse", "best_bet")
                    and row["versus"] != "most_played"
                ):
                    failures["clear-off-scale"].append(what)
                if (
                    row["wpa"] is not None
                    and row["versus"] != "most_played"
                    and row["confidence"] == "no_clear_difference"
                ):
                    reported["off-scale"].append(what)
            chosen = [r for r in rows if r["chosen"]]
            if rows and choice is not None and len(chosen) != 1:
                failures["no-pick"].append(f"{where}: {len(chosen)} chosen")
            mismatch = (
                chosen[0]["value"]["perks"][0] != choice["perks"][0]
                if name == "runes" and chosen and choice is not None
                else chosen and choice is not None and chosen[0]["value"] != choice
            )
            if mismatch:
                failures["choice-mismatch"].append(f"{where}: {chosen[0]['value']} vs {choice}")
    return failures, reported


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Check every board of a data set")
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        labelled = plans(args.core, args.data.resolve(), args.key.resolve())
    except (OSError, RuntimeError, json.JSONDecodeError, IndexError) as e:
        print(f"board-sanity: {e}", file=sys.stderr)
        return 1
    failures, reported = check(labelled)
    print(f"board-sanity: {len(labelled)} boards")
    for name, found in [*failures.items(), *reported.items()]:
        kind = "FAIL" if name in failures else "note"
        print(f"  {kind}  {name}: {len(found)}")
        for example in found[:EXAMPLES]:
            print(f"          {example}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
