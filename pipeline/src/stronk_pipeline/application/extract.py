"""`extract.run`: a crawl directory -> `frames.parquet`, `decisions.parquet`, `report.json`."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from stronk_pipeline.application.registry import Command, CommandError
from stronk_pipeline.domain.extract.tables import extract
from stronk_pipeline.domain.match import Match
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.ports import DecisionStore, FrameStore, MatchStore, ReportWriter, StoreError


class ExtractParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crawl: Annotated[str, Field(min_length=1, description="Crawl directory")]
    out: Annotated[str, Field(min_length=1, description="Output directory")]


class ExtractResult(BaseModel):
    matches: int
    frames: int
    decisions: int
    decisions_by_slot: dict[int, int]
    inferred: int
    dropped: dict[str, int]
    outputs: list[str]


def extract_command(
    stores: Callable[[Path], MatchStore],
    decisions: DecisionStore,
    frames: FrameStore,
    reports: ReportWriter,
) -> Command[ExtractParams, ExtractResult]:
    def run(params: ExtractParams) -> Result[ExtractResult, CommandError]:
        store = stores(Path(params.crawl))
        match store.read_matches():
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=(matches, unreadable)):
                pass
        if not matches:
            return Err(CommandError(code="invalid_input", message=f"no games in {params.crawl}"))
        match store.read_static():
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=statics):
                pass
        extracted = extract(matches, statics)
        stats = extracted.stats
        if unreadable:
            stats.dropped["unreadable_file"] += unreadable
        out = Path(params.out)
        match frames.write_frames(extracted.frames, out / "frames.parquet"):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=frames_path):
                pass
        match decisions.write_decisions(extracted.decisions, out / "decisions.parquet"):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=decisions_path):
                pass
        result = ExtractResult(
            matches=stats.matches,
            frames=len(extracted.frames),
            decisions=len(extracted.decisions),
            decisions_by_slot=dict(sorted(stats.decisions_by_slot.items())),
            inferred=stats.inferred,
            dropped=dict(sorted(stats.dropped.items())),
            outputs=[str(frames_path), str(decisions_path)],
        )
        report = {
            "stage": "extract",
            "params": params.model_dump(),
            "inputs": {"matches": len(matches), "match_ids_sha256": _ids_hash(matches)},
            "patches": sorted({m.patch for m in matches}),
            "static_versions": {p: s.version for p, s in sorted(statics.items())},
            "result": result.model_dump(),
        }
        match reports.write(report, out / "report.json"):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=report_path):
                result.outputs.append(str(report_path))
        return Ok(result)

    return Command(
        id="extract.run",
        summary="Turn crawled games into per-minute frames and decision points",
        params=ExtractParams,
        result=ExtractResult,
        run=run,
    )


def _ids_hash(matches: list[Match]) -> str:
    ids = sorted(m.match_id for m in matches)
    return hashlib.sha256("\n".join(ids).encode()).hexdigest()


def _error(error: StoreError) -> CommandError:
    code = "not_found" if error.kind == "not_found" else "invalid_input"
    return CommandError(code=code, message=error.message)
