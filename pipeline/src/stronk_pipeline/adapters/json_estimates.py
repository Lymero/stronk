"""EstimateStore on a JSON file: the WPA estimates `publish` reads. Validated when read."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.wpa.types import Flag, OptionEstimate
from stronk_pipeline.ports import StoreError


class _Row(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    champion: str
    champion_class: str
    role: str
    slot: int
    option: str
    wpa: float | None
    ci: tuple[float, float] | None
    n: int
    flags: list[Flag]


class _File(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimator: str
    estimates: list[_Row]


class JsonEstimateStore:
    def write_estimates(
        self, estimator: str, estimates: Sequence[OptionEstimate], path: Path
    ) -> Result[Path, StoreError]:
        rows = [
            _Row(
                champion=e.champion,
                champion_class=e.champion_class,
                role=e.role,
                slot=e.slot,
                option=e.option,
                wpa=e.wpa,
                ci=e.ci,
                n=e.n,
                flags=sorted(e.flags),
            )
            for e in estimates
        ]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_File(estimator=estimator, estimates=rows).model_dump_json(indent=1))
        except OSError as e:
            return Err(StoreError("invalid", f"cannot write {path}: {e}"))
        return Ok(path)

    def read_estimates(self, path: Path) -> Result[list[OptionEstimate], StoreError]:
        if not path.is_file():
            return Err(StoreError("not_found", f"no estimates at {path}"))
        try:
            data = _File.model_validate_json(path.read_bytes())
        except (OSError, ValidationError, json.JSONDecodeError) as e:
            return Err(StoreError("invalid", f"{path} is not an estimates file: {_first(e)}"))
        return Ok(
            [
                OptionEstimate(
                    r.champion,
                    r.champion_class,
                    r.role,
                    r.slot,
                    r.option,
                    r.wpa,
                    r.ci,
                    r.n,
                    frozenset(r.flags),
                )
                for r in data.estimates
            ]
        )


def _first(error: Exception) -> str:
    lines = str(error).splitlines()
    return " ".join(lines[:2]) if lines else type(error).__name__
