"""`publish`: WPA estimates and the crawls behind them -> signed build files for the app.

One file per champion and role (contracts/schemas/build.v1.schema.json): rune options from the
keystone estimates, each with the page most played with that keystone, item options per slot,
spell pairs from theirs (ADR-083), and the skill order, the first levels and the max order
(ADR-085). Every file is validated against the contract, listed with its sha256 and size in the
patch manifest, and the manifest is signed (contracts/README.md).
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, model_validator

from stronk_contracts.build_v1 import Build
from stronk_contracts.champions_v1 import Champions
from stronk_contracts.manifest_v1 import Manifest
from stronk_pipeline.application.extract import crawl_bands, each_game
from stronk_pipeline.application.registry import Command, CommandError
from stronk_pipeline.domain.bracket import BRACKETS, published
from stronk_pipeline.domain.extract.decision_points import (
    BOOTS_SLOT,
    COMPONENTS_SLOT,
    LATE_SLOT,
    SKILL_LEVELS_SLOT,
    SKILL_MAX_SLOT,
    SPELLS_SLOT,
    START_SLOT,
    is_rune_slot,
    rune_row,
)
from stronk_pipeline.domain.extract.situation import MAGIC_FROM, PHYSICAL_BELOW, PROFILES
from stronk_pipeline.domain.match import Match
from stronk_pipeline.domain.patches import MissingFingerprintsError, changed_in, in_order
from stronk_pipeline.domain.publish import Played, played
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.static import StaticData
from stronk_pipeline.domain.wpa.types import OptionEstimate
from stronk_pipeline.ports import (
    EstimateStore,
    MatchStore,
    Publisher,
    SigningKeys,
    StoreError,
)

MANIFEST = "manifest.json"
SIGNATURE = "manifest.json.minisig"


type Crawls = Annotated[
    list[Annotated[str, Field(min_length=1)]],
    BeforeValidator(lambda v: [v] if isinstance(v, str) else v),
    Field(min_length=1, description="The crawl directories the estimates came from"),
]


class BracketSource(BaseModel):
    """One bracket's estimates and the crawls behind them; their bands name it (ADR-079)."""

    model_config = ConfigDict(extra="forbid")

    estimates: Annotated[str, Field(min_length=1, description="Estimates from wpa.estimate")]
    crawl: Crawls
    window: Literal["patch", "pooled"] = "patch"
    """`patch`: the crawls hold one patch. `pooled`: they may hold several, published under the
    newest at `{region}/{elo}/pooled/` (ADR-088)."""


class PublishParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimates: Annotated[str | None, Field(min_length=1)] = None
    """One bracket's estimates, with `crawl`; or `brackets` for several."""
    crawl: Crawls | None = None
    brackets: list[BracketSource] = []
    """Every bracket of the patch, published together: a patch is replaced as a whole."""
    key: Annotated[str, Field(min_length=1, description="Signing key (signing.keygen)")]
    out: Annotated[str, Field(min_length=1, description="Data root, the CDN's layout")] = (
        "dist/data"
    )
    region: Annotated[str, Field(pattern=r"^[a-z0-9]{2,8}$")] = "all"
    elo: Annotated[str | None, Field(pattern=r"^[a-z_]{2,32}$")] = None
    """With `estimates` alone: the files' bracket, the one the crawls' bands make (ADR-079), and
    refused if given otherwise."""

    @model_validator(mode="after")
    def _one_or_several(self) -> PublishParams:
        single = self.estimates is not None or self.crawl is not None
        if single == bool(self.brackets) or (single and None in (self.estimates, self.crawl)):
            raise ValueError("give estimates and crawl, or brackets")
        if self.elo is not None and not single:
            raise ValueError("elo goes with estimates and crawl; brackets are named by their bands")
        return self

    def sources(self) -> list[BracketSource]:
        if self.estimates is not None and self.crawl is not None:
            return [BracketSource(estimates=self.estimates, crawl=self.crawl)]
        return self.brackets


class PublishResult(BaseModel):
    patch: str
    run_id: str
    key_id: str
    builds: int
    outputs: list[str]


type Clock = Callable[[], datetime]


def publish_command(
    estimates: EstimateStore,
    stores: Callable[[Path], MatchStore],
    keys: SigningKeys,
    publishers: Callable[[Path], Publisher],
    clock: Clock = lambda: datetime.now(UTC),
) -> Command[PublishParams, PublishResult]:
    def run(params: PublishParams) -> Result[PublishResult, CommandError]:
        match keys.load(Path(params.key)):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=signer):
                pass
        match _changes(stores, params.sources()):
            case Err() as e:
                return e
            case Ok(value=(statics, changed)):
                pass
        match _every_build(estimates, stores, params, changed):
            case Err() as e:
                return e
            case Ok(value=(files, patch)):
                pass
        if patch in statics:
            files[CHAMPIONS] = _champions(statics[patch], patch)
        now = clock()
        content = hashlib.sha256(b"".join(_sha(d).encode() for _, d in sorted(files.items())))
        run_id = f"{now:%Y%m%dT%H%M%SZ}-{content.hexdigest()[:8]}"
        manifest = Manifest.model_validate(
            {
                "schemaVersion": 1,
                "patch": patch,
                "generatedAt": now.isoformat().replace("+00:00", "Z"),
                "runId": run_id,
                "keyId": signer.key_id,
                "files": [
                    {"path": path, "sha256": _sha(data), "bytes": len(data)}
                    for path, data in sorted(files.items())
                ],
            }
        )
        manifest_bytes = _canonical(manifest.model_dump(mode="json", by_alias=True))
        comment = f"stronk manifest v1 patch={patch} runId={run_id}"
        signature = signer.sign(manifest_bytes, comment)
        published = {**files, MANIFEST: manifest_bytes, SIGNATURE: signature}
        match publishers(Path(params.out)).publish(patch, published):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=outputs):
                pass
        return Ok(
            PublishResult(
                patch=patch,
                run_id=run_id,
                key_id=signer.key_id,
                builds=len(files),
                outputs=outputs,
            )
        )

    return Command(
        id="publish",
        summary="Publish signed build files from WPA estimates",
        params=PublishParams,
        result=PublishResult,
        run=run,
    )


def _every_build(
    estimates: EstimateStore,
    stores: Callable[[Path], MatchStore],
    params: PublishParams,
    changed: Mapping[int, str],
) -> Result[tuple[dict[str, bytes], str], CommandError]:
    """Every bracket's builds, in each window, and the patch they're published under: the one
    every bracket ends on."""
    files: dict[str, bytes] = {}
    newest: set[str] = set()
    named: set[tuple[str, str]] = set()
    for source in params.sources():
        match _bracket(estimates, stores, source, params):
            case Err(error=e):
                return Err(e)
            case Ok(value=(elo, rows, seen, found, _)):
                pass
        if (elo, source.window) in named:
            message = f"two sources make {elo} ({source.window}): give each bracket once"
            return Err(CommandError(code="invalid_params", message=message))
        named.add((elo, source.window))
        if not found or (source.window == "patch" and len(found) != 1):
            message = f"crawls must hold one patch, found {sorted(found) or 'none'}"
            return Err(CommandError(code="invalid_input", message=message))
        pooled = in_order(found) if source.window == "pooled" else None
        newest.add(in_order(found)[-1])
        if len(newest) != 1:
            message = f"every bracket must end on one patch, found {in_order(newest)}"
            return Err(CommandError(code="invalid_input", message=message))
        where = _Where(next(iter(newest)), params.region, elo, pooled)
        try:
            files |= _builds(rows, seen, where, changed)
        except (ValidationError, ValueError) as e:
            return Err(CommandError(code="invalid_input", message=f"not publishable: {e}"))
    return Ok((files, next(iter(newest))))


type _Bracket = tuple[str, list[OptionEstimate], Played, set[str], dict[str, StaticData]]


def _bracket(
    estimates: EstimateStore,
    stores: Callable[[Path], MatchStore],
    source: BracketSource,
    params: PublishParams,
) -> Result[_Bracket, CommandError]:
    """One bracket: its name, the one its crawls' bands make (ADR-079), which a given `elo`
    must match; its estimates; what its games played, read one at a time; their patches; and
    the crawls' game data."""
    match crawl_bands(stores, source.crawl):
        case Err() as e:
            return e
        case Ok(value=bands):
            pass
    elo = published(bands)
    if elo is None:
        made = ", ".join(f"{name}: {' + '.join(pooled)}" for name, pooled in BRACKETS.items())
        message = f"the crawls hold {' + '.join(bands)} games: a bracket pools {made}"
        return Err(CommandError(code="invalid_params", message=message))
    if params.elo is not None and params.elo != elo:
        message = f"the crawls hold {elo} games, not {params.elo}"
        return Err(CommandError(code="invalid_params", message=message))
    match estimates.read_estimates(Path(source.estimates)):
        case Err(error=e):
            return Err(_error(e))
        case Ok(value=rows):
            pass
    match _statics(stores, source.crawl):
        case Err(error=e):
            return Err(_error(e))
        case Ok(value=statics):
            pass
    match each_game(stores, source.crawl):
        case Err() as e:
            return e
        case Ok(value=games):
            pass
    patches: set[str] = set()

    def noting(games: Iterable[Match | None]) -> Iterator[Match]:
        for game in games:
            if game is not None:
                patches.add(game.patch)
                yield game

    seen = played(noting(games), statics)
    return Ok((elo, list(rows), seen, patches, statics))


def _changes(
    stores: Callable[[Path], MatchStore], sources: Sequence[BracketSource]
) -> Result[tuple[dict[str, StaticData], dict[int, str]], CommandError]:
    """Every source's game data, and each item changed within its patches with the latest patch
    that changed it (ADR-088); nothing to compare with one patch."""
    statics: dict[str, StaticData] = {}
    for source in sources:
        match _statics(stores, source.crawl):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=found):
                statics = {**found, **statics}
    if len(statics) < 2:
        return Ok((statics, {}))
    try:
        return Ok((statics, changed_in(statics, statics)))
    except MissingFingerprintsError as e:
        return Err(CommandError(code="invalid_input", message=f"can't tell changed items: {e}"))


def _statics(
    stores: Callable[[Path], MatchStore], crawls: Sequence[str]
) -> Result[dict[str, StaticData], StoreError]:
    statics: dict[str, StaticData] = {}
    for crawl in crawls:
        match stores(Path(crawl)).read_static():
            case Err() as e:
                return e
            case Ok(value=found):
                for patch, static in found.items():
                    statics.setdefault(patch, static)
    return Ok(statics)


SPELL_PAIRS = 5
"""Spell pairs published per champion and role without estimates, most played first."""


@dataclass(frozen=True)
class _Where:
    """Where a bracket's builds go: the patch they're published under, their region and
    bracket, and the patches pooled (None: the patch alone)."""

    patch: str
    region: str
    elo: str
    pooled: list[str] | None

    def path(self, champion: str, role: str) -> str:
        window = "pooled/" if self.pooled is not None else ""
        return f"{self.region}/{self.elo}/{window}{champion}/{role}.json"


def _builds(
    rows: Sequence[OptionEstimate], seen: Played, where: _Where, changed: Mapping[int, str]
) -> dict[str, bytes]:
    """`{region}/{elo}/[pooled/]{champion}/{role}.json` -> canonical bytes, validated by the
    contract; an item option changed within the published patches says which changed it."""

    def since(*items: int) -> dict[str, str]:
        found = in_order(changed[i] for i in items if i in changed)
        return {"changedIn": found[-1]} if found else {}

    by_pick: defaultdict[tuple[str, str], list[OptionEstimate]] = defaultdict(list)
    for e in rows:
        by_pick[(e.champion, e.role)].append(e)
    files: dict[str, bytes] = {}
    for (champion, role), options in sorted(by_pick.items()):
        runes = [
            {
                "page": {
                    "primaryStyle": page.primary_style,
                    "subStyle": page.sub_style,
                    "perks": list(page.perks),
                },
                "games": games,
                **_numbers(e),
            }
            for e in _ranked(o for o in options if o.slot == 0)
            if (found := seen.pages.get((champion, role, int(e.option)))) is not None
            for page, games in [found]
        ]
        items = [
            {
                "slot": e.slot,
                "item": int(e.option),
                "picks": e.chosen,
                **_numbers(e),
                **since(int(e.option)),
            }
            for e in _ranked(o for o in options if 1 <= o.slot <= LATE_SLOT)
        ]
        choices = [
            {
                **_row_of(e.slot),
                "perks": _perks(e.option),
                "games": e.chosen,
                **_numbers(e, versus=_perks),
            }
            for e in _ranked(o for o in options if is_rune_slot(o.slot))
        ]
        spells = _spells(options, seen.spells.get((champion, role), []))
        build = Build.model_validate(
            {
                "schemaVersion": 1,
                "patch": where.patch,
                **({"patches": where.pooled} if where.pooled is not None else {}),
                "region": where.region,
                "elo": where.elo,
                "champion": champion,
                "role": role,
                "games": seen.games[(champion, role)],
                "runes": runes,
                "items": items,
                "starts": _purchases(options, seen, START_SLOT, since),
                "firstComponents": _purchases(options, seen, COMPONENTS_SLOT, since),
                "boots": [
                    {
                        "item": int(e.option),
                        **_against(e.slot),
                        "games": e.chosen,
                        **_numbers(e),
                        **since(int(e.option)),
                    }
                    for e in _ranked(o for o in options if BOOTS_SLOT <= o.slot <= BOOTS_SLOT + 3)
                ],
                "lateSlot": LATE_SLOT,
                "spells": spells,
                "runeChoices": choices,
                "skillLevels": _skills(options, SKILL_LEVELS_SLOT),
                "skillMax": _skills(options, SKILL_MAX_SLOT),
            }
        )
        skills = {k for k in ("skill_levels", "skill_max") if not getattr(build, k)}
        data = build.model_dump(mode="json", by_alias=True, exclude={"skill_order", *skills})
        if data.get("patches") is None:  # optional: absent, not null
            data.pop("patches", None)
        every = (*data["runes"], *data["items"], *data["runeChoices"], *data["spells"])
        orders = (*data.get("skillLevels", []), *data.get("skillMax", []))
        for option in (*every, *data["starts"], *data["firstComponents"], *data["boots"], *orders):
            for key in ("style", "row", "against", "changedIn"):  # optional: absent, not null
                if option.get(key, 0) is None:
                    option.pop(key)
            if option.get("comparison") is None:  # optional: absent, not null
                option.pop("comparison", None)
        files[where.path(champion, role)] = _canonical(data)
    return files


def _purchases(
    options: list[OptionEstimate],
    seen: Played,
    slot: int,
    since: Callable[..., dict[str, str]],
) -> list[dict[str, object]]:
    """A start or first components (ADR-071, ADR-072): the items estimated, and what is most
    often bought with them."""
    return [
        {
            "items": _perks(e.option),
            "buy": list(seen.purchases.get((e.champion, e.role, slot, e.option), _perks(e.option))),
            "games": e.chosen,
            **_numbers(e, versus=_perks),
            **since(*_perks(e.option)),
        }
        for e in _ranked(o for o in options if o.slot == slot)
    ]


def _spells(
    options: list[OptionEstimate], played: list[tuple[tuple[int, int], int]]
) -> list[dict[str, object]]:
    """The spell pairs (ADR-083): every pair estimated, in its usual key order, with the games
    played with it; without estimates, the most played pairs alone."""
    usual = {frozenset(pair): (pair, n) for pair, n in played}
    estimated = _ranked(o for o in options if o.slot == SPELLS_SLOT)
    if not estimated:
        return [
            {"spells": list(pair), "games": n, "wpa": None, "ci": None, "n": n, "flags": []}
            for pair, n in played[:SPELL_PAIRS]
        ]
    out: list[dict[str, object]] = []
    for e in estimated:
        ids = _perks(e.option)
        pair, games = usual.get(frozenset(ids), (tuple(ids), e.chosen))
        out.append({"spells": list(pair), "games": games, **_numbers(e, versus=_perks)})
    return out


SKILL_KEYS = "QWER"
"""Skill slots 1 to 4 as players name them."""


def _letters(option: str) -> list[str]:
    """A skill order's option, `"1,3,2"`, as its keys: `["Q", "E", "W"]`."""
    return [SKILL_KEYS[int(s) - 1] for s in option.split(",")]


def _skills(options: list[OptionEstimate], slot: int) -> list[dict[str, object]]:
    """The first levels or the max order (ADR-085): every order estimated, best first."""
    return [
        {"skills": _letters(e.option), "games": e.chosen, **_numbers(e, versus=_letters)}
        for e in _ranked(o for o in options if o.slot == slot)
    ]


def _against(slot: int) -> dict[str, str]:
    """Boots against one kind of enemy team (ADR-074): nothing for every game."""
    return {} if slot == BOOTS_SLOT else {"against": PROFILES[slot - BOOTS_SLOT - 1]}


CHAMPIONS = "champions.json"
"""Each champion's damage ratings and the enemy profile cuts, per patch (ADR-074)."""


def _champions(static: StaticData, patch: str) -> bytes:
    data = Champions.model_validate(
        {
            "schemaVersion": 1,
            "patch": patch,
            "physicalBelow": PHYSICAL_BELOW,
            "magicFrom": MAGIC_FROM,
            "champions": [
                {"id": c.champion_id, "attack": c.attack, "magic": c.magic}
                for c in sorted(static.champions.values(), key=lambda c: c.champion_id)
            ],
        }
    )
    return _canonical(data.model_dump(mode="json", by_alias=True))


def _ranked(options: Iterable[OptionEstimate]) -> list[OptionEstimate]:
    """By slot, then best first; options without a number last, most played first."""
    return sorted(options, key=lambda e: (e.slot, e.wpa is None, -(e.wpa or 0.0), -e.n, e.option))


def _row_of(slot: int) -> dict[str, object]:
    kind, tree, row = rune_row(slot)
    return {"kind": kind, "style": tree, "row": row}


def _perks(option: str) -> list[int]:
    """A rune row's option (one id, or a secondary pair `"low,high"`), or a start's items."""
    return [int(p) for p in option.split(",")]


def _numbers(e: OptionEstimate, versus: Callable[[str], object] = int) -> dict[str, object]:
    numbers: dict[str, object] = {
        "wpa": None if e.wpa is None else round(e.wpa, 5),
        "ci": None if e.ci is None else [round(e.ci[0], 5), round(e.ci[1], 5)],
        "n": e.n,
        "flags": sorted(e.flags),
    }
    if e.versus is not None and e.contrast is not None and e.q is not None:
        numbers["comparison"] = {
            "versus": versus(e.versus),
            "wpa": round(e.contrast, 5),
            "q": round(e.q, 5),
            **({"ci": [round(v, 5) for v in e.contrast_ci]} if e.contrast_ci else {}),
        }
    return numbers


def _canonical(data: object) -> bytes:
    return (
        json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _error(error: StoreError) -> CommandError:
    code = "not_found" if error.kind == "not_found" else "invalid_input"
    return CommandError(code=code, message=error.message)
