"""`publish`: WPA estimates and the crawls behind them -> signed build files for the app.

One file per champion and role (contracts/schemas/build.v1.schema.json): rune options from the
keystone estimates, each with the page most played with that keystone, and item options per
slot. Every file is validated against the contract, listed with its sha256 and size in the
patch manifest, and the manifest is signed (contracts/README.md). Spells and skill order have no
estimates yet and are published empty.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from stronk_contracts.build_v1 import Build
from stronk_contracts.champions_v1 import Champions
from stronk_contracts.manifest_v1 import Manifest
from stronk_pipeline.application.registry import Command, CommandError
from stronk_pipeline.domain.extract.decision_points import (
    BOOTS_SLOT,
    COMPONENTS_SLOT,
    LATE_SLOT,
    MAX_SLOT,
    START_SLOT,
    is_rune_slot,
    rune_row,
)
from stronk_pipeline.domain.extract.situation import MAGIC_FROM, PHYSICAL_BELOW, PROFILES
from stronk_pipeline.domain.match import Match
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


class PublishParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimates: Annotated[str, Field(min_length=1, description="Estimates from wpa.estimate")]
    crawl: Annotated[
        list[Annotated[str, Field(min_length=1)]],
        BeforeValidator(lambda v: [v] if isinstance(v, str) else v),
        Field(min_length=1, description="The crawl directories the estimates came from"),
    ]
    key: Annotated[str, Field(min_length=1, description="Signing key (signing.keygen)")]
    out: Annotated[str, Field(min_length=1, description="Data root, the CDN's layout")] = (
        "dist/data"
    )
    region: Annotated[str, Field(pattern=r"^[a-z0-9]{2,8}$")] = "all"
    elo: Annotated[str, Field(pattern=r"^[a-z_]{2,32}$")] = "master_plus"


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
        match estimates.read_estimates(Path(params.estimates)):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=rows):
                pass
        match _games(stores, params.crawl):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=(matches, statics)):
                pass
        patches = sorted({m.patch for m in matches})
        if len(patches) != 1:
            message = f"crawls must hold one patch, found {patches or 'none'}"
            return Err(CommandError(code="invalid_input", message=message))
        patch = patches[0]
        match keys.load(Path(params.key)):
            case Err(error=e):
                return Err(_error(e))
            case Ok(value=signer):
                pass
        try:
            files = _builds(rows, played(matches, statics), patch, params)
            if patch in statics:
                files[CHAMPIONS] = _champions(statics[patch], patch)
        except (ValidationError, ValueError) as e:
            return Err(CommandError(code="invalid_input", message=f"not publishable: {e}"))
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


def _games(
    stores: Callable[[Path], MatchStore], crawls: Sequence[str]
) -> Result[tuple[list[Match], dict[str, StaticData]], StoreError]:
    matches: dict[str, Match] = {}
    statics: dict[str, StaticData] = {}
    for crawl in crawls:
        store = stores(Path(crawl))
        match store.read_matches():
            case Err() as e:
                return e
            case Ok(value=(found, _)):
                for m in found:
                    matches.setdefault(m.match_id, m)
        match store.read_static():
            case Err() as e:
                return e
            case Ok(value=found_statics):
                for patch, static in found_statics.items():
                    statics.setdefault(patch, static)
    return Ok((list(matches.values()), statics))


SPELL_PAIRS = 5
"""Spell pairs published per champion and role, most played first."""


def _builds(
    rows: Sequence[OptionEstimate], seen: Played, patch: str, params: PublishParams
) -> dict[str, bytes]:
    """`{region}/{elo}/{champion}/{role}.json` -> canonical bytes, validated by the contract."""
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
            {"slot": e.slot, "item": int(e.option), "picks": e.chosen, **_numbers(e)}
            for e in _ranked(o for o in options if 1 <= o.slot <= MAX_SLOT)
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

        spells = [
            {"spells": list(pair), "games": n, "wpa": None, "ci": None, "n": n, "flags": []}
            for pair, n in seen.spells.get((champion, role), [])[:SPELL_PAIRS]
        ]
        build = Build.model_validate(
            {
                "schemaVersion": 1,
                "patch": patch,
                "region": params.region,
                "elo": params.elo,
                "champion": champion,
                "role": role,
                "games": seen.games[(champion, role)],
                "runes": runes,
                "items": items,
                "starts": _purchases(options, seen, START_SLOT),
                "firstComponents": _purchases(options, seen, COMPONENTS_SLOT),
                "boots": [
                    {"item": int(e.option), **_against(e.slot), "games": e.chosen, **_numbers(e)}
                    for e in _ranked(o for o in options if BOOTS_SLOT <= o.slot <= BOOTS_SLOT + 3)
                ],
                "lateSlot": LATE_SLOT,
                "spells": spells,
                "runeChoices": choices,
            }
        )
        data = build.model_dump(mode="json", by_alias=True, exclude={"skill_order"})
        every = (*data["runes"], *data["items"], *data["runeChoices"])
        for option in (*every, *data["starts"], *data["firstComponents"], *data["boots"]):
            for key in ("style", "row", "against"):  # optional: absent, not null
                if option.get(key, 0) is None:
                    option.pop(key)
            if option.get("comparison") is None:  # optional: absent, not null
                option.pop("comparison", None)
        files[f"{params.region}/{params.elo}/{champion}/{role}.json"] = _canonical(data)
    return files


def _purchases(options: list[OptionEstimate], seen: Played, slot: int) -> list[dict[str, object]]:
    """A start or first components (ADR-071, ADR-072): the items estimated, and what is most
    often bought with them."""
    return [
        {
            "items": _perks(e.option),
            "buy": list(seen.purchases.get((e.champion, e.role, slot, e.option), _perks(e.option))),
            "games": e.chosen,
            **_numbers(e, versus=_perks),
        }
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
