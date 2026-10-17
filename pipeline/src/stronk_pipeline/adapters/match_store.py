"""MatchStore on a directory. One gzipped JSON file per game, written atomically, so a crawl
can stop at any point and resume without losing or corrupting anything.

    <dir>/matches/<match_id>.json.gz   validated domain Match, players pseudonymous
    <dir>/static/<patch>.json.gz       Data Dragon data for the patch
    <dir>/skipped.jsonl                games looked at and rejected, with the reason
    <dir>/.salt                        pseudonym key: never published or committed
"""

from __future__ import annotations

import gzip
import json
import re
import secrets
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from stronk_pipeline.domain.match import InvalidMatchError, Match
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.static import StaticData
from stronk_pipeline.ports import StoreError

MATCH_ID = re.compile(r"[A-Z0-9]+_[0-9]+")
PATCH = re.compile(r"[0-9]+\.[0-9]+")
_MATCH = TypeAdapter(Match)
_STATIC = TypeAdapter(StaticData)


class FileMatchStore:
    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def known(self) -> Result[frozenset[str], StoreError]:
        stored = {p.name.removesuffix(".json.gz") for p in self._matches_dir().glob("*.json.gz")}
        try:
            lines = self._skipped_file().read_text().splitlines()
        except FileNotFoundError:
            lines = []
        except OSError as e:
            return Err(StoreError("invalid", f"cannot read {self._skipped_file()}: {e}"))
        skipped: set[str] = set()
        for line in lines:
            try:
                record = json.loads(line)
            except ValueError:
                continue  # a line cut short by an interrupted write
            match record:
                case {"id": str(match_id)}:
                    skipped.add(match_id)
                case _:
                    pass
        return Ok(frozenset(stored | skipped))

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

    def has_static(self, patch: str) -> bool:
        return self._static_path(patch).is_file()

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

    def _static_path(self, patch: str) -> Path:
        return self._dir / "static" / f"{patch}.json.gz"


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
