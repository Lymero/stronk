"""`crawl.run`: ranked solo games of one platform and one patch, into a crawl directory.

Seeds players from the ranked ladder (best first; Diamond page by page, division I to IV), walks
each one's latest games and keeps the ones from the target patch. A crawl directory holds one elo
bracket (ADR-076), set by its tiers: Master+ (Challenger, Grandmaster, Master) or Diamond,
written with its first game. Games that fail validation go to quarantine with their payloads,
for `extract.run` with `retry_quarantine` once the parser is fixed. Resumable: games already
stored, skipped or quarantined are never fetched again, so rerunning the command continues where
the last run stopped.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections import Counter
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from stronk_pipeline.application.registry import Command, CommandError
from stronk_pipeline.domain.bracket import MASTER_PLUS, bracket_of
from stronk_pipeline.domain.match import Match
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.ports import (
    MatchHeader,
    MatchSource,
    MatchStore,
    Platform,
    Rejected,
    Skipped,
    SourceError,
    StoreError,
    Tier,
)

log = logging.getLogger(__name__)

RANKED_SOLO = 420
SUMMONERS_RIFT = 11
PROGRESS_EVERY = 25
DIVISIONS = ("I", "II", "III", "IV")
"""Diamond's divisions, best first."""


class CrawlParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Platform = "euw1"
    tiers: Annotated[list[Tier], Field(min_length=1)] = ["CHALLENGER", "GRANDMASTER", "MASTER"]
    patch: Annotated[str | None, Field(pattern=r"^\d+\.\d+$")] = None
    """Target patch, for example "16.20". Default: the newest patch already in `out`, or else
    the patch of the first game found (the best player's latest game)."""
    max_matches: Annotated[int, Field(ge=1, le=1_000_000)] = 100
    """New games to store in this run."""
    matches_per_player: Annotated[int, Field(ge=1, le=100)] = 20
    out: Annotated[str, Field(min_length=1)] = "runs/crawl/euw1"
    record: str | None = None
    """Also save scrubbed responses to this directory, to commit as a test recording."""
    replay: str | None = None
    """Play back a recording instead of calling Riot: no key, no network."""

    @model_validator(mode="after")
    def _record_or_replay(self) -> CrawlParams:
        if self.record is not None and self.replay is not None:
            raise ValueError("record and replay cannot be combined")
        if bracket_of(self.tiers) is None:
            raise ValueError(
                "tiers mix Master+ and Diamond: crawl each bracket into its own directory"
            )
        return self


class CrawlResult(BaseModel):
    platform: str
    bracket: str
    """The crawl's elo bracket: `master_plus` or `diamond` (ADR-076)."""
    patch: str | None
    stored: int
    """New games stored in this run."""
    total: int
    """Games in the crawl directory after this run."""
    skipped: dict[str, int]
    errors: int
    players: int
    requests: int
    retries: int
    waited_seconds: float


type _Step = Literal["next", "player_done"] | CommandError
type SourceFactory = Callable[[CrawlParams], Result[MatchSource, CommandError]]
type StoreFactory = Callable[[Path], MatchStore]


def crawl_command(
    sources: SourceFactory, stores: StoreFactory
) -> Command[CrawlParams, CrawlResult]:
    def run(params: CrawlParams) -> Result[CrawlResult, CommandError]:
        match sources(params):
            case Err() as e:
                return e
            case Ok(value=source):
                pass
        return asyncio.run(_crawl_then_close(params, source, stores(Path(params.out))))

    return Command(
        id="crawl.run",
        summary="Crawl ranked games of one platform and patch into a crawl directory",
        params=CrawlParams,
        result=CrawlResult,
        run=run,
    )


async def _crawl_then_close(
    params: CrawlParams, source: MatchSource, store: MatchStore
) -> Result[CrawlResult, CommandError]:
    try:
        return await _Crawl(params, source, store).run()
    finally:
        await source.close()


class _Crawl:
    def __init__(self, params: CrawlParams, source: MatchSource, store: MatchStore) -> None:
        self.params = params
        self.source = source
        self.store = store
        self.patch = params.patch
        self.bracket = bracket_of(params.tiers) or MASTER_PLUS
        self.stored = 0
        self.skipped: Counter[str] = Counter()
        self.errors = 0
        self.players = 0
        self.salt: bytes | None = None

    async def run(self) -> Result[CrawlResult, CommandError]:
        match self.store.known():
            case Err(error=e):
                return Err(_store_error(e))
            case Ok(value=known):
                pass
        if (failure := self._check_bracket()) is not None:
            return Err(failure)
        seen = set(known)
        if self.patch is None and (stored := self.store.patches()):
            self.patch = stored[-1]  # resuming: keep the crawl on one patch
            log.info("target patch: %s (from earlier runs)", self.patch)
        for tier in self.params.tiers:
            async for players in self._ladder(tier):
                if isinstance(players, CommandError):
                    return Err(players)
                for player in players:
                    if self.stored >= self.params.max_matches:
                        return Ok(self._result())
                    self.players += 1
                    failure = await self._walk(player, seen)
                    if failure is not None:
                        return Err(failure)
        return Ok(self._result())

    async def _ladder(self, tier: Tier) -> AsyncIterator[list[str] | CommandError]:
        """A tier's players, a page at a time: an apex league whole, Diamond by division and page
        until a page comes back empty. A rejected key ends the crawl; another error skips the rest
        of that division."""
        for division in DIVISIONS if tier == "DIAMOND" else ("I",):
            for page in itertools.count(1):
                match await self.source.players(tier, division, page):
                    case Err(error=e) if e.kind == "unauthorized":
                        yield self._stopped(e)
                        return
                    case Err(error=e):
                        log.warning("skipping %s %s page %d: %s", tier, division, page, e.message)
                        self.errors += 1
                        break
                    case Ok(value=players):
                        if not players:
                            break
                        yield players

    def _check_bracket(self) -> CommandError | None:
        """One bracket per crawl directory: the one its games were crawled for, if any."""
        bracket = self.bracket
        match self.store.bracket():
            case Err(error=e):
                return _store_error(e)
            case Ok(value=held):
                pass
        if self.store.count() > 0 and held != bracket:
            return CommandError(
                code="invalid_params",
                message=f"{self.params.out} holds {held} games; "
                f"crawl {bracket} into another directory",
            )
        return None

    async def _walk(self, player: str, seen: set[str]) -> CommandError | None:
        """Store the player's new games; stop at the first game older than the patch."""
        match await self.source.match_ids(player, self.params.matches_per_player):
            case Err(error=e):
                if e.kind == "unauthorized":
                    return self._stopped(e)
                self.errors += 1
                return None
            case Ok(value=match_ids):
                pass
        for match_id in match_ids:
            if self.stored >= self.params.max_matches:
                return None
            if match_id in seen:
                continue
            step = await self._visit(match_id, seen)
            if step != "next":
                return None if step == "player_done" else step
        return None

    async def _visit(self, match_id: str, seen: set[str]) -> _Step:
        match await self.source.fetch(match_id, self._wanted):
            case Err(error=e) if e.kind == "unauthorized":
                return self._stopped(e)
            case Err(error=e) if e.kind == "unavailable":
                self.errors += 1  # not remembered: worth retrying in a later run
                return "next"
            case Err(error=e):
                log.warning("skipping %s: %s", match_id, e.message)
                outcome: Match | Skipped | Rejected = Skipped(e.kind)
            case Ok(value=outcome):
                pass
        seen.add(match_id)
        if isinstance(outcome, Rejected):
            log.warning("quarantining %s: %s", match_id, outcome.reason)
            self.skipped["quarantined"] += 1
            stored = self.store.quarantine(match_id, outcome.reason, outcome.payload)
            return self._check(stored) or "next"
        if isinstance(outcome, Skipped):
            self.skipped[outcome.reason] += 1
            if (failure := self._check(self.store.skip(match_id, outcome.reason))) is not None:
                return failure
            # Histories are newest first: everything after an older game is older too.
            return "player_done" if outcome.reason == "older_patch" else "next"
        if (failure := await self._put(outcome)) is not None:
            return failure
        # The bracket is written with the first game, so no game is ever without it.
        if self.stored == 0 and (failure := self._check(self.store.set_bracket(self.bracket))):
            return failure
        self.stored += 1
        if self.stored % PROGRESS_EVERY == 0:
            stats = self.source.stats()
            log.info(
                "%d/%d games stored, %d requests, %.0f s waiting on rate limits",
                self.stored,
                self.params.max_matches,
                stats.requests,
                stats.waited_seconds,
            )
        return "next"

    def _wanted(self, header: MatchHeader) -> str | None:
        if header.queue != RANKED_SOLO:
            return "other_queue"
        if header.map_id != SUMMONERS_RIFT:
            return "other_map"
        if header.remake:
            return "remake"
        if header.patch is None:
            return "unknown_patch"
        if self.patch is None:
            self.patch = header.patch
            log.info("target patch: %s", self.patch)
        if header.patch != self.patch:
            if _patch_key(header.patch) < _patch_key(self.patch):
                return "older_patch"
            if self.params.patch is None:
                log.warning("found patch %s, newer than the target %s", header.patch, self.patch)
            return "newer_patch"
        return None

    async def _put(self, match: Match) -> CommandError | None:
        """Store a game, its patch's static data first. The salt is read on first use, so a
        crawl that stores nothing writes nothing."""
        if self.salt is None:
            match self.store.salt():
                case Err(error=e):
                    return _store_error(e)
                case Ok(value=salt):
                    self.salt = salt
        if (failure := await self._ensure_static(match.patch)) is not None:
            return failure
        return self._check(self.store.put(match.pseudonymized(self.salt)))

    async def _ensure_static(self, patch: str) -> CommandError | None:
        if self.store.has_static(patch):
            return None
        match await self.source.static_data(patch):
            case Err(error=e):
                return CommandError(code="unavailable", message=e.message)
            case Ok(value=static):
                return self._check(self.store.put_static(patch, static))

    def _check(self, result: Result[None, StoreError]) -> CommandError | None:
        match result:
            case Err(error=e):
                return _store_error(e)
            case Ok():
                return None

    def _stopped(self, error: SourceError) -> CommandError:
        return CommandError(
            code="unauthorized",
            message=f"{error.message}. Stopped after storing {self.stored} new games; "
            "rerun to continue.",
        )

    def _result(self) -> CrawlResult:
        stats = self.source.stats()
        return CrawlResult(
            platform=self.params.platform,
            bracket=self.bracket,
            patch=self.patch,
            stored=self.stored,
            total=self.store.count(),
            skipped=dict(sorted(self.skipped.items())),
            errors=self.errors,
            players=self.players,
            requests=stats.requests,
            retries=stats.retries,
            waited_seconds=round(stats.waited_seconds, 1),
        )


def _patch_key(patch: str) -> tuple[int, ...]:
    return tuple(int(p) for p in patch.split("."))


def _store_error(error: StoreError) -> CommandError:
    return CommandError(code="invalid_input", message=error.message)
