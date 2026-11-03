"""How well each win probability model predicts, against production's logistic one (ADR-084).

    uv run python tools/experiments/winprob/fit_compare.py <frames.parquet> <out> [name,...]

Fits every model of `wp_models` (or those named) on the training matches, reports on the
validation and test matches, every prediction symmetric as in production, and appends one JSON
line per model to <out>/results.jsonl; a model already there is skipped, so a stopped run
resumes. `gain` is the drop in test log loss from `logistic`, `gain_se` its standard error with
frames clustered by match.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from wp_models import Frames, Indices, fitters, read_frames

from stronk_pipeline.domain.calibration import calibration, log_loss
from stronk_pipeline.domain.logistic import Floats
from stronk_pipeline.domain.winprob import TEST, VALID, symmetric
from stronk_pipeline.ports import WinProbModel

BASELINE = "logistic"


def predict(model: WinProbModel, frames: Frames, rows: Indices) -> Floats:
    p = symmetric(model.predict, frames.x[rows], frames.minute[rows])
    return np.clip(p, 1e-12, 1 - 1e-12)


def losses(y: Floats, p: Floats) -> Floats:
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def gain(frames: Frames, rows: Indices, loss: Floats, base: Floats) -> tuple[float, float]:
    """Mean loss drop from the baseline and its standard error, frames clustered by match."""
    d = loss - base
    groups = frames.match[rows]
    sums = np.bincount(groups, weights=d)
    counts = np.bincount(groups)
    used = counts > 0
    n = int(used.sum())
    mean = float(d.mean())
    resid = sums[used] - mean * counts[used]
    se = float(np.sqrt(n / (n - 1) * np.sum(resid**2)) / len(d))
    return -mean, se


def evaluate(name: str, model: WinProbModel, frames: Frames, fit_s: float) -> dict[str, object]:
    row: dict[str, object] = {"name": name, "fit_s": round(fit_s, 1)}
    valid, test = frames.rows(VALID), frames.rows(TEST)
    row["valid_log_loss"] = round(log_loss(frames.outcome[valid], predict(model, frames, valid)), 6)
    y, p = frames.outcome[test], predict(model, frames, test)
    report = calibration(y, p, frames.minute[test])
    row |= {
        "test_log_loss": round(report.log_loss, 6),
        "test_brier": round(report.brier, 6),
        "test_calibration_error": round(report.calibration_error, 5),
        "test_calibration_30plus": round(report.by_minute[-1].calibration_error, 5),
    }
    return row


def main(frames_path: Path, out: Path, only: set[str] | None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    results = out / "results.jsonl"
    baseline_loss = out / f"{BASELINE}-test-loss.npy"
    done: set[str] = (
        {json.loads(line)["name"] for line in results.read_text().splitlines()}
        if results.exists()
        else set()
    )
    t0 = time.time()
    frames = read_frames(frames_path)
    test = frames.rows(TEST)
    print(f"{len(frames.outcome):,} frames read in {time.time() - t0:.0f}s", flush=True)
    models = fitters(frames)
    names = [BASELINE, *(n for n in models if n != BASELINE)]
    for name in names:
        if name in done or (only is not None and name not in only and name != BASELINE):
            continue
        start = time.time()
        model = models[name]()
        row = evaluate(name, model, frames, time.time() - start)
        loss = losses(frames.outcome[test], predict(model, frames, test))
        if name == BASELINE:
            np.save(baseline_loss, loss)
        else:
            g, se = gain(frames, test, loss, np.load(baseline_loss))
            row |= {"gain": round(g, 6), "gain_se": round(se, 6)}
        print(json.dumps(row), flush=True)
        with results.open("a") as f:
            f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main(
        Path(sys.argv[1]),
        Path(sys.argv[2]),
        set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None,
    )
