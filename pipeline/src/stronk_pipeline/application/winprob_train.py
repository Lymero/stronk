"""`winprob.train`: per-minute frames -> win probability model and its calibration report.

Matches are split into train, validation and test parts. Every learner is fitted on the
training part; the one with the lowest log loss on the validation part is kept. Test numbers,
for every candidate, are measured on games no candidate saw and played no part in the choice.
"""

from __future__ import annotations

import itertools
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Annotated

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from stronk_pipeline.application.registry import Command, CommandError
from stronk_pipeline.domain.calibration import CalibrationReport, calibration, log_loss
from stronk_pipeline.domain.frames import FrameTable
from stronk_pipeline.domain.logistic import Floats
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.winprob import (
    TEST,
    TRAIN,
    VALID,
    WP_FEATURES,
    WP_MONOTONE,
    MissingFeaturesError,
    Rows,
    columns,
    match_parts,
    symmetric,
)
from stronk_pipeline.ports import (
    FrameStore,
    ReportWriter,
    StoreError,
    WinProbLearner,
    WinProbModel,
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
        match frames.frame_chunks(Path(params.frames)):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=loaders):
                pass
        match _layout(loaders, params.frames):
            case Err() as e:
                return e
            case Ok(value=(parts, sizes)):
                pass
        rows = {p: Rows(sizes[p], _loader(loaders, parts, p)) for p in (TRAIN, VALID, TEST)}
        try:
            models = {
                learner.id: learner.fit(
                    rows[TRAIN], rows[VALID], WP_FEATURES, WP_MONOTONE, params.seed
                )
                for learner in learners
            }
            candidates = {
                name: _candidate(m, rows[VALID], rows[TEST]) for name, m in models.items()
            }
        except _ChunkError as e:
            return Err(_error(e.error))
        chosen = min(candidates, key=lambda name: candidates[name].valid_log_loss)
        out = Path(params.out)
        match store.save(models[chosen], out / "model.json"):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=model_path):
                pass
        counts = Counter(parts.values())
        result = WinProbTrainResult(
            matches={"train": counts[TRAIN], "valid": counts[VALID], "test": counts[TEST]},
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


type _Loader = Callable[[], Result[FrameTable, StoreError]]


class _ChunkError(Exception):
    """A part of the frames that read before and doesn't now: ends the run with its error."""

    def __init__(self, error: StoreError) -> None:
        super().__init__(error.message)
        self.error = error


def _layout(
    loaders: Sequence[_Loader], frames: str
) -> Result[tuple[dict[str, int], dict[int, tuple[int, ...]]], CommandError]:
    """The part of every match (`match_parts`), and the rows of each part in each chunk: one
    pass over the frames, holding only their match ids (ADR-081)."""
    matches: list[NDArray[np.str_]] = []
    for load in loaders:
        match load():
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=table):
                pass
        try:
            columns(table.features, table.feature_names, WP_FEATURES)
        except MissingFeaturesError as e:
            return Err(CommandError(code="invalid_input", message=f"{frames}: {e}"))
        matches.append(table.match_id)
    try:
        parts = match_parts(itertools.chain.from_iterable(m.tolist() for m in matches))
    except ValueError as e:
        return Err(CommandError(code="invalid_input", message=f"{frames}: {e}"))
    of_rows = [_parts_of(ids, parts) for ids in matches]
    sizes = {
        p: tuple(int(np.count_nonzero(of == p)) for of in of_rows) for p in (TRAIN, VALID, TEST)
    }
    return Ok((parts, sizes))


def _parts_of(match_id: NDArray[np.str_], parts: dict[str, int]) -> NDArray[np.int64]:
    """The part of each row, looked up once per match."""
    unique, inverse = np.unique(match_id, return_inverse=True)
    return np.array([parts[m] for m in unique.tolist()], dtype=np.int64)[inverse]


def _loader(
    loaders: Sequence[_Loader], parts: dict[str, int], part: int
) -> Callable[[int], tuple[Floats, Floats, Floats]]:
    """Chunk `i` of one part of the split, read again from its frames each time."""

    def load(i: int) -> tuple[Floats, Floats, Floats]:
        match loaders[i]():
            case Err(error=e):
                raise _ChunkError(e)
            case Ok(value=table):
                pass
        mine = _parts_of(table.match_id, parts) == part
        x = columns(table.features, table.feature_names, WP_FEATURES)
        return x[mine], table.minute[mine], table.outcome.astype(np.float64)[mine]

    return load


def _candidate(model: WinProbModel, valid: Rows, test: Rows) -> Candidate:
    """A model's validation log loss and test calibration, predicted a chunk at a time."""
    y, p, _ = _predictions(model, valid)
    ty, tp, minute = _predictions(model, test)
    return Candidate(
        valid_log_loss=round(log_loss(y, p), 6),
        test=_calibration(calibration(ty, tp, minute)),
    )


def _predictions(model: WinProbModel, rows: Rows) -> tuple[Floats, Floats, Floats]:
    """Outcomes, predictions and minutes of every row."""
    parts = [(y, symmetric(model.predict, x, m), m) for x, m, y in rows.chunks()]
    return (
        np.concatenate([y for y, _, _ in parts]),
        np.concatenate([p for _, p, _ in parts]),
        np.concatenate([m for _, _, m in parts]),
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
