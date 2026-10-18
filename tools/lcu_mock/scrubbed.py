"""The identifier rules for session recordings, as app/core/crates/lcu/src/scrub.rs applies
them: personal key names, UUIDs, long opaque tokens and Riot IDs (`name#tag`)."""

from __future__ import annotations

import re
from typing import Any, cast

PERSONAL_KEYS = (
    "puuid", "summonerid", "accountid", "playerid", "gamename", "tagline", "displayname",
    "summonername", "internalname", "obfuscated", "chat", "muc", "jwt", "password",
)  # fmt: skip
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
TOKEN = re.compile(r"[A-Za-z0-9\-_=./+]{32,}")
RIOT_ID = re.compile(r".+#[A-Za-z0-9]{2,5}")


def identifiers(value: Any, path: str = "") -> list[str]:
    """JSON paths of anything that looks like a personal identifier; empty means clean."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in cast("dict[str, Any]", value).items():
            child_path = f"{path}/{key}"
            if any(k in key.lower() for k in PERSONAL_KEYS):
                found.append(child_path)
            found += identifiers(child, child_path)
    elif isinstance(value, list):
        for i, item in enumerate(cast("list[Any]", value)):
            found += identifiers(item, f"{path}/{i}")
    elif isinstance(value, str) and (
        UUID.fullmatch(value) or TOKEN.fullmatch(value) or RIOT_ID.fullmatch(value)
    ):
        found.append(path)
    return found
