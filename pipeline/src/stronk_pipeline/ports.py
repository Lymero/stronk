"""Interfaces the application layer works through. Adapters implement them.

Publish writes through Signer and Publisher.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import numpy as np
from numpy.typing import NDArray

from stronk_pipeline.domain.decisions import DecisionTable
from stronk_pipeline.domain.frames import FrameTable
from stronk_pipeline.domain.logistic import Floats
from stronk_pipeline.domain.match import Match
from stronk_pipeline.domain.result import Result
from stronk_pipeline.domain.static import StaticData
from stronk_pipeline.domain.wpa.types import OptionEstimate, WpaSettings

type Tier = Literal["CHALLENGER", "GRANDMASTER", "MASTER", "DIAMOND"]
type Division = Literal["I", "II", "III", "IV"]
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
class Rejected:
    """A game fetched whole that failed validation: kept in quarantine for a later retry."""

    reason: str
    """Short and free of ids, so rejections group by cause."""
    payload: Mapping[str, object]
    """`{"match": ..., "timeline": ...}` as received; `timeline` is None when the match itself
    failed, before the timeline was fetched."""


@dataclass(frozen=True)
class Quarantined:
    match_id: str
    reason: str
    payload: Mapping[str, object]
    """As `Rejected.payload`, with identities scrubbed and PUUIDs replaced by the crawl's
    pseudonyms, so a game that parses on retry is stored as it is."""


class PayloadParser(Protocol):
    def __call__(self, payload: object) -> Result[Match | None, str]:
        """A quarantined game read with today's parser: the game; None when only its match
        was kept and it now reads (crawl it again for its timeline); or why it still fails."""
        ...


@dataclass(frozen=True)
class SourceStats:
    requests: int
    retries: int
    waited_seconds: float
    """Time spent waiting on rate limits and backoff."""


class MatchSource(Protocol):
    """Ranked players and their games (Riot API, or recorded responses)."""

    async def players(
        self, tier: Tier, division: Division, page: int
    ) -> Result[list[str], SourceError]:
        """One page of a ranked tier's ladder, best first: the whole league for an apex tier on
        page 1 (nothing on later pages), a division's page for Diamond; empty past the last."""
        ...

    async def match_ids(self, player: str, count: int) -> Result[list[str], SourceError]:
        """The player's latest ranked solo games, newest first."""
        ...

    async def fetch(
        self, match_id: str, wanted: Callable[[MatchHeader], str | None]
    ) -> Result[Match | Skipped | Rejected, SourceError]:
        """The whole game, unless `wanted` returns a reason to skip it after the header."""
        ...

    async def static_data(self, patch: str) -> Result[StaticData, SourceError]: ...

    def stats(self) -> SourceStats: ...

    async def close(self) -> None: ...


class MatchStore(Protocol):
    """Crawled games of one crawl directory. Skipped games are remembered so they aren't
    fetched again."""

    def known(self) -> Result[frozenset[str], StoreError]:
        """Ids of games stored, skipped or quarantined."""
        ...

    def salt(self) -> Result[bytes, StoreError]:
        """The secret key for player pseudonyms, created on first use; never published."""
        ...

    def count(self) -> int:
        """Games stored."""
        ...

    def put(self, match: Match) -> Result[None, StoreError]: ...

    def skip(self, match_id: str, reason: str) -> Result[None, StoreError]: ...

    def skip_counts(self) -> Result[dict[str, int], StoreError]:
        """Skipped games by reason."""
        ...

    def quarantine(
        self, match_id: str, reason: str, payload: Mapping[str, object]
    ) -> Result[None, StoreError]:
        """Keep a rejected game, scrubbed, for `quarantined`; replaces an earlier entry."""
        ...

    def quarantined(self) -> Result[list[Quarantined], StoreError]: ...

    def release(self, match_id: str) -> Result[None, StoreError]:
        """Forget a quarantined game: stored since, or to be crawled again."""
        ...

    def has_static(self, patch: str) -> bool: ...

    def bracket(self) -> Result[str, StoreError]:
        """The elo bracket of the crawl's games (ADR-076); a crawl from before brackets were
        recorded is Master+."""
        ...

    def set_bracket(self, bracket: str) -> Result[None, StoreError]: ...

    def patches(self) -> list[str]:
        """Patches with stored games, oldest first."""
        ...

    def put_static(self, patch: str, static: StaticData) -> Result[None, StoreError]: ...

    def read_static(self) -> Result[dict[str, StaticData], StoreError]: ...

    def read_matches(self) -> Result[tuple[list[Match], int], StoreError]:
        """Every stored game, and how many files could not be read."""
        ...


class FrameStore(Protocol):
    def read_frames(self, path: Path) -> Result[FrameTable, StoreError]: ...

    def write_frames(self, table: FrameTable, path: Path) -> Result[Path, StoreError]: ...


class WinProbModel(Protocol):
    """A trained win probability model (docs/wpa-method.md, section 4)."""

    @property
    def feature_names(self) -> tuple[str, ...]: ...

    def predict(self, features: Floats, minute: Floats) -> Floats:
        """P(win) for the team whose leads `features` holds, columns in `feature_names` order.
        Raw: not yet symmetric (`domain.winprob.symmetric`)."""
        ...


class WinProbLearner(Protocol):
    """One kind of win probability model; `winprob.train` keeps the best on validation."""

    @property
    def id(self) -> str: ...

    def fit(
        self,
        train: tuple[Floats, Floats, Floats],
        valid: tuple[Floats, Floats, Floats],
        feature_names: tuple[str, ...],
        monotone: tuple[int, ...],
        seed: int,
    ) -> WinProbModel:
        """`train` and `valid` are (features, minute, outcome); `valid` stops boosting early.
        `monotone` per feature: 1 when P(win) may only rise with it, 0 when unconstrained."""
        ...


class WinProbStore(Protocol):
    def save(self, model: WinProbModel, path: Path) -> Result[Path, StoreError]: ...

    def load(self, path: Path) -> Result[WinProbModel, StoreError]: ...


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
        self,
        table: DecisionTable,
        wp: Floats,
        settings: WpaSettings,
        outcome: Floats | None = None,
        strata: NDArray[np.str_] | None = None,
    ) -> list[OptionEstimate]:
        """`outcome` defaults to the final result (docs/wpa-method.md, section 5); `strata`
        compares options within each label (champion, when pooled by class)."""
        ...


class Signer(Protocol):
    """Signs published manifests (minisign format, contracts/README.md)."""

    @property
    def key_id(self) -> str:
        """16 upper-case hex digits, as `manifest.keyId`."""
        ...

    def public_key(self) -> str:
        """The public key file the app needs to verify."""
        ...

    def sign(self, message: bytes, trusted_comment: str) -> bytes:
        """The `.minisig` file for `message`."""
        ...


class SigningKeys(Protocol):
    def generate(self, path: Path) -> Result[Signer, StoreError]:
        """A new key at `path` (owner-only), its public key next to it as `<path>.pub`.
        Never overwrites."""
        ...

    def load(self, path: Path) -> Result[Signer, StoreError]: ...


class EstimateStore(Protocol):
    def write_estimates(
        self, estimator: str, estimates: Sequence[OptionEstimate], path: Path
    ) -> Result[Path, StoreError]: ...

    def read_estimates(self, path: Path) -> Result[list[OptionEstimate], StoreError]: ...


class Publisher(Protocol):
    def publish(self, patch: str, files: Mapping[str, bytes]) -> Result[list[str], StoreError]:
        """Replace the patch's published files with exactly `files` (paths relative to the
        patch), as a whole: readers never see a mix of two runs."""
        ...
