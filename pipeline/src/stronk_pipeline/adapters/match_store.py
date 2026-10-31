"""MatchStore on a directory. One gzipped JSON file per game, written atomically, so a crawl
can stop at any point and resume without losing or corrupting anything.

    <dir>/matches/<match_id>.json.gz   validated domain Match, players pseudonymous
    <dir>/static/<patch>.json.gz       Data Dragon data for the patch
    <dir>/skipped.jsonl                games looked at and passed over, with the reason
    <dir>/quarantine/<match_id>.json.gz  games that failed validation: payloads and reason,
                                       identities scrubbed (gitignored, never packed)
    <dir>/.salt                        pseudonym key: never published or committed
"""

from __future__ import annotations

import gzip
import json
import re
import secrets
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from pydantic import TypeAdapter, ValidationError

from stronk_pipeline.adapters.recording import IDENTITY_KEYS, PUUID
from stronk_pipeline.domain.bracket import DIAMOND, LEGACY, MASTER_PLUS
from stronk_pipeline.domain.match import InvalidMatchError, Match, pseudonym
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.static import StaticData
from stronk_pipeline.ports import Quarantined, StoreError

MATCH_ID = re.compile(r"[A-Z0-9]+_[0-9]+")
PATCH = re.compile(r"[0-9]+\.[0-9]+")
BRACKET_FILE = "bracket.txt"
"""The crawl's elo bracket, one word (ADR-076); absent in crawls from before brackets."""
_MATCH = TypeAdapter(Match)
_STATIC = TypeAdapter(StaticData)


class FileMatchStore:
    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def known(self) -> Result[frozenset[str], StoreError]:
        stored = {p.name.removesuffix(".json.gz") for p in self._matches_dir().glob("*.json.gz")}
        held = {p.name.removesuffix(".json.gz") for p in self._quarantine_dir().glob("*.json.gz")}
        match self._skips():
            case Err() as e:
                return e
            case Ok(value=skips):
                return Ok(frozenset(stored | held | {match_id for match_id, _ in skips}))

    def skip_counts(self) -> Result[dict[str, int], StoreError]:
        match self._skips():
            case Err() as e:
                return e
            case Ok(value=skips):
                return Ok(dict(sorted(Counter(reason for _, reason in skips).items())))

    def _skips(self) -> Result[list[tuple[str, str]], StoreError]:
        try:
            lines = self._skipped_file().read_text().splitlines()
        except FileNotFoundError:
            lines = []
        except OSError as e:
            return Err(StoreError("invalid", f"cannot read {self._skipped_file()}: {e}"))
        skips: list[tuple[str, str]] = []
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue  # a line cut short by an interrupted write
            match record:
                case {"id": str(match_id), "reason": str(reason)}:
                    skips.append((match_id, reason))
                case _:
                    pass
        return Ok(skips)

    def salt(self) -> Result[bytes, StoreError]:
        path = self._dir / ".salt"
        try:
            if not path.exists():
                self._dir.mkdir(parents=True, exist_ok=True)
                _write_atomic(path, secrets.token_hex(32).encode())
            return Ok(bytes.fromhex(path.read_text().strip()))
        except (OSError, ValueError) as e:
            return Err(StoreError("invalid", f"cannot read or create {path}: {e}"))

    def count(self) -> int:
        return sum(1 for _ in self._matches_dir().glob("*.json.gz"))

    def put(self, match: Match) -> Result[None, StoreError]:
        if not MATCH_ID.fullmatch(match.match_id):
            return Err(StoreError("invalid", f"unexpected match id {match.match_id!r}"))
        path = self._matches_dir() / f"{match.match_id}.json.gz"
        return _write_gzip(path, _MATCH.dump_json(match))

    def skip(self, match_id: str, reason: str) -> Result[None, StoreError]:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            with self._skipped_file().open("a") as f:
                f.write(json.dumps({"id": match_id, "reason": reason}) + "\n")
        except OSError as e:
            return Err(StoreError("invalid", f"cannot write {self._skipped_file()}: {e}"))
        return Ok(None)

    def quarantine(
        self, match_id: str, reason: str, payload: Mapping[str, object]
    ) -> Result[None, StoreError]:
        if not MATCH_ID.fullmatch(match_id):
            return Err(StoreError("invalid", f"unexpected match id {match_id!r}"))
        match self.salt():
            case Err() as e:
                return e
            case Ok(value=salt):
                pass
        record = {"id": match_id, "reason": reason, "payload": _scrub(dict(payload), salt)}
        return _write_gzip(self._quarantine_path(match_id), json.dumps(record).encode())

    def quarantined(self) -> Result[list[Quarantined], StoreError]:
        held: list[Quarantined] = []
        for path in sorted(self._quarantine_dir().glob("*.json.gz")):
            try:
                record: object = json.loads(gzip.decompress(path.read_bytes()))
            except (OSError, ValueError) as e:
                return Err(StoreError("invalid", f"{path}: {type(e).__name__}"))
            entry = cast("dict[str, object]", record) if isinstance(record, dict) else {}
            match_id, reason, payload = entry.get("id"), entry.get("reason"), entry.get("payload")
            if not (
                isinstance(match_id, str) and isinstance(reason, str) and isinstance(payload, dict)
            ):
                return Err(StoreError("invalid", f"{path}: not a quarantine entry"))
            held.append(Quarantined(match_id, reason, cast("dict[str, object]", payload)))
        return Ok(held)

    def release(self, match_id: str) -> Result[None, StoreError]:
        if not MATCH_ID.fullmatch(match_id):
            return Err(StoreError("invalid", f"unexpected match id {match_id!r}"))
        path = self._quarantine_path(match_id)
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            return Err(StoreError("invalid", f"cannot remove {path}: {e}"))
        return Ok(None)

    def has_static(self, patch: str) -> bool:
        return self._static_path(patch).is_file()

    def bracket(self) -> Result[str, StoreError]:
        path = self._dir / BRACKET_FILE
        if not path.is_file():
            return Ok(LEGACY)
        try:
            bracket = path.read_text().strip()
        except OSError as e:
            return Err(StoreError("invalid", f"cannot read {path}: {e}"))
        if bracket not in (MASTER_PLUS, DIAMOND):
            return Err(StoreError("invalid", f"{path}: unknown bracket {bracket!r}"))
        return Ok(bracket)

    def set_bracket(self, bracket: str) -> Result[None, StoreError]:
        path = self._dir / BRACKET_FILE
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_text(bracket + "\n")
        except OSError as e:
            return Err(StoreError("invalid", f"cannot write {path}: {e}"))
        return Ok(None)

    def patches(self) -> list[str]:
        found = [p.name.removesuffix(".json.gz") for p in (self._dir / "static").glob("*.json.gz")]
        return sorted((p for p in found if PATCH.fullmatch(p)), key=_patch_key)

    def put_static(self, patch: str, static: StaticData) -> Result[None, StoreError]:
        if not PATCH.fullmatch(patch):
            return Err(StoreError("invalid", f"unexpected patch {patch!r}"))
        return _write_gzip(self._static_path(patch), _STATIC.dump_json(static))

    def read_static(self) -> Result[dict[str, StaticData], StoreError]:
        statics: dict[str, StaticData] = {}
        for path in sorted((self._dir / "static").glob("*.json.gz")):
            try:
                statics[path.name.removesuffix(".json.gz")] = _STATIC.validate_json(
                    gzip.decompress(path.read_bytes())
                )
            except (OSError, ValueError, ValidationError) as e:
                return Err(StoreError("invalid", f"{path}: {type(e).__name__}"))
        return Ok(statics)

    def read_matches(self) -> Result[tuple[list[Match], int], StoreError]:
        if not self._dir.is_dir():
            return Err(StoreError("not_found", f"no crawl directory at {self._dir}"))
        matches: list[Match] = []
        unreadable = 0
        for path in sorted(self._matches_dir().glob("*.json.gz")):
            try:
                matches.append(_MATCH.validate_json(gzip.decompress(path.read_bytes())))
            except (OSError, ValueError, ValidationError, InvalidMatchError):
                unreadable += 1
        return Ok((matches, unreadable))

    def _matches_dir(self) -> Path:
        return self._dir / "matches"

    def _skipped_file(self) -> Path:
        return self._dir / "skipped.jsonl"

    def _quarantine_dir(self) -> Path:
        return self._dir / "quarantine"

    def _quarantine_path(self, match_id: str) -> Path:
        return self._quarantine_dir() / f"{match_id}.json.gz"

    def _static_path(self, patch: str) -> Path:
        return self._dir / "static" / f"{patch}.json.gz"


def _scrub(value: object, salt: bytes) -> object:
    """Riot JSON without names or Riot ids, PUUIDs replaced by their pseudonyms under `salt`:
    the same ids `Match.pseudonymized` gives stored games."""
    if isinstance(value, dict):
        items = cast("dict[str, object]", value).items()
        return {k: _scrub(v, salt) for k, v in items if k not in IDENTITY_KEYS}
    if isinstance(value, list):
        return [_scrub(v, salt) for v in cast("list[object]", value)]
    if isinstance(value, str) and PUUID.fullmatch(value):
        return pseudonym(value, salt)
    return value


def _patch_key(patch: str) -> tuple[int, ...]:
    return tuple(int(p) for p in patch.split("."))


def _write_gzip(path: Path, data: bytes) -> Result[None, StoreError]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(path, gzip.compress(data, mtime=0))
    except OSError as e:
        return Err(StoreError("invalid", f"cannot write {path}: {e}"))
    return Ok(None)


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
