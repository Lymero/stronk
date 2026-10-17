"""Riot and Data Dragon payloads, validated at the boundary and turned into domain types.

Only the fields the pipeline uses are declared; everything else is ignored, so new fields
Riot adds don't break the crawl. A payload missing a declared field, or with a wrong type, is
rejected as a whole.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from stronk_pipeline.domain.match import (
    BuildingEvent,
    Frame,
    InvalidMatchError,
    ItemEvent,
    KillEvent,
    Match,
    MonsterEvent,
    Participant,
    PlayerFrame,
    Position,
    SkillEvent,
    Team,
    patch_of,
)
from stronk_pipeline.domain.static import Champion, Item, StaticData
from stronk_pipeline.ports import MatchHeader

RIFT = 11


class _Payload(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)


# --- league-v4 ---------------------------------------------------------------------------


class LeagueEntry(_Payload):
    puuid: Annotated[str, Field(min_length=1)]
    league_points: int = Field(alias="leaguePoints")


class League(_Payload):
    entries: list[LeagueEntry]


# --- match-v5 ----------------------------------------------------------------------------


class _Selection(_Payload):
    perk: int


class _Style(_Payload):
    description: str
    style: int
    selections: list[_Selection]


class _StatPerks(_Payload):
    offense: int
    flex: int
    defense: int


class _Perks(_Payload):
    stat_perks: _StatPerks = Field(alias="statPerks")
    styles: list[_Style]


class _MatchParticipant(_Payload):
    participant_id: int = Field(alias="participantId")
    puuid: str
    team_id: Team = Field(alias="teamId")
    champion_id: int = Field(alias="championId")
    team_position: str = Field(alias="teamPosition")
    win: bool
    perks: _Perks
    summoner1_id: int = Field(alias="summoner1Id")
    summoner2_id: int = Field(alias="summoner2Id")
    item0: int
    item1: int
    item2: int
    item3: int
    item4: int
    item5: int
    item6: int
    early_surrender: bool = Field(default=False, alias="gameEndedInEarlySurrender")


class _MatchInfo(_Payload):
    game_creation: int = Field(alias="gameCreation")
    game_duration: int = Field(alias="gameDuration")
    game_version: str = Field(alias="gameVersion")
    map_id: int = Field(alias="mapId")
    queue_id: int = Field(alias="queueId")
    platform_id: str = Field(alias="platformId")
    participants: list[_MatchParticipant]


class _MatchMetadata(_Payload):
    match_id: str = Field(alias="matchId")


class MatchPayload(_Payload):
    metadata: _MatchMetadata
    info: _MatchInfo

    def header(self) -> MatchHeader:
        return MatchHeader(
            match_id=self.metadata.match_id,
            patch=patch_of(self.info.game_version),
            queue=self.info.queue_id,
            map_id=self.info.map_id,
            remake=any(p.early_surrender for p in self.info.participants),
        )


# --- match-v5 timeline -------------------------------------------------------------------


class _ParticipantFrame(_Payload):
    total_gold: int = Field(alias="totalGold")
    current_gold: int = Field(alias="currentGold")
    xp: int
    level: int
    minions_killed: int = Field(alias="minionsKilled")
    jungle_minions_killed: int = Field(alias="jungleMinionsKilled")


class _ItemEvent(_Payload):
    type: Literal["ITEM_PURCHASED", "ITEM_SOLD", "ITEM_DESTROYED"]
    timestamp: int
    participant_id: int = Field(alias="participantId")
    item_id: int = Field(alias="itemId")


class _ItemUndo(_Payload):
    type: Literal["ITEM_UNDO"]
    timestamp: int
    participant_id: int = Field(alias="participantId")
    before_id: int = Field(alias="beforeId")
    after_id: int = Field(alias="afterId")


class _ChampionKill(_Payload):
    type: Literal["CHAMPION_KILL"]
    timestamp: int
    killer_id: int = Field(alias="killerId")
    victim_id: int = Field(alias="victimId")
    assists: list[int] = Field(default_factory=list[int], alias="assistingParticipantIds")


class _BuildingKill(_Payload):
    type: Literal["BUILDING_KILL"]
    timestamp: int
    team_id: Team = Field(alias="teamId")
    building_type: str = Field(alias="buildingType")
    lane_type: str = Field(default="", alias="laneType")


class _MonsterKill(_Payload):
    type: Literal["ELITE_MONSTER_KILL"]
    timestamp: int
    killer_team_id: Team | Literal[300] = Field(alias="killerTeamId")  # 300: neutral, see below
    monster_type: str = Field(alias="monsterType")
    monster_sub_type: str = Field(default="", alias="monsterSubType")


class _SkillLevelUp(_Payload):
    type: Literal["SKILL_LEVEL_UP"]
    timestamp: int
    participant_id: int = Field(alias="participantId")
    skill_slot: int = Field(alias="skillSlot")


type _KnownEvent = Annotated[
    _ItemEvent | _ItemUndo | _ChampionKill | _BuildingKill | _MonsterKill | _SkillLevelUp,
    Field(discriminator="type"),
]
_KNOWN_EVENTS = frozenset(
    {
        "ITEM_PURCHASED",
        "ITEM_SOLD",
        "ITEM_DESTROYED",
        "ITEM_UNDO",
        "CHAMPION_KILL",
        "BUILDING_KILL",
        "ELITE_MONSTER_KILL",
        "SKILL_LEVEL_UP",
    }
)


class _TimelineFrame(_Payload):
    timestamp: int
    participant_frames: dict[str, _ParticipantFrame] = Field(alias="participantFrames")
    events: list[dict[str, object]]


class _TimelineInfo(_Payload):
    frames: list[_TimelineFrame]


class TimelinePayload(_Payload):
    info: _TimelineInfo


class _Event(_Payload):
    event: _KnownEvent


# --- Data Dragon -------------------------------------------------------------------------


class _ChampionInfo(_Payload):
    attack: int
    magic: int


class _ChampionEntry(_Payload):
    id: str
    key: str
    tags: list[str]
    info: _ChampionInfo


class ChampionsPayload(_Payload):
    data: dict[str, _ChampionEntry]


class _Gold(_Payload):
    total: int
    purchasable: bool


class _ItemEntry(_Payload):
    name: str
    gold: _Gold
    tags: list[str] = Field(default_factory=list[str])
    maps: dict[str, bool] = Field(default_factory=dict[str, bool])
    builds_from: list[str] = Field(default_factory=list[str], alias="from")
    builds_into: list[str] = Field(default_factory=list[str], alias="into")
    in_store: bool = Field(default=True, alias="inStore")
    required_champion: str = Field(default="", alias="requiredChampion")
    required_ally: str = Field(default="", alias="requiredAlly")


class ItemsPayload(_Payload):
    data: dict[str, _ItemEntry]


# --- conversion --------------------------------------------------------------------------


class PayloadError(ValueError):
    """A payload that validated but cannot form a consistent domain object."""


def to_match(match: MatchPayload, timeline: TimelinePayload) -> Match:
    """Raises PayloadError, or pydantic's ValidationError for a malformed event."""
    info = match.info
    patch = patch_of(info.game_version)
    if patch is None:
        raise PayloadError(f"unrecognised game version {info.game_version!r}")
    participants = tuple(_participant(p) for p in sorted(info.participants, key=_by_id))
    winners: set[Team] = {p.team for p in participants if p.win}
    if len(winners) != 1:
        raise PayloadError("exactly one team must win")
    events = [e for frame in timeline.info.frames for e in frame.events]
    parsed = [_Event.model_validate({"event": e}).event for e in events if _is_known(e)]
    attributed = [e for e in parsed if not _is_ownerless(e)]
    known = sorted(attributed, key=lambda e: e.timestamp)  # stable: same-time events keep order
    try:
        return Match(
            match_id=match.metadata.match_id,
            platform=info.platform_id,
            patch=patch,
            game_version=info.game_version,
            created_at=info.game_creation,
            duration=info.game_duration,
            queue=info.queue_id,
            winning_team=winners.pop(),
            participants=participants,
            frames=tuple(_frame(f) for f in timeline.info.frames),
            items=tuple(_item(e) for e in known if isinstance(e, _ItemEvent | _ItemUndo)),
            kills=tuple(
                KillEvent(e.timestamp, e.killer_id, e.victim_id, tuple(e.assists))
                for e in known
                if isinstance(e, _ChampionKill)
            ),
            buildings=tuple(_building(e) for e in known if isinstance(e, _BuildingKill)),
            monsters=tuple(
                MonsterEvent(e.timestamp, e.killer_team_id, e.monster_type, e.monster_sub_type)
                for e in known
                if isinstance(e, _MonsterKill) and e.killer_team_id != _NEUTRAL
            ),
            skills=tuple(
                SkillEvent(e.timestamp, e.participant_id, e.skill_slot)
                for e in known
                if isinstance(e, _SkillLevelUp)
            ),
        )
    except InvalidMatchError as e:
        raise PayloadError(str(e)) from e


def to_static(version: str, champions: ChampionsPayload, items: ItemsPayload) -> StaticData:
    try:
        return StaticData(
            version=version,
            champions={
                int(c.key): Champion(int(c.key), c.id, tuple(c.tags), c.info.attack, c.info.magic)
                for c in champions.data.values()
            },
            items={
                int(item_id): Item(
                    item_id=int(item_id),
                    name=i.name,
                    total_gold=i.gold.total,
                    purchasable=i.gold.purchasable,
                    on_rift=i.maps.get(str(RIFT), False) and i.in_store,
                    tags=tuple(i.tags),
                    builds_from=tuple(int(c) for c in i.builds_from),
                    builds_into=tuple(int(c) for c in i.builds_into),
                    champion_specific=bool(i.required_champion or i.required_ally),
                )
                for item_id, i in items.data.items()
            },
        )
    except ValueError as e:  # non-numeric ids
        raise PayloadError(f"Data Dragon {version}: {e}") from e


def _by_id(p: _MatchParticipant) -> int:
    return p.participant_id


def _participant(p: _MatchParticipant) -> Participant:
    styles = {s.description: s for s in p.perks.styles}
    primary, sub = styles.get("primaryStyle"), styles.get("subStyle")
    if primary is None or sub is None or not primary.selections:
        raise PayloadError(f"participant {p.participant_id} has no complete rune page")
    if p.team_position not in ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"):
        raise PayloadError(f"participant {p.participant_id} has no position")
    position: Position = p.team_position  # pyright: ignore[reportAssignmentType]
    stat = p.perks.stat_perks
    return Participant(
        participant_id=p.participant_id,
        player=p.puuid,
        team=p.team_id,
        champion_id=p.champion_id,
        position=position,
        win=p.win,
        keystone=primary.selections[0].perk,
        primary_style=primary.style,
        sub_style=sub.style,
        perks=tuple(s.perk for s in (*primary.selections, *sub.selections)),
        stat_perks=(stat.offense, stat.flex, stat.defense),
        spells=(p.summoner1_id, p.summoner2_id),
        final_items=(p.item0, p.item1, p.item2, p.item3, p.item4, p.item5, p.item6),
    )


def _frame(f: _TimelineFrame) -> Frame:
    players: list[PlayerFrame] = []
    for participant_id in range(1, 11):
        pf = f.participant_frames.get(str(participant_id))
        if pf is None:
            raise PayloadError(f"frame at {f.timestamp} lacks participant {participant_id}")
        cs = pf.minions_killed + pf.jungle_minions_killed
        players.append(PlayerFrame(pf.total_gold, pf.current_gold, pf.xp, pf.level, cs))
    return Frame(f.timestamp, tuple(players))


def _item(e: _ItemEvent | _ItemUndo) -> ItemEvent:
    if isinstance(e, _ItemUndo):
        return ItemEvent(e.timestamp, e.participant_id, "undo", e.before_id, e.after_id)
    match e.type:
        case "ITEM_PURCHASED":
            return ItemEvent(e.timestamp, e.participant_id, "purchased", e.item_id)
        case "ITEM_SOLD":
            return ItemEvent(e.timestamp, e.participant_id, "sold", e.item_id)
        case "ITEM_DESTROYED":
            return ItemEvent(e.timestamp, e.participant_id, "destroyed", e.item_id)


def _building(e: _BuildingKill) -> BuildingEvent:
    building = "tower" if e.building_type == "TOWER_BUILDING" else "inhibitor"
    return BuildingEvent(e.timestamp, e.team_id, building, e.lane_type)


_NEUTRAL: Final = 300
"""Killer team of an elite monster no team took (seen 2026-10 on a Void Grub despawning, with
killerId 0). No team gains it, so those kills are dropped."""


def _is_ownerless(event: object) -> bool:
    """Live timelines carry a few item and skill events with participant 0 (seen 2026-10 on
    item 3865 and one SKILL_LEVEL_UP per game). They belong to no player, so they are dropped."""
    return isinstance(event, _ItemEvent | _ItemUndo | _SkillLevelUp) and event.participant_id == 0


def _is_known(event: dict[str, object]) -> bool:
    kind = event.get("type")
    return isinstance(kind, str) and kind in _KNOWN_EVENTS
