"""Thresholds that only tighten: compare a TOML file with its committed version."""

from __future__ import annotations

import subprocess
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

type Entry = Mapping[str, Any]
type Direction = Literal["upper", "lower"]


def committed(path: Path, root: Path) -> dict[str, Any] | None:
    """The file as of HEAD, or None when there is no git history for it yet."""
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{path.relative_to(root).as_posix()}"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return tomllib.loads(result.stdout) if result.returncode == 0 else None


def loosened(
    old: list[Entry],
    new: list[Entry],
    *,
    key: str,
    limits: Mapping[str, Direction],
    enforce_default: bool,
) -> list[str]:
    """Names of entries that got looser: removed, a limit relaxed or dropped, enforcement off."""
    current = {e[key]: e for e in new}
    out: list[str] = []
    for before in old:
        name = before[key]
        after = current.get(name)
        if after is None:
            out.append(name)
            continue
        if before.get("enforce", enforce_default) and not after.get("enforce", enforce_default):
            out.append(name)
            continue
        for limit, direction in limits.items():
            was, now = before.get(limit), after.get(limit)
            if was is None:
                continue
            if now is None or (now > was if direction == "upper" else now < was):
                out.append(name)
                break
    return out


def unjustified(names: list[str], decisions: Path) -> list[str]:
    text = decisions.read_text() if decisions.is_file() else ""
    return [n for n in names if n not in text]
