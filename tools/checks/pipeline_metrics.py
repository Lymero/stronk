"""Pipeline quality metrics for metrics/floors.toml, from a stage's report.json.

pipeline_metrics.py <report.json> <out.json> [corpus]

extract: `pipeline.skip_rate`. winprob: `winprob.calibration_error` and `winprob.log_loss` of the
chosen model on the test matches. With a corpus name, each corpus has its own metrics and
floors (ADR-038): `extract.<corpus>.skip_rate`, `winprob.<corpus>.log_loss`...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def metrics(report: dict[str, Any], corpus: str | None = None) -> dict[str, float]:
    result = report["result"]
    match report["stage"]:
        case "extract":
            name = "pipeline.skip_rate" if corpus is None else f"extract.{corpus}.skip_rate"
            return {name: float(result["skip_rate"])}
        case "winprob":
            test = result["test"]
            prefix = "winprob." if corpus is None else f"winprob.{corpus}."
            return {
                f"{prefix}calibration_error": float(test["calibration_error"]),
                f"{prefix}log_loss": float(test["log_loss"]),
            }
        case stage:
            raise ValueError(f"no metrics for stage {stage!r}")


def main(argv: list[str]) -> int:
    match argv:
        case [report, out, *corpus] if len(corpus) <= 1:
            values = metrics(json.loads(Path(report).read_text()), *corpus)
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_text(json.dumps(values, indent=2) + "\n")
            return 0
        case _:
            print(__doc__, file=sys.stderr)
            return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
