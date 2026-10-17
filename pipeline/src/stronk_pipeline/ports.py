"""Interfaces the application layer works through. Adapters implement them.

More ports arrive with their stages: Publisher and Signer (publish, M2).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.frames import FrameTable
from stronk_pipeline.domain.logistic import Floats
from stronk_pipeline.domain.match import Match
from stronk_pipeline.domain.result import Result
from stronk_pipeline.domain.static import StaticData
from stronk_pipeline.domain.wpa.types import OptionEstimate, WpaSettings

type Tier = Literal["CHALLENGER", "GRANDMASTER", "MASTER", "DIAMOND"]
type Platform = Literal[
    "br1", "eun1", "euw1", "jp1", "kr", "la1", "la2", "me1",
    "na1", "oc1", "ru", "sg2", "tr1", "tw2", "vn2",
]  # fmt: skip
"""Riot platform: where league-v4 lives and games are played."""


@dataclass(frozen=True)
class StoreError:
    kind: Literal["not_found", "invalid"]
    message: str


@dataclass(frozen=True)
class SourceError:
    kind: Literal["not_found", "unauthorized", "unavailable", "invalid"]
    """`unauthorized`: the API key is missing, expired or revoked; nothing else will work.
    `unavailable`: the source kept failing after retries; trying again later may work."""
    message: str


@dataclass(frozen=True)
class MatchHeader:
    """What a match is, read before deciding whether its timeline is worth fetching."""

    match_id: str
    patch: str | None
    queue: int
    map_id: int
    remake: bool


@dataclass(frozen=True)
class Skipped:
    reason: str


@dataclass(frozen=True)
class SourceStats:
    requests: int
    retries: int
    waited_seconds: float
    """Time spent waiting on rate limits and backoff."""


class MatchSource(Protocol):
    """Ranked players and their games (Riot API, or recorded responses)."""

    async def players(self, tier: Tier) -> Result[list[str], SourceError]:
        """Player ids in a ranked tier, best first."""
        ...

    async def match_ids(self, player: str, count: int) -> Result[list[str], SourceError]:
        """The player's latest ranked solo games, newest first."""
        ...

    async def fetch(
        self, match_id: str, wanted: Callable[[MatchHeader], str | None]
    ) -> Result[Match | Skipped, SourceError]:
        """The whole game, unless `wanted` returns a reason to skip it after the header."""
        ...

    async def static_data(self, patch: str) -> Result[StaticData, SourceError]: ...

    def stats(self) -> SourceStats: ...

    async def close(self) -> None: ...


class MatchStore(Protocol):
    """Crawled games of one crawl directory. Skipped games are remembered so they aren't
    fetched again."""

    def known(self) -> Result[frozenset[str], StoreError]:
        """Ids of games stored or skipped."""
        ...

    def salt(self) -> Result[bytes, StoreError]:
        """The secret key for player pseudonyms, created on first use; never published."""
        ...

    def count(self) -> int:
        """Games stored."""
        ...

    def put(self, match: Match) -> Result[None, StoreError]: ...

    def skip(self, match_id: str, reason: str) -> Result[None, StoreError]: ...

    def has_static(self, patch: str) -> bool: ...

    def patches(self) -> list[str]:
        """Patches with stored games, oldest first."""
        ...

    def put_static(self, patch: str, static: StaticData) -> Result[None, StoreError]: ...

    def read_static(self) -> Result[dict[str, StaticData], StoreError]: ...

    def read_matches(self) -> Result[tuple[list[Match], int], StoreError]:
        """Every stored game, and how many files could not be read."""
        ...


class FrameStore(Protocol):
    def write_frames(self, table: FrameTable, path: Path) -> Result[Path, StoreError]: ...


class ReportWriter(Protocol):
    def write(self, report: Mapping[str, object], path: Path) -> Result[Path, StoreError]: ...


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
