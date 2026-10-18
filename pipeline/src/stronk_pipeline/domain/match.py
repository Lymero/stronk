"""A crawled game: the parts of match-v5 and its timeline that the pipeline uses.

Built from validated Riot payloads by the crawl adapter and stored instead of raw JSON
(docs/architecture.md, section 4). Players are pseudonymous: `player` is a keyed hash of the
Riot PUUID, stable within one crawl, so skill can be derived from prior games without keeping
identities.
"""

from __future__ import annotations

import hashlib
import hmac
import itertools
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol

POSITIONS = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
TEAMS = (100, 200)

type Position = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
type Team = Literal[100, 200]
type ItemAction = Literal["purchased", "sold", "destroyed", "undo"]
type Building = Literal["tower", "inhibitor"]


class InvalidMatchError(ValueError):
    """The game breaks an invariant; raised at construction, never later."""


@dataclass(frozen=True, slots=True)
class Participant:
    participant_id: int
    """1 to 10, the index used by timeline frames and events."""
    player: str
    team: Team
    champion_id: int
    position: Position
    win: bool
    keystone: int
    primary_style: int
    sub_style: int
    perks: tuple[int, ...]
    """Every selected rune, primary tree first, keystone included."""
    stat_perks: tuple[int, ...]
    spells: tuple[int, int]
    final_items: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PlayerFrame:
    total_gold: int
    current_gold: int
    xp: int
    level: int
    cs: int
    """Lane and jungle minions."""


@dataclass(frozen=True, slots=True)
class Frame:
    timestamp: int
    """Milliseconds since game start."""
    players: tuple[PlayerFrame, ...]
    """Indexed by participant_id - 1."""


@dataclass(frozen=True, slots=True)
class ItemEvent:
    timestamp: int
    participant_id: int
    action: ItemAction
    item_id: int
    """For an undo, the item before it (a purchase being undone); 0 when undoing a sale."""
    after_id: int = 0
    """For an undo, the item after it (a sale being undone); 0 otherwise."""


@dataclass(frozen=True, slots=True)
class KillEvent:
    timestamp: int
    killer_id: int
    """0 when no champion got the kill (executed by a turret or monster)."""
    victim_id: int
    assists: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class BuildingEvent:
    timestamp: int
    team: Team
    """The team that lost the building."""
    building: Building
    lane: str


@dataclass(frozen=True, slots=True)
class MonsterEvent:
    timestamp: int
    team: Team
    """The team that took the objective."""
    monster: str
    """DRAGON, BARON_NASHOR, RIFTHERALD, HORDE, ATAKHAN..."""
    subtype: str = ""


@dataclass(frozen=True, slots=True)
class SkillEvent:
    timestamp: int
    participant_id: int
    skill_slot: int


@dataclass(frozen=True, slots=True)
class Match:
    match_id: str
    platform: str
    patch: str
    """Major.minor of the game version, for example "16.20"."""
    game_version: str
    created_at: int
    """Milliseconds since the epoch."""
    duration: int
    """Seconds."""
    queue: int
    winning_team: Team
    participants: tuple[Participant, ...]
    frames: tuple[Frame, ...]
    items: tuple[ItemEvent, ...]
    kills: tuple[KillEvent, ...]
    buildings: tuple[BuildingEvent, ...]
    monsters: tuple[MonsterEvent, ...]
    skills: tuple[SkillEvent, ...]

    def __post_init__(self) -> None:
        if not self.match_id:
            raise InvalidMatchError("match_id is empty")
        self._check_participants()
        self._check_frames()
        self._check_events()

    def _check_participants(self) -> None:
        ids = [p.participant_id for p in self.participants]
        if ids != list(range(1, 11)):
            raise InvalidMatchError(f"participant ids must be 1 to 10 in order, got {ids}")
        for team in TEAMS:
            members = [p for p in self.participants if p.team == team]
            if len(members) != 5:
                raise InvalidMatchError(f"team {team} has {len(members)} players, not 5")
            if sorted(p.position for p in members) != sorted(POSITIONS):
                raise InvalidMatchError(f"team {team} does not fill every position once")
            if any(p.win != (team == self.winning_team) for p in members):
                raise InvalidMatchError(f"team {team} players disagree with the result")
        if any((p.team == 100) != (p.participant_id <= 5) for p in self.participants):
            # Riot's convention, relied on by tables that keep the participant, not the team.
            raise InvalidMatchError("participants 1 to 5 must be team 100, 6 to 10 team 200")

    def _check_frames(self) -> None:
        if not self.frames:
            raise InvalidMatchError("timeline has no frames")
        if any(len(f.players) != 10 for f in self.frames):
            raise InvalidMatchError("every frame needs all 10 players")
        if not _in_order(self.frames):
            raise InvalidMatchError("frames are out of order")

    def _check_events(self) -> None:
        if any(not 1 <= e.participant_id <= 10 for e in (*self.items, *self.skills)):
            raise InvalidMatchError("an event names a participant outside 1 to 10")
        if any(not 0 <= k.killer_id <= 10 or not 1 <= k.victim_id <= 10 for k in self.kills):
            raise InvalidMatchError("a kill names a participant outside 1 to 10")
        groups = (self.items, self.kills, self.buildings, self.monsters, self.skills)
        if not all(_in_order(g) for g in groups):
            raise InvalidMatchError("events are out of order")

    def participant(self, participant_id: int) -> Participant:
        return self.participants[participant_id - 1]

    def pseudonymized(self, salt: bytes) -> Match:
        """The same game with every `player` replaced by its keyed hash."""
        participants = tuple(
            replace(p, player=pseudonym(p.player, salt)) for p in self.participants
        )
        return replace(self, participants=participants)


class _Timed(Protocol):
    @property
    def timestamp(self) -> int: ...


def _in_order(items: Sequence[_Timed]) -> bool:
    return all(a.timestamp <= b.timestamp for a, b in itertools.pairwise(items))


def pseudonym(player: str, salt: bytes) -> str:
    """A stable, non-reversible id for a player: HMAC-SHA256 of their id under `salt`."""
    return hmac.new(salt, player.encode(), hashlib.sha256).hexdigest()


def patch_of(game_version: str) -> str | None:
    """ "16.20.717.2831" -> "16.20"; None if the version is not of that form."""
    parts = game_version.split(".")
    if len(parts) < 2 or not all(p.isdigit() for p in parts[:2]):
        return None
    return f"{int(parts[0])}.{int(parts[1])}"
