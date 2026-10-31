"""`extract.run`: crawl directories -> `frames.parquet`, `decisions.parquet`, `report.json`.

Several crawls (one per region, say) are read into one table: match ids carry their platform,
and a game found in two crawls counts once.

With `retry_quarantine`, games the crawl quarantined are first read again with today's parser:
those that now pass are stored and leave quarantine, those whose match now reads but whose
timeline was never fetched leave it to be crawled again, the rest stay.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from stronk_pipeline.application.registry import Command, CommandError
from stronk_pipeline.domain.bracket import single
from stronk_pipeline.domain.extract.tables import extract
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
    bracket: str
    """The crawls' elo bracket, one for all of them (ADR-076)."""
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
            case Ok(value=(bracket, crawl)):
                pass
        matches, unreadable, statics = crawl.matches, crawl.unreadable, crawl.statics
        if not matches:
            where = ", ".join(params.crawl)
            return Err(CommandError(code="invalid_input", message=f"no games in {where}"))
        extracted = extract(matches, statics)
        stats = extracted.stats
        if unreadable:
            stats.dropped["unreadable_file"] += unreadable
        held = sum(crawl.quarantined.values())
        failed = held + sum(n for k, n in stats.dropped.items() if k in GAME_DROPS)
        attempted = len(matches) + unreadable + held
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
            bracket=bracket,
            matches=stats.matches,
            frames=len(extracted.frames),
            decisions=len(extracted.decisions),
            decisions_by_slot=dict(sorted(stats.decisions_by_slot.items())),
            inferred=stats.inferred,
            dropped=dict(sorted(stats.dropped.items())),
            skipped=crawl.skipped,
            quarantined=dict(sorted(crawl.quarantined.items())),
            skip_rate=round(failed / attempted, 6),
            retried=crawl.retried,
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


@dataclass(frozen=True)
class _CrawlContents:
    matches: list[Match]
    unreadable: int
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
    match store.read_matches():
        case Err() as e:
            return e
        case Ok(value=(matches, unreadable)):
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
    return Ok(_CrawlContents(matches, unreadable, statics, skipped, quarantined, retried))


def _merge(contents: list[_CrawlContents]) -> _CrawlContents:
    """One crawl's worth of contents from several; the first copy of a game or a patch wins."""
    matches: dict[str, Match] = {}
    statics: dict[str, StaticData] = {}
    skipped: Counter[str] = Counter()
    quarantined: Counter[str] = Counter()
    retried: Counter[str] = Counter()
    for c in contents:
        for m in c.matches:
            matches.setdefault(m.match_id, m)
        for patch, static in c.statics.items():
            statics.setdefault(patch, static)
        skipped.update(c.skipped)
        quarantined.update(c.quarantined)
        if c.retried is not None:
            retried.update(c.retried.model_dump())
    return _CrawlContents(
        matches=list(matches.values()),
        unreadable=sum(c.unreadable for c in contents),
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


def _ids_hash(matches: list[Match]) -> str:
    ids = sorted(m.match_id for m in matches)
    return hashlib.sha256("\n".join(ids).encode()).hexdigest()


def _read_all(
    stores: Callable[[Path], MatchStore], parse: PayloadParser, params: ExtractParams
) -> Result[tuple[str, _CrawlContents], CommandError]:
    """Every crawl's contents, merged, and their one bracket."""
    match crawl_bracket(stores, params.crawl):
        case Err() as e:
            return e
        case Ok(value=bracket):
            pass
    contents: list[_CrawlContents] = []
    for directory in params.crawl:
        match _read(stores(Path(directory)), parse, retry=params.retry_quarantine):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=one):
                contents.append(one)
    return Ok((bracket, _merge(contents)))


def crawl_bracket(
    stores: Callable[[Path], MatchStore], crawls: Sequence[str]
) -> Result[str, CommandError]:
    """The elo bracket of `crawls` (ADR-076), refused when they hold two: Master+ and Diamond
    games are never estimated or published together."""
    brackets: list[str] = []
    for crawl in crawls:
        match stores(Path(crawl)).bracket():
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=bracket):
                brackets.append(bracket)
    bracket = single(brackets)
    if bracket is None:
        held = ", ".join(f"{c}: {b}" for c, b in zip(crawls, brackets, strict=True))
        return Err(CommandError(code="invalid_input", message=f"crawls mix brackets ({held})"))
    return Ok(bracket)


def _error(error: StoreError) -> CommandError:
    code = "not_found" if error.kind == "not_found" else "invalid_input"
    return CommandError(code=code, message=error.message)
