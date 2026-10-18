"""`wpa.estimate`: WPA for every option at every decision point of a decision table."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

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
from stronk_pipeline.domain.wpa.types import WpaSettings
from stronk_pipeline.ports import DecisionStore, EstimateStore, Estimator, WinProbStore


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
    """False-discovery-adjusted p-value of "no effect" (ADR-036)."""


class WpaEstimateResult(BaseModel):
    estimator: str
    decisions: int
    estimates: list[OptionEstimateRow]


def wpa_estimate_command(
    store: DecisionStore,
    estimators: Mapping[str, Estimator],
    models: WinProbStore,
    estimates_out: EstimateStore,
) -> Command[WpaEstimateParams, WpaEstimateResult]:
    def win_probability(
        table: DecisionTable, model_path: str | None
    ) -> Result[Floats, CommandError]:
        if model_path is None:
            return Ok(BaselineWinProb.fit(table).predict(table))
        match models.load(Path(model_path)):
            case Err(error=e):
                code = "not_found" if e.kind == "not_found" else "invalid_input"
                return Err(CommandError(code=code, message=e.message))
            case Ok(value=model):
                pass
        try:
            x = columns(table.features, table.feature_names, model.feature_names)
        except MissingFeaturesError as e:
            return Err(CommandError(code="invalid_input", message=f"{model_path}: {e}"))
        return Ok(symmetric(model.predict, x, table.minute))

    def run(params: WpaEstimateParams) -> Result[WpaEstimateResult, CommandError]:
        estimator = estimators.get(params.estimator)
        if estimator is None:
            known = ", ".join(sorted(estimators))
            message = f"unknown estimator {params.estimator!r}; known: {known}"
            return Err(CommandError(code="invalid_params", message=message))
        match store.read_decisions(Path(params.decisions)):
            case Err(error=e):
                code = "not_found" if e.kind == "not_found" else "invalid_input"
                return Err(CommandError(code=code, message=e.message))
            case Ok(value=table):
                pass
        if len(table) == 0:
            return Err(CommandError(code="invalid_input", message="decision table is empty"))
        match win_probability(table, params.winprob):
            case Err() as e:
                return e
            case Ok(value=wp):
                pass
        settings = WpaSettings(bootstrap_samples=params.bootstrap_samples, seed=params.seed)
        estimates = estimator.estimate(table, wp, settings)
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
