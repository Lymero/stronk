"""Pipeline quality metrics for metrics/floors.toml, from a stage's report.json.

pipeline_metrics.py <report.json> <out.json>

extract: `pipeline.skip_rate`. winprob: `winprob.calibration_error` and `winprob.log_loss` of the
chosen model on the test matches.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def metrics(report: dict[str, Any]) -> dict[str, float]:
    result = report["result"]
    match report["stage"]:
        case "extract":
            return {"pipeline.skip_rate": float(result["skip_rate"])}
        case "winprob":
            test = result["test"]
            return {
                "winprob.calibration_error": float(test["calibration_error"]),
                "winprob.log_loss": float(test["log_loss"]),
            }
        case stage:
            raise ValueError(f"no metrics for stage {stage!r}")


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
