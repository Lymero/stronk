"""`wpa.estimate`: WPA for every option at every decision point of a decision table."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from stronk_pipeline.application.registry import Command, CommandError
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.winprob import BaselineWinProb
from stronk_pipeline.domain.wpa.types import WpaSettings
from stronk_pipeline.ports import DecisionStore, Estimator


class WpaEstimateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: Annotated[str, Field(min_length=1, description="Decision table (Parquet)")]
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


class WpaEstimateResult(BaseModel):
    estimator: str
    decisions: int
    estimates: list[OptionEstimateRow]


def wpa_estimate_command(
    store: DecisionStore, estimators: Mapping[str, Estimator]
) -> Command[WpaEstimateParams, WpaEstimateResult]:
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
        # M0 stand-in: the winprob stage (M2) will supply WP from its trained model.
        wp = BaselineWinProb.fit(table).predict(table)
        settings = WpaSettings(bootstrap_samples=params.bootstrap_samples, seed=params.seed)
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
            )
            for e in estimator.estimate(table, wp, settings)
        ]
        return Ok(WpaEstimateResult(estimator=estimator.id, decisions=len(table), estimates=rows))

    return Command(
        id="wpa.estimate",
        summary="Estimate WPA per option and decision point from a decision table",
        params=WpaEstimateParams,
        result=WpaEstimateResult,
        run=run,
    )
