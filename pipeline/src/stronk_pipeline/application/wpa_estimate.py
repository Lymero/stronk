"""`wpa.estimate`: WPA for every option at every decision point of a decision table."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from stronk_pipeline.application.registry import Command, CommandError
from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.logistic import Floats
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.winprob import (
    BaselineWinProb,
    MissingFeaturesError,
    columns,
    symmetric,
)
from stronk_pipeline.domain.wpa.outcome import windowed_outcome
from stronk_pipeline.domain.wpa.pooling import pool_by_class
from stronk_pipeline.domain.wpa.types import WpaSettings
from stronk_pipeline.ports import (
    DecisionStore,
    EstimateStore,
    Estimator,
    FrameStore,
    WinProbModel,
    WinProbStore,
)


class WpaEstimateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: Annotated[str, Field(min_length=1, description="Decision table (Parquet)")]
    out: str | None = None
    """Also write the estimates to this file, for `publish`."""
    winprob: str | None = None
    """Model from `winprob.train`. Without one, a logistic baseline is fitted on the decisions
    themselves (synthetic games have no frames to train on)."""
    estimator: str = "v1-reference"
    bootstrap_samples: Annotated[int, Field(ge=10, le=10_000)] = 200
    seed: int = 0
    window: Annotated[float, Field(gt=0, le=60)] | None = None
    """Score against the team's WP this many minutes later instead of the final result
    (ADR-039). Needs `frames` and `winprob`."""
    frames: str | None = None
    """Frame table (Parquet) of the same games, for `window`."""
    group: Literal["champion", "class"] = "champion"
    """`class` pools every champion of a class at each decision point, champion as a feature."""

    @model_validator(mode="after")
    def _window_needs_frames(self) -> Self:
        if self.window is not None and (self.frames is None or self.winprob is None):
            raise ValueError("window needs frames and winprob")
        return self


class OptionEstimateRow(BaseModel):
    champion: str
    role: str
    slot: int
    option: str
    wpa: float | None
    ci: tuple[float, float] | None
    n: int
    flags: list[str]
    q: float | None
    """False-discovery-adjusted p-value of no difference with `versus` (ADR-036)."""
    versus: str | None


class WpaEstimateResult(BaseModel):
    estimator: str
    decisions: int
    estimates: list[OptionEstimateRow]


def wpa_estimate_command(
    store: DecisionStore,
    estimators: Mapping[str, Estimator],
    models: WinProbStore,
    estimates_out: EstimateStore,
    frames: FrameStore,
) -> Command[WpaEstimateParams, WpaEstimateResult]:
    def inputs(
        params: WpaEstimateParams,
    ) -> Result[tuple[DecisionTable, Floats, Floats | None], CommandError]:
        """The decisions, WP at each and what scores measure against it (None: the result)."""
        match store.read_decisions(Path(params.decisions)):
            case Err(error=e):
                return Err(_error(e.kind, e.message))
            case Ok(value=table):
                pass
        if len(table) == 0:
            return Err(CommandError(code="invalid_input", message="decision table is empty"))
        if params.winprob is None:
            return Ok((table, BaselineWinProb.fit(table).predict(table), None))
        match models.load(Path(params.winprob)):
            case Err(error=e):
                return Err(_error(e.kind, e.message))
            case Ok(value=model):
                pass
        try:
            wp = _predict(model, table.features, table.feature_names, table.minute)
        except MissingFeaturesError as e:
            return Err(CommandError(code="invalid_input", message=f"{params.winprob}: {e}"))
        if params.window is None or params.frames is None:
            return Ok((table, wp, None))
        match frames.read_frames(Path(params.frames)):
            case Err(error=e):
                return Err(_error(e.kind, e.message))
            case Ok(value=f):
                pass
        try:
            frame_wp = _predict(model, f.features, f.feature_names, f.minute)
        except MissingFeaturesError as e:
            return Err(CommandError(code="invalid_input", message=f"{params.frames}: {e}"))
        return Ok((table, wp, windowed_outcome(table, f, frame_wp, params.window)))

    def run(params: WpaEstimateParams) -> Result[WpaEstimateResult, CommandError]:
        estimator = estimators.get(params.estimator)
        if estimator is None:
            known = ", ".join(sorted(estimators))
            message = f"unknown estimator {params.estimator!r}; known: {known}"
            return Err(CommandError(code="invalid_params", message=message))
        match inputs(params):
            case Err() as e:
                return e
            case Ok(value=(table, wp, target)):
                pass
        settings = WpaSettings(bootstrap_samples=params.bootstrap_samples, seed=params.seed)
        if params.group == "class":
            pooled = pool_by_class(table)
            reordered = None if target is None else target[pooled.order]
            estimates = estimator.estimate(
                pooled.table, wp[pooled.order], settings, reordered, pooled.strata
            )
        else:
            estimates = estimator.estimate(table, wp, settings, target)
        if params.out is not None:
            match estimates_out.write_estimates(estimator.id, estimates, Path(params.out)):
                case Err(error=e):
                    return Err(CommandError(code="invalid_input", message=e.message))
                case Ok():
                    pass
        rows = [
            OptionEstimateRow(
                champion=e.champion,
                role=e.role,
                slot=e.slot,
                option=e.option,
                wpa=e.wpa,
                ci=e.ci,
                n=e.n,
                flags=sorted(e.flags),
                q=e.q,
                versus=e.versus,
            )
            for e in estimates
        ]
        return Ok(WpaEstimateResult(estimator=estimator.id, decisions=len(table), estimates=rows))

    return Command(
        id="wpa.estimate",
        summary="Estimate WPA per option and decision point from a decision table",
        params=WpaEstimateParams,
        result=WpaEstimateResult,
        run=run,
    )


def _predict(model: WinProbModel, features: Floats, names: Sequence[str], minute: Floats) -> Floats:
    return symmetric(model.predict, columns(features, names, model.feature_names), minute)


def _error(kind: str, message: str) -> CommandError:
    return CommandError(
        code="not_found" if kind == "not_found" else "invalid_input", message=message
    )
