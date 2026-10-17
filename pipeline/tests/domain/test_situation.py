import pytest
from riot_builders import domain_match, domain_static, kill, monster, tower

from stronk_pipeline.domain.extract.situation import (
    SITUATION_FEATURES,
    enemy_magic_share,
    frame_at,
    player_situation,
    situation,
)

MIN = 60_000
STATIC = domain_static()


def features(values: tuple[float, ...]) -> dict[str, float]:
    return dict(zip(SITUATION_FEATURES, values, strict=True))


def test_frame_at_uses_the_last_frame_before() -> None:
    match = domain_match(minutes=5)
    assert frame_at(match, 0) == 0
    assert frame_at(match, 2 * MIN + 30_000) == 2
    assert frame_at(match, 99 * MIN) == 5


def test_gold_lead_from_the_frame() -> None:
    match = domain_match(gold={1: 100})  # participant 1 (team 100) earns 100 more per minute
    assert features(situation(match, 10 * MIN + 1_000, 100))["gold_diff"] == pytest.approx(1.0)


def test_kills_and_objectives_count_up_to_the_moment() -> None:
    events = [
        kill(3 * MIN, 1, 6),  # team 100 kills
        kill(4 * MIN, 7, 2),  # team 200 kills
        kill(5 * MIN, 0, 8),  # executed: still a team 100 kill
        tower(6 * MIN, 200),  # team 200 loses a tower
        monster(7 * MIN, 100),
        monster(8 * MIN, 200, "HORDE"),
        kill(20 * MIN, 1, 6),  # after the moment
    ]
    f = features(situation(domain_match(events=events), 10 * MIN, 100))
    assert f["kill_diff"] == 1
    assert f["tower_diff"] == 1
    assert f["dragon_diff"] == 1
    assert f["grub_diff"] == -1
    assert f["baron_diff"] == 0


def test_the_other_side_sees_the_opposite() -> None:
    events = [kill(3 * MIN, 1, 6), tower(6 * MIN, 100), monster(7 * MIN, 200)]
    match = domain_match(events=events, gold={3: 50, 9: 20})
    ours, theirs = situation(match, 12 * MIN, 100), situation(match, 12 * MIN, 200)
    assert ours == pytest.approx(tuple(-v for v in theirs))


def test_lane_gold_is_against_the_same_position() -> None:
    match = domain_match(gold={3: 100})  # team 100 MIDDLE
    lane_gold, _ = player_situation(match, 10 * MIN + 1_000, match.participant(3), STATIC)
    assert lane_gold == pytest.approx(1.0)
    lane_gold, _ = player_situation(match, 10 * MIN + 1_000, match.participant(8), STATIC)
    assert lane_gold == pytest.approx(-1.0)


def test_enemy_magic_share_from_champion_ratings() -> None:
    # Team 200 holds champions 6..10: 7 and 9 are fighters (2 magic), 6, 8, 10 mages (8 magic).
    match = domain_match()
    assert enemy_magic_share(match, 100, STATIC) == pytest.approx((3 * 8 + 2 * 2) / 50)
