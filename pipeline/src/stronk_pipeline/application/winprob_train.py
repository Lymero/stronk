"""`winprob.train`: per-minute frames -> win probability model and its calibration report.

Matches are split into train, validation and test parts. Every learner is fitted on the
training part; the one with the lowest log loss on the validation part is kept. Test numbers,
for every candidate, are measured on games no candidate saw and played no part in the choice.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from stronk_pipeline.application.registry import Command, CommandError
from stronk_pipeline.domain.calibration import CalibrationReport, calibration, log_loss
from stronk_pipeline.domain.logistic import Floats
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.winprob import (
    WP_FEATURES,
    WP_MONOTONE,
    MissingFeaturesError,
    columns,
    split_by_match,
    symmetric,
)
from stronk_pipeline.ports import (
    FrameStore,
    ReportWriter,
    StoreError,
    WinProbLearner,
    WinProbStore,
)


class WinProbTrainParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frames: Annotated[str, Field(min_length=1, description="Frame table (Parquet)")]
    out: Annotated[str, Field(min_length=1, description="Output directory")]
    seed: int = 0


class BinRow(BaseModel):
    low: float
    high: float
    n: int
    predicted: float
    observed: float


class BandRow(BaseModel):
    minutes: tuple[float, float | None]
    n: int
    log_loss: float
    calibration_error: float


class Calibration(BaseModel):
    n: int
    log_loss: float
    brier: float
    calibration_error: float
    bins: list[BinRow]
    by_minute: list[BandRow]


class Candidate(BaseModel):
    valid_log_loss: float
    test: Calibration


class WinProbTrainResult(BaseModel):
    matches: dict[str, int]
    """Matches in each part: train, valid, test."""
    chosen: str
    """The learner kept: lowest validation log loss."""
    test: Calibration
    """The chosen model on the test part."""
    candidates: dict[str, Candidate]
    outputs: list[str]


def winprob_train_command(
    frames: FrameStore,
    learners: Sequence[WinProbLearner],
    store: WinProbStore,
    reports: ReportWriter,
) -> Command[WinProbTrainParams, WinProbTrainResult]:
    def run(params: WinProbTrainParams) -> Result[WinProbTrainResult, CommandError]:
        match frames.read_frames(Path(params.frames)):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=table):
                pass
        try:
            x = columns(table.features, table.feature_names, WP_FEATURES)
            split = split_by_match(table.match_id)
        except (MissingFeaturesError, ValueError) as e:
            return Err(CommandError(code="invalid_input", message=f"{params.frames}: {e}"))
        y = table.outcome.astype(np.float64)

        def part(mask: np.ndarray[tuple[int], np.dtype[np.bool_]]) -> tuple[Floats, Floats, Floats]:
            return x[mask], table.minute[mask], y[mask]

        train, valid, test = part(split.train), part(split.valid), part(split.test)
        models = {
            learner.id: learner.fit(train, valid, WP_FEATURES, WP_MONOTONE, params.seed)
            for learner in learners
        }
        candidates = {
            name: Candidate(
                valid_log_loss=round(log_loss(valid[2], symmetric(m.predict, *valid[:2])), 6),
                test=_calibration(calibration(test[2], symmetric(m.predict, *test[:2]), test[1])),
            )
            for name, m in models.items()
        }
        chosen = min(candidates, key=lambda name: candidates[name].valid_log_loss)
        out = Path(params.out)
        match store.save(models[chosen], out / "model.json"):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=model_path):
                pass
        result = WinProbTrainResult(
            matches={
                name: len(set(table.match_id[mask].tolist()))
                for name, mask in (
                    ("train", split.train),
                    ("valid", split.valid),
                    ("test", split.test),
                )
            },
            chosen=chosen,
            test=candidates[chosen].test,
            candidates=candidates,
            outputs=[str(model_path)],
        )
        report = {
            "stage": "winprob",
            "params": params.model_dump(),
            "features": [*WP_FEATURES, "minute"],
            "result": result.model_dump(),
        }
        match reports.write(report, out / "report.json"):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=report_path):
                result.outputs.append(str(report_path))
        return Ok(result)

    return Command(
        id="winprob.train",
        summary="Train the win probability model on frames and report its calibration",
        params=WinProbTrainParams,
        result=WinProbTrainResult,
        run=run,
    )


def _calibration(report: CalibrationReport) -> Calibration:
    return Calibration(
        n=report.n,
        log_loss=round(report.log_loss, 6),
        brier=round(report.brier, 6),
        calibration_error=round(report.calibration_error, 6),
        bins=[
            BinRow(
                low=b.low,
                high=b.high,
                n=b.n,
                predicted=round(b.predicted, 4),
                observed=round(b.observed, 4),
            )
            for b in report.bins
        ],
        by_minute=[
            BandRow(
                minutes=(b.low, None if b.high == float("inf") else b.high),
                n=b.n,
                log_loss=round(b.log_loss, 6),
                calibration_error=round(b.calibration_error, 6),
            )
            for b in report.by_minute
        ],
    )


def _error(error: StoreError) -> CommandError:
    code = "not_found" if error.kind == "not_found" else "invalid_input"
    return CommandError(code=code, message=error.message)
