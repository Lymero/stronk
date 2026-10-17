"""Pipeline quality metrics for metrics/floors.toml, from the extract report of `just pipeline`.

pipeline_metrics.py <report.json> <out.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def metrics(report: dict[str, Any]) -> dict[str, float]:
    return {"pipeline.skip_rate": float(report["result"]["skip_rate"])}


def main(argv: list[str]) -> int:
    match argv:
        case [report, out]:
            values = metrics(json.loads(Path(report).read_text()))
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_text(json.dumps(values, indent=2) + "\n")
            return 0
        case _:
            print(__doc__, file=sys.stderr)
            return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
