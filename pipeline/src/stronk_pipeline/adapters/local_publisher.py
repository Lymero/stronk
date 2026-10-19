"""Publisher on a local directory with the CDN's layout (`dist/data/` by default, ADR-017).

A patch is replaced as a whole: the new files go to a hidden sibling directory, which then takes
the patch directory's place. Readers see the old patch or the new one, never a mix. Then
`index.json` (index.v1) is rewritten to list every patch directory with a manifest, so a client
over HTTP can find the newest one; it is replaced in one rename too.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
from collections.abc import Mapping
from pathlib import Path

from stronk_contracts.index_v1 import Index
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.ports import StoreError

PATCH = re.compile(r"[0-9]{1,3}\.[0-9]{1,3}")
PATH = re.compile(r"[A-Za-z0-9_+-][A-Za-z0-9._+-]*(/[A-Za-z0-9_+-][A-Za-z0-9._+-]*)*")
"""As manifest.v1's FileEntry.path: no segment starts with '.', so no '..' and no hidden files."""
MANIFEST = "manifest.json"
INDEX = "index.json"


class LocalPublisher:
    def __init__(self, root: Path) -> None:
        self._root = root

    def publish(self, patch: str, files: Mapping[str, bytes]) -> Result[list[str], StoreError]:
        if not PATCH.fullmatch(patch):
            return Err(StoreError("invalid", f"unexpected patch {patch!r}"))
        unsafe = [p for p in files if not PATH.fullmatch(p)]
        if unsafe:
            return Err(StoreError("invalid", f"unsafe paths: {', '.join(sorted(unsafe))}"))
        target = self._root / patch
        staging = self._root / f".{patch}.new-{secrets.token_hex(4)}"
        retired = self._root / f".{patch}.old-{secrets.token_hex(4)}"
        try:
            for path, data in files.items():
                file = staging / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
            if target.exists():
                target.rename(retired)
            staging.rename(target)
        except OSError as e:
            shutil.rmtree(staging, ignore_errors=True)
            if retired.exists() and not target.exists():
                retired.rename(target)  # put the previous patch back
            return Err(StoreError("invalid", f"cannot publish {patch} to {self._root}: {e}"))
        shutil.rmtree(retired, ignore_errors=True)
        try:
            index = self._write_index()
        except OSError as e:
            return Err(StoreError("invalid", f"cannot write the index in {self._root}: {e}"))
        return Ok(sorted([*(str(target / p) for p in files), str(index)]))

    def _write_index(self) -> Path:
        patches = sorted(
            (
                d.name
                for d in self._root.iterdir()
                if PATCH.fullmatch(d.name) and (d / MANIFEST).is_file()
            ),
            key=lambda p: tuple(int(n) for n in p.split(".")),
        )
        index = Index.model_validate({"schemaVersion": 1, "patches": patches})
        data = json.dumps(
            index.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":")
        )
        target = self._root / INDEX
        staging = self._root / f".{INDEX}.new-{secrets.token_hex(4)}"
        try:
            staging.write_text(data + "\n", encoding="utf-8")
            staging.replace(target)
        finally:
            staging.unlink(missing_ok=True)
        return target
