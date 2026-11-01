"""`extract.run`: crawl directories -> `frames.parquet`, `decisions.parquet`, `report.json`.

Several crawls (one per region, or one per band of tiers) are read into one table: match ids
carry their platform, and a game found in two crawls counts once. Games are read one at a time,
twice: their headers first, for player skill across every game, then each game whole (ADR-079).

With `retry_quarantine`, games the crawl quarantined are first read again with today's parser:
those that now pass are stored and leave quarantine, those whose match now reads but whose
timeline was never fetched leave it to be crawled again, the rest stay.
"""

from __future__ import annotations

import hashlib
import itertools
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from stronk_pipeline.application.registry import Command, CommandError
from stronk_pipeline.domain.bracket import ordered, published
from stronk_pipeline.domain.extract.skill import GameHeader, PlayerGame, prior_skill
from stronk_pipeline.domain.extract.tables import ExtractStats, extract
from stronk_pipeline.domain.match import Match
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.static import StaticData
from stronk_pipeline.ports import (
    DecisionStore,
    FrameStore,
    MatchStore,
    PayloadParser,
    Quarantined,
    ReportWriter,
    StoreError,
)

GAME_DROPS = frozenset({"unreadable_file", "no_static_data", "unknown_champion"})
"""Extract drops that lose a whole game; the others (`unfinished_slot`) lose one decision."""


class ExtractParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crawl: Annotated[
        list[Annotated[str, Field(min_length=1)]],
        BeforeValidator(lambda v: [v] if isinstance(v, str) else v),
        Field(min_length=1, description="Crawl directory, or a list of them"),
    ]
    out: Annotated[str, Field(min_length=1, description="Output directory")]
    retry_quarantine: bool = False
    """Read quarantined games again first, and clear the ones that now pass."""


class QuarantineRetry(BaseModel):
    stored: int
    """Now pass: stored and out of quarantine."""
    recrawl: int
    """Only the match was kept and it now reads: out of quarantine, for the next crawl."""
    still_failing: int


class ExtractResult(BaseModel):
    bands: list[str]
    """The crawls' bands of tiers, highest first (ADR-076, ADR-079)."""
    bracket: str | None
    """The published bracket those bands make (`diamond_plus`...), if they make one."""
    matches: int
    frames: int
    decisions: int
    decisions_by_slot: dict[int, int]
    inferred: int
    dropped: dict[str, int]
    skipped: dict[str, int]
    """Games the crawl passed over, by reason (older patch, remake...)."""
    quarantined: dict[str, int]
    """Games in quarantine, by reason."""
    skip_rate: float
    """Games lost to a failure (quarantined, or dropped whole by extract) over games attempted.
    Games passed over on purpose (`skipped`) don't count."""
    retried: QuarantineRetry | None = None
    outputs: list[str]


def extract_command(
    stores: Callable[[Path], MatchStore],
    parse: PayloadParser,
    decisions: DecisionStore,
    frames: FrameStore,
    reports: ReportWriter,
) -> Command[ExtractParams, ExtractResult]:
    def run(params: ExtractParams) -> Result[ExtractResult, CommandError]:
        match _read_all(stores, parse, params):
            case Err(error=e):
                return Err(e)
            case Ok(value=(bands, crawl)):
                pass
        statics = crawl.statics
        match _two_passes(stores, params.crawl):
            case Err(error=e):
                return Err(e)
            case Ok(value=(headers, unreadable, games)):
                pass
        out = Path(params.out)
        match _write_tables(
            games, statics, prior_skill(headers), out=out, frames=frames, decisions=decisions
        ):
            case Err(error=e):
                return Err(e)
            case Ok(value=(stats, rows, outputs)):
                pass
        if unreadable:
            stats.dropped["unreadable_file"] += unreadable
        held = sum(crawl.quarantined.values())
        failed = held + sum(n for k, n in stats.dropped.items() if k in GAME_DROPS)
        attempted = len(headers) + unreadable + held
        result = ExtractResult(
            bands=bands,
            bracket=published(bands),
            matches=stats.matches,
            frames=rows[0],
            decisions=rows[1],
            decisions_by_slot=dict(sorted(stats.decisions_by_slot.items())),
            inferred=stats.inferred,
            dropped=dict(sorted(stats.dropped.items())),
            skipped=crawl.skipped,
            quarantined=dict(sorted(crawl.quarantined.items())),
            skip_rate=round(failed / attempted, 6),
            retried=crawl.retried,
            outputs=[str(p) for p in outputs],
        )
        report = {
            "stage": "extract",
            "params": params.model_dump(),
            "inputs": {"matches": len(headers), "match_ids_sha256": _ids_hash(headers)},
            "patches": sorted({h.patch for h in headers}),
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


CHUNK_GAMES = 2_000
"""Games extracted and written at once, as one part of each table (ADR-080)."""


def _write_tables(
    games: Iterable[Match],
    statics: Mapping[str, StaticData],
    skill: Mapping[PlayerGame, tuple[float, float]],
    *,
    out: Path,
    frames: FrameStore,
    decisions: DecisionStore,
) -> Result[tuple[ExtractStats, tuple[int, int], tuple[Path, Path]], CommandError]:
    """Both tables, written a chunk of games at a time as the parts of `frames.parquet` and
    `decisions.parquet`; the counts, the rows of each, and where they are."""
    stats = ExtractStats()
    frame_rows = decision_rows = 0
    frames_path, decisions_path = out / "frames.parquet", out / "decisions.parquet"
    for part, chunk in enumerate(itertools.batched(games, CHUNK_GAMES, strict=False)):
        extracted = extract(chunk, statics, skill)
        stats.add(extracted.stats)
        frame_rows += len(extracted.frames)
        decision_rows += len(extracted.decisions)
        written = frames.write_frames(extracted.frames, frames_path, part)
        if isinstance(written, Ok):
            written = decisions.write_decisions(extracted.decisions, decisions_path, part)
        if isinstance(written, Err):
            return Err(_error(written.error))
    return Ok((stats, (frame_rows, decision_rows), (frames_path, decisions_path)))


@dataclass(frozen=True)
class _CrawlContents:
    """A crawl's game data and counts; its games are read on their own (`each_game`)."""

    statics: dict[str, StaticData]
    skipped: dict[str, int]
    quarantined: Counter[str]
    retried: QuarantineRetry | None


def _read(
    store: MatchStore, parse: PayloadParser, *, retry: bool
) -> Result[_CrawlContents, StoreError]:
    retried = None
    if retry:
        match _retry(store, parse):
            case Err() as e:
                return e
            case Ok(value=retried):
                pass
    match store.read_static():
        case Err() as e:
            return e
        case Ok(value=statics):
            pass
    match store.skip_counts():
        case Err() as e:
            return e
        case Ok(value=skipped):
            pass
    match store.quarantined():
        case Err() as e:
            return e
        case Ok(value=held):
            quarantined = Counter(q.reason for q in held)
    return Ok(_CrawlContents(statics, skipped, quarantined, retried))


def _merge(contents: list[_CrawlContents]) -> _CrawlContents:
    """One crawl's worth of contents from several; the first copy of a patch wins."""
    statics: dict[str, StaticData] = {}
    skipped: Counter[str] = Counter()
    quarantined: Counter[str] = Counter()
    retried: Counter[str] = Counter()
    for c in contents:
        for patch, static in c.statics.items():
            statics.setdefault(patch, static)
        skipped.update(c.skipped)
        quarantined.update(c.quarantined)
        if c.retried is not None:
            retried.update(c.retried.model_dump())
    return _CrawlContents(
        statics=statics,
        skipped=dict(sorted(skipped.items())),
        quarantined=quarantined,
        retried=QuarantineRetry(**retried) if any(c.retried for c in contents) else None,
    )


def _retry(store: MatchStore, parse: PayloadParser) -> Result[QuarantineRetry, StoreError]:
    match store.quarantined():
        case Err() as e:
            return e
        case Ok(value=held):
            pass
    counts: Counter[str] = Counter()
    for entry in held:
        match _retry_one(store, parse, entry):
            case Err() as e:
                return e
            case Ok(value=outcome):
                counts[outcome] += 1
    return Ok(
        QuarantineRetry(
            stored=counts["stored"],
            recrawl=counts["recrawl"],
            still_failing=counts["still_failing"],
        )
    )


def _retry_one(
    store: MatchStore, parse: PayloadParser, entry: Quarantined
) -> Result[str, StoreError]:
    parsed = parse(entry.payload)
    if isinstance(parsed, Err):
        if parsed.error == entry.reason:
            return Ok("still_failing")
        updated = store.quarantine(entry.match_id, parsed.error, entry.payload)
        return _labelled(updated, "still_failing")
    if parsed.value is None:
        return _labelled(store.release(entry.match_id), "recrawl")
    stored = store.put(parsed.value)
    if isinstance(stored, Err):
        return stored
    return _labelled(store.release(entry.match_id), "stored")


def _labelled(result: Result[None, StoreError], label: str) -> Result[str, StoreError]:
    return result if isinstance(result, Err) else Ok(label)


def _ids_hash(headers: Sequence[GameHeader]) -> str:
    ids = sorted(h.match_id for h in headers)
    return hashlib.sha256("\n".join(ids).encode()).hexdigest()


def _read_all(
    stores: Callable[[Path], MatchStore], parse: PayloadParser, params: ExtractParams
) -> Result[tuple[list[str], _CrawlContents], CommandError]:
    """Every crawl's game data and counts, merged, and their bands."""
    match crawl_bands(stores, params.crawl):
        case Err() as e:
            return e
        case Ok(value=bands):
            pass
    contents: list[_CrawlContents] = []
    for directory in params.crawl:
        match _read(stores(Path(directory)), parse, retry=params.retry_quarantine):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=one):
                contents.append(one)
    return Ok((bands, _merge(contents)))


def each_game(
    stores: Callable[[Path], MatchStore], crawls: Sequence[str]
) -> Result[Iterator[Match | None], CommandError]:
    """Every game of `crawls`, read one at a time in order, a game in two crawls once (its first
    copy); None for a file that doesn't read."""
    each: list[Iterator[Match | None]] = []
    for crawl in crawls:
        match stores(Path(crawl)).iter_matches():
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=games):
                each.append(games)
    return Ok(_first_copies(itertools.chain.from_iterable(each)))


def _first_copies(games: Iterable[Match | None]) -> Iterator[Match | None]:
    seen: set[str] = set()
    for game in games:
        if game is not None:
            if game.match_id in seen:
                continue
            seen.add(game.match_id)
        yield game


def _two_passes(
    stores: Callable[[Path], MatchStore], crawls: Sequence[str]
) -> Result[tuple[list[GameHeader], int, Iterator[Match]], CommandError]:
    """Every game's header and how many files didn't read, read through once; then the games
    again, one at a time, for the tables."""
    match each_game(stores, crawls):
        case Err() as e:
            return e
        case Ok(value=games):
            pass
    headers: list[GameHeader] = []
    unreadable = 0
    for game in games:
        if game is None:
            unreadable += 1
        else:
            headers.append(GameHeader.of(game))
    if not headers:
        message = f"no games in {', '.join(crawls)}"
        return Err(CommandError(code="invalid_input", message=message))
    match each_game(stores, crawls):
        case Err() as e:
            return e
        case Ok(value=again):
            return Ok((headers, unreadable, (g for g in again if g is not None)))


def crawl_bands(
    stores: Callable[[Path], MatchStore], crawls: Sequence[str]
) -> Result[list[str], CommandError]:
    """The bands of tiers `crawls` hold (ADR-079), highest first."""
    bands: list[str] = []
    for crawl in crawls:
        match stores(Path(crawl)).bracket():
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=band):
                bands.append(band)
    return Ok(ordered(bands))


def _error(error: StoreError) -> CommandError:
    code = "not_found" if error.kind == "not_found" else "invalid_input"
    return CommandError(code=code, message=error.message)
