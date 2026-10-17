"""ReportWriter: stage reports as pretty-printed JSON."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.ports import StoreError


class JsonReportWriter:
    def write(self, report: Mapping[str, object], path: Path) -> Result[Path, StoreError]:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
        except OSError as e:
            return Err(StoreError("invalid", f"cannot write {path}: {e}"))
        return Ok(path)
