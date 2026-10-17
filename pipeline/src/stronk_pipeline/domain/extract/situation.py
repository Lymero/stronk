"""Game state at a moment, from one team's side (docs/wpa-method.md, section 3).

Everything is a difference, own team minus enemy team, so 0 means even and the same numbers
seen from the other side are negated. Gold and XP come from the last minute frame at or
before the moment; kills and objectives count every event up to it.
"""

from __future__ import annotations

import bisect

from stronk_pipeline.domain.match import Match, Participant, Team
from stronk_pipeline.domain.static import StaticData

SITUATION_FEATURES = (
    "gold_diff",
    "xp_diff",
    "kill_diff",
    "tower_diff",
    "inhibitor_diff",
    "dragon_diff",
    "baron_diff",
    "herald_diff",
    "grub_diff",
)
"""Team-level state. Gold and XP in thousands."""

PLAYER_FEATURES = ("lane_gold_diff", "enemy_magic_share")
"""Player-level state: gold against the same position (thousands), enemy damage profile."""

MONSTER_FEATURES = {
    "DRAGON": "dragon_diff",
    "BARON_NASHOR": "baron_diff",
    "RIFTHERALD": "herald_diff",
    "HORDE": "grub_diff",
}


def frame_at(match: Match, timestamp: int) -> int:
    """Index of the last frame at or before `timestamp` (the first one if none is)."""
    stamps = [f.timestamp for f in match.frames]
    return max(bisect.bisect_right(stamps, timestamp) - 1, 0)


def situation(match: Match, timestamp: int, team: Team) -> tuple[float, ...]:
    """Values for SITUATION_FEATURES at `timestamp`, from `team`'s side."""
    frame = match.frames[frame_at(match, timestamp)]
    sign = {p.participant_id: 1 if p.team == team else -1 for p in match.participants}
    gold = sum(sign[i + 1] * f.total_gold for i, f in enumerate(frame.players))
    xp = sum(sign[i + 1] * f.xp for i, f in enumerate(frame.players))
    kills = sum(-sign[k.victim_id] for k in match.kills if k.timestamp <= timestamp)
    towers = sum(
        _lost(b.team, team)
        for b in match.buildings
        if b.timestamp <= timestamp and b.building == "tower"
    )
    inhibitors = sum(
        _lost(b.team, team)
        for b in match.buildings
        if b.timestamp <= timestamp and b.building == "inhibitor"
    )
    monsters = dict.fromkeys(MONSTER_FEATURES.values(), 0)
    for m in match.monsters:
        feature = MONSTER_FEATURES.get(m.monster)
        if feature is not None and m.timestamp <= timestamp:
            monsters[feature] += 1 if m.team == team else -1
    return (
        gold / 1000,
        xp / 1000,
        float(kills),
        float(towers),
        float(inhibitors),
        *(float(monsters[f]) for f in MONSTER_FEATURES.values()),
    )


def player_situation(
    match: Match, timestamp: int, participant: Participant, static: StaticData
) -> tuple[float, ...]:
    """Values for PLAYER_FEATURES at `timestamp` for `participant`."""
    frame = match.frames[frame_at(match, timestamp)]
    opponent = next(
        p
        for p in match.participants
        if p.team != participant.team and p.position == participant.position
    )
    lane_gold = (
        frame.players[participant.participant_id - 1].total_gold
        - frame.players[opponent.participant_id - 1].total_gold
    )
    return lane_gold / 1000, enemy_magic_share(match, participant.team, static)


def enemy_magic_share(match: Match, team: Team, static: StaticData) -> float:
    """Share of the enemy team's damage rating that is magic, from Data Dragon's ratings."""
    attack = magic = 0
    for p in match.participants:
        champion = static.champions.get(p.champion_id)
        if p.team != team and champion is not None:
            attack += champion.attack
            magic += champion.magic
    total = attack + magic
    return magic / total if total > 0 else 0.5


def _lost(owner: Team, team: Team) -> int:
    """+1 when the enemy lost the building, -1 when we did."""
    return -1 if owner == team else 1
