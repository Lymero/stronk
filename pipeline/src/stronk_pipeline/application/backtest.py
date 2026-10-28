"""`backtest.run`: one patch's WPA contrasts against the next patch's (ADR-055)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from stronk_pipeline.application.registry import Command, CommandError
from stronk_pipeline.domain.backtest import Backtest, backtest
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.wpa.types import OptionEstimate, WpaSettings
from stronk_pipeline.ports import EstimateStore, ReportWriter, StoreError


class BacktestParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    earlier: Annotated[str, Field(min_length=1, description="Estimates of the earlier patch")]
    later: Annotated[str, Field(min_length=1, description="Estimates of the later patch")]
    out: str | None = None
    """Also write the report (`report.json`, for metrics/floors.toml) into this directory."""
    fdr: Annotated[float, Field(gt=0, lt=1)] = WpaSettings().fdr
    """A contrast with q at most this is a claim."""


class ClaimRow(BaseModel):
    champion: str
    role: str
    slot: int
    option: str
    versus: str
    earlier: float
    earlier_q: float
    later: float | None
    later_q: float | None


class BacktestResult(BaseModel):
    earlier_contrasts: int
    later_contrasts: int
    paired: int
    sign_agreement: float | None
    clear: int
    clear_sign_agreement: float | None
    correlation: float | None
    slope: float | None
    claims: list[ClaimRow]
    claims_held: int
    claims_replicated: int
    outputs: list[str] = []


def backtest_command(
    estimates: EstimateStore, reports: ReportWriter
) -> Command[BacktestParams, BacktestResult]:
    def read(path: str) -> Result[list[OptionEstimate], CommandError]:
        match estimates.read_estimates(Path(path)):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=rows):
                return Ok(rows)

    def run(params: BacktestParams) -> Result[BacktestResult, CommandError]:
        match read(params.earlier), read(params.later):
            case Err() as e, _:
                return e
            case _, Err() as e:
                return e
            case Ok(value=earlier), Ok(value=later):
                pass
        result = _result(backtest(earlier, later, params.fdr))
        if params.out is not None:
            report = {
                "stage": "backtest",
                "params": params.model_dump(),
                "result": result.model_dump(),
            }
            match reports.write(report, Path(params.out) / "report.json"):
                case Err(error=e):
                    return Err(_error(e))
                case Ok(value=path):
                    result.outputs.append(str(path))
        return Ok(result)

    return Command(
        id="backtest.run",
        summary="Compare one patch's WPA contrasts with the next patch's",
        params=BacktestParams,
        result=BacktestResult,
        run=run,
    )


def _result(b: Backtest) -> BacktestResult:
    return BacktestResult(
        earlier_contrasts=b.earlier_contrasts,
        later_contrasts=b.later_contrasts,
        paired=b.paired,
        sign_agreement=b.sign_agreement,
        clear=b.clear,
        clear_sign_agreement=b.clear_sign_agreement,
        correlation=b.correlation,
        slope=b.slope,
        claims=[
            ClaimRow(
                champion=c.key[0],
                role=c.key[1],
                slot=c.key[2],
                option=c.key[3],
                versus=c.key[4],
                earlier=c.earlier,
                earlier_q=c.earlier_q,
                later=c.later,
                later_q=c.later_q,
            )
            for c in b.claims
        ],
        claims_held=b.claims_held,
        claims_replicated=b.claims_replicated,
    )


def _error(e: StoreError) -> CommandError:
    return CommandError(
        code="not_found" if e.kind == "not_found" else "invalid_input", message=e.message
    )
