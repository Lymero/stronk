"""WPA with each win probability model, to see what a better model changes downstream (ADR-084).

    uv run python tools/experiments/winprob/wpa_compare.py <frames.parquet> <decisions.parquet> \
        <model.json> <out> [name,...]

Runs production's `wpa.estimate` (v1-reference, its defaults) once per model, into
<out>/<name>/estimates.json; a model already estimated is skipped. `production` is the stored
`model.json` again, a check that this harness reproduces the published estimates; the others
are `wp_models`' (default: gam-odd-pairs and two linear LightGBM seeds), fitted on the frames'
training matches. Compare two runs with `compare_estimates.py`.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path

from wp_models import fitters, read_frames

from stronk_pipeline.adapters.json_estimates import JsonEstimateStore
from stronk_pipeline.adapters.parquet_store import ParquetDecisionStore, ParquetFrameStore
from stronk_pipeline.adapters.winprob_store import JsonWinProbStore
from stronk_pipeline.application.wpa_estimate import WpaEstimateParams, wpa_estimate_command
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.wpa.reference import ReferenceEstimatorV1
from stronk_pipeline.ports import StoreError, WinProbModel

DEFAULT = ("production", "gam-odd-pairs", "lightgbm-linear-s0", "lightgbm-linear-s1")


class Fixed:
    """A `WinProbStore` handing out one model, whatever the path."""

    def __init__(self, model: WinProbModel) -> None:
        self.model = model

    def load(self, path: Path) -> Result[WinProbModel, StoreError]:
        return Ok(self.model)

    def save(self, model: WinProbModel, path: Path) -> Result[Path, StoreError]:
        return Err(StoreError("invalid", "this store only hands out a model"))


def main(
    frames: Path, decisions: Path, production: Path, out: Path, names: tuple[str, ...]
) -> None:
    def stored() -> WinProbModel:
        match JsonWinProbStore().load(production):
            case Ok(value=model):
                return model
            case Err(error=e):
                raise SystemExit(f"{production}: {e.message}")

    todo = [n for n in names if not (out / n / "estimates.json").exists()]
    models: dict[str, Callable[[], WinProbModel]] = {"production": stored}
    if any(n != "production" for n in todo):
        models |= fitters(read_frames(frames))
    for name in todo:
        target = out / name / "estimates.json"
        start = time.time()
        model = models[name]()
        fitted = time.time()
        command = wpa_estimate_command(
            ParquetDecisionStore(),
            {"v1-reference": ReferenceEstimatorV1()},
            Fixed(model),
            JsonEstimateStore(),
            ParquetFrameStore(),
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        params = WpaEstimateParams(decisions=str(decisions), winprob="fixed", out=str(target))
        match command.run(params):
            case Ok(value=result):
                print(
                    f"{name}: fit {fitted - start:.0f}s, wpa {time.time() - fitted:.0f}s, "
                    f"{result.decisions:,} decisions, {len(result.estimates):,} estimates",
                    flush=True,
                )
            case Err(error=e):
                raise SystemExit(f"{name}: {e.message}")


if __name__ == "__main__":
    args = sys.argv[1:]
    chosen = tuple(args[4].split(",")) if len(args) > 4 else DEFAULT
    main(Path(args[0]), Path(args[1]), Path(args[2]), Path(args[3]), chosen)
