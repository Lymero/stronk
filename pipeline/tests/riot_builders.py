"""Small Riot and Data Dragon payloads, shaped like the real ones, for offline tests.

Champions 1 to 10 alternate Fighter (physical) and Mage (magic). Items form two recipes that
share a component, plus one with a unique component, so unfinished slots can be inferred
or not:

    Caulfield 3133 <- Long Sword 1036 x2      Phage 3044 <- Long Sword 1036, Ruby 1028
    Black Cleaver 3071 <- Phage, Caulfield    Death's Dance 6333 <- Pickaxe 1037, Caulfield
    Infinity Edge 3031 <- BF Sword 1038, Pickaxe 1037
"""

from __future__ import annotations

import random
from typing import Any

from stronk_pipeline.adapters.riot.payloads import (
    ChampionsPayload,
    ItemsPayload,
    MatchPayload,
    TimelinePayload,
    to_match,
    to_static,
)
from stronk_pipeline.domain.match import Match
from stronk_pipeline.domain.static import StaticData

POSITIONS = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
KEYSTONES = (8010, 8112, 8214, 8437, 8351)
VERSION = "16.20.717.2831"
DDRAGON_VERSION = "16.20.1"

type Json = dict[str, Any]


def puuid(n: int) -> str:
    return f"{n:02d}".ljust(78, "x")


def ddragon_champions() -> Json:
    data: Json = {}
    for key in range(1, 11):
        mage = key % 2 == 0
        data[f"Champ{key}"] = {
            "id": f"Champ{key}",
            "key": str(key),
            "name": f"Champ {key}",
            "tags": ["Mage", "Support"] if mage else ["Fighter", "Tank"],
            "info": {"attack": 2 if mage else 8, "defense": 5, "magic": 8 if mage else 2},
        }
    return {"type": "champion", "version": DDRAGON_VERSION, "data": data}


def _item(
    name: str, total: int, *, into: tuple[int, ...] = (), built: tuple[int, ...] = (), **extra: Any
) -> Json:
    item: Json = {
        "name": name,
        "gold": {"base": total, "purchasable": True, "total": total, "sell": total * 7 // 10},
        "tags": [],
        "maps": {"11": True, "12": True},
    }
    if into:
        item["into"] = [str(i) for i in into]
    if built:
        item["from"] = [str(i) for i in built]
    item.update(extra)
    return item


def ddragon_items() -> Json:
    return {
        "type": "item",
        "version": DDRAGON_VERSION,
        "data": {
            "1036": _item(
                "Long Sword",
                350,
                into=(
                    3133,
                    3044,
                ),
            ),
            "1028": _item("Ruby Crystal", 400, into=(3044,)),
            "1037": _item(
                "Pickaxe",
                875,
                into=(
                    6333,
                    3031,
                ),
            ),
            "1038": _item("B. F. Sword", 1300, into=(3031,)),
            "3133": _item(
                "Caulfield's Warhammer",
                1100,
                into=(
                    3071,
                    6333,
                ),
                built=(
                    1036,
                    1036,
                ),
            ),
            "3044": _item(
                "Phage",
                1100,
                into=(3071,),
                built=(
                    1036,
                    1028,
                ),
            ),
            "3071": _item(
                "Black Cleaver",
                3000,
                built=(
                    3044,
                    3133,
                ),
            ),
            "6333": _item(
                "Death's Dance",
                3300,
                built=(
                    1037,
                    3133,
                ),
            ),
            "3031": _item(
                "Infinity Edge",
                3400,
                built=(
                    1038,
                    1037,
                ),
            ),
            "1001": _item("Boots", 300, into=(3006,), tags=["Boots"]),
            "3006": _item("Berserker's Greaves", 1100, built=(1001,), tags=["Boots"]),
            "2003": _item("Health Potion", 50, tags=["Consumable"]),
            "1055": _item("Doran's Blade", 450),
            "3340": _item("Stealth Ward", 0, tags=["Trinket"]),
            "3599": _item("Kalista's Spear", 3000, built=(1036,), requiredChampion="Kalista"),
            "223071": _item("Black Cleaver (Arena)", 3000, built=(3044,), maps={"30": True}),
        },
    }


def match_payload(
    match_id: str = "EUW1_1",
    *,
    created: int = 1_760_000_000_000,
    winner: int = 100,
    players: list[str] | None = None,
    champions: list[int] | None = None,
    version: str = VERSION,
    queue: int = 420,
    duration: int = 1800,
    early_surrender: bool = False,
) -> Json:
    players = players if players is not None else [puuid(i) for i in range(1, 11)]
    champions = champions if champions is not None else list(range(1, 11))
    participants: list[Json] = []
    for i in range(10):
        team = 100 if i < 5 else 200
        primary = [KEYSTONES[i % 5], 8139, 8138, 8135]
        participants.append(
            {
                "participantId": i + 1,
                "puuid": players[i],
                "riotIdGameName": f"Player{i}",
                "riotIdTagline": "EUW",
                "teamId": team,
                "championId": champions[i],
                "championName": f"Champ{champions[i]}",
                "teamPosition": POSITIONS[i % 5],
                "win": team == winner,
                "perks": {
                    "statPerks": {"offense": 5008, "flex": 5008, "defense": 5011},
                    "styles": [
                        {
                            "description": "primaryStyle",
                            "style": 8100,
                            "selections": [{"perk": p, "var1": 0} for p in primary],
                        },
                        {
                            "description": "subStyle",
                            "style": 8300,
                            "selections": [{"perk": 8345}, {"perk": 8347}],
                        },
                    ],
                },
                "summoner1Id": 4,
                "summoner2Id": 14,
                **{f"item{s}": 0 for s in range(7)},
                "gameEndedInEarlySurrender": early_surrender,
            }
        )
    return {
        "metadata": {"dataVersion": "2", "matchId": match_id, "participants": players},
        "info": {
            "gameCreation": created,
            "gameDuration": duration,
            "gameVersion": version,
            "mapId": 11,
            "queueId": queue,
            "platformId": "EUW1",
            "participants": participants,
            "teams": [{"teamId": 100, "win": winner == 100}, {"teamId": 200, "win": winner == 200}],
        },
    }


def timeline_payload(
    *,
    minutes: int = 30,
    events: list[Json] | None = None,
    gold: dict[int, int] | None = None,
) -> Json:
    """`gold`: extra gold per minute for some participants, to create leads."""
    events = sorted(events or [], key=lambda e: e["timestamp"])
    gold = gold or {}
    frames: list[Json] = []
    for minute in range(minutes + 1):
        start, end = minute * 60_000, (minute + 1) * 60_000
        frames.append(
            {
                "timestamp": start + (minute > 0) * 17,
                "participantFrames": {
                    str(p): {
                        "participantId": p,
                        "currentGold": 100,
                        "totalGold": 500 + minute * (400 + gold.get(p, 0)),
                        "xp": minute * 500,
                        "level": min(1 + minute // 2, 18),
                        "minionsKilled": minute * 7,
                        "jungleMinionsKilled": 0,
                        "position": {"x": 0, "y": 0},
                    }
                    for p in range(1, 11)
                },
                "events": [
                    {"type": "PAUSE_END", "timestamp": 0} if minute == 0 else {"type": "LEVEL_UP"},
                    *(e for e in events if start <= e["timestamp"] < end),
                ],
            }
        )
    return {"metadata": {"matchId": "x"}, "info": {"frameInterval": 60000, "frames": frames}}


def buy(t: int, pid: int, item: int) -> Json:
    return {"type": "ITEM_PURCHASED", "timestamp": t, "participantId": pid, "itemId": item}


def sell(t: int, pid: int, item: int) -> Json:
    return {"type": "ITEM_SOLD", "timestamp": t, "participantId": pid, "itemId": item}


def undo(t: int, pid: int, before: int, after: int = 0) -> Json:
    return {
        "type": "ITEM_UNDO",
        "timestamp": t,
        "participantId": pid,
        "beforeId": before,
        "afterId": after,
        "goldGain": 100,
    }


def kill(t: int, killer: int, victim: int) -> Json:
    return {
        "type": "CHAMPION_KILL",
        "timestamp": t,
        "killerId": killer,
        "victimId": victim,
        "assistingParticipantIds": [],
    }


def tower(t: int, owner: int) -> Json:
    return {
        "type": "BUILDING_KILL",
        "timestamp": t,
        "teamId": owner,
        "buildingType": "TOWER_BUILDING",
        "laneType": "MID_LANE",
        "towerType": "OUTER_TURRET",
        "killerId": 0,
    }


def monster(t: int, team: int, kind: str = "DRAGON") -> Json:
    return {
        "type": "ELITE_MONSTER_KILL",
        "timestamp": t,
        "killerTeamId": team,
        "monsterType": kind,
        "monsterSubType": "FIRE_DRAGON" if kind == "DRAGON" else "",
        "killerId": 1,
    }


def league(players: list[str]) -> Json:
    return {
        "tier": "CHALLENGER",
        "queue": "RANKED_SOLO_5x5",
        "entries": [
            {"puuid": p, "leaguePoints": 1000 - i, "summonerId": f"s{i}", "wins": 1, "losses": 1}
            for i, p in enumerate(players)
        ],
    }


def domain_static() -> StaticData:
    return to_static(
        DDRAGON_VERSION,
        ChampionsPayload.model_validate(ddragon_champions()),
        ItemsPayload.model_validate(ddragon_items()),
    )


def domain_match(
    match_id: str = "EUW1_1",
    *,
    events: list[Json] | None = None,
    gold: dict[int, int] | None = None,
    minutes: int = 30,
    **match: Any,
) -> Match:
    return to_match(
        MatchPayload.model_validate(match_payload(match_id, **match)),
        TimelinePayload.model_validate(timeline_payload(minutes=minutes, events=events, gold=gold)),
    )


BUILDS = ((1036, 1036, 3133, 1028, 3071), (1037, 3133, 6333), (1038, 1037, 3031))


def random_game_events(rng: random.Random) -> list[Json]:
    """Every player buys starting items, then two or three random builds."""
    events: list[Json] = []
    for pid in range(1, 11):
        events.append(buy(rng.randint(1_000, 20_000), pid, 1055))
        t = rng.randint(180_000, 300_000)
        for _ in range(rng.randint(2, 3)):
            for item in rng.choice(BUILDS):
                events.append(buy(t, pid, item))
                t += rng.randint(30_000, 120_000)
    return events


def fake_ladder(games: int, players: int = 3, seed: int = 0) -> dict[str, Any]:
    """Responses for a crawl: one Challenger league, `players` histories, `games` games."""
    rng = random.Random(seed)
    ladder = [puuid(50 + i) for i in range(players)]
    responses: dict[str, Any] = {
        "/lol/league/v4/challengerleagues/by-queue/RANKED_SOLO_5x5": league(ladder),
    }
    histories: dict[str, list[str]] = {p: [] for p in ladder}
    for g in range(games):
        match_id = f"EUW1_{1000 + g}"
        owner = ladder[g % players]
        histories[owner].insert(0, match_id)
        roster = [owner, *(puuid(rng.randint(0, 40)) for _ in range(9))]
        if len(set(roster)) < 10:
            roster = [owner, *(puuid(100 + 10 * g + i) for i in range(9))]
        responses[f"/lol/match/v5/matches/{match_id}"] = match_payload(
            match_id,
            created=1_760_000_000_000 + g * 3_600_000,
            winner=rng.choice((100, 200)),
            players=roster,
            champions=rng.sample(range(1, 11), 10),
        )
        responses[f"/lol/match/v5/matches/{match_id}/timeline"] = timeline_payload(
            minutes=rng.randint(22, 35), events=random_game_events(rng)
        )
    for owner, ids in histories.items():
        responses[f"/lol/match/v5/matches/by-puuid/{owner}/ids"] = ids
    return responses
