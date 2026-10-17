"""Interfaces the application layer works through. Adapters implement them.

More ports arrive with their stages: MatchSource (crawl, M1), Publisher and Signer (publish, M2).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.logistic import Floats
from stronk_pipeline.domain.result import Result
from stronk_pipeline.domain.wpa.types import OptionEstimate, WpaSettings


@dataclass(frozen=True)
class StoreError:
    kind: Literal["not_found", "invalid"]
    message: str


class DecisionStore(Protocol):
    def read_decisions(self, path: Path) -> Result[DecisionTable, StoreError]: ...

    def write_decisions(self, table: DecisionTable, path: Path) -> Result[Path, StoreError]: ...


class Estimator(Protocol):
    """One WPA estimator version (docs/wpa-method.md, section 5)."""

    @property
    def id(self) -> str: ...

    def estimate(
        self, table: DecisionTable, wp: Floats, settings: WpaSettings
    ) -> list[OptionEstimate]: ...
