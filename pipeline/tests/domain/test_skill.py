import math

import pytest
from riot_builders import domain_match, puuid

from stronk_pipeline.domain.extract.skill import PRIOR_GAMES, prior_skill
from stronk_pipeline.domain.match import Match

DAY = 86_400_000


def games(count: int, winner: int = 100) -> list[Match]:
    """Games with the same ten players and champions, a day apart."""
    return [domain_match(f"EUW1_{i}", created=i * DAY, winner=winner) for i in range(count)]


def test_first_game_has_no_history() -> None:
    skill = prior_skill(games(1))
    assert skill[("EUW1_0", 1)] == (0.0, 0.0)


def test_uses_only_earlier_games() -> None:
    skill = prior_skill(games(3))
    rate = (2 + PRIOR_GAMES / 2) / (2 + PRIOR_GAMES)
    assert skill[("EUW1_2", 1)] == pytest.approx((rate - 0.5, math.log1p(2)))
    assert skill[("EUW1_2", 6)] == pytest.approx(
        (PRIOR_GAMES / 2 / (2 + PRIOR_GAMES) - 0.5, math.log1p(2))
    )


def test_input_order_does_not_matter() -> None:
    matches = games(4)
    assert prior_skill(matches) == prior_skill(list(reversed(matches)))


def test_history_is_per_champion() -> None:
    first = domain_match("EUW1_0", created=0)
    other_champion = domain_match("EUW1_1", created=DAY, champions=[2, 1, 3, 4, 5, 6, 7, 8, 9, 10])
    skill = prior_skill([first, other_champion])
    assert skill[("EUW1_1", 1)] == (0.0, 0.0)
    assert skill[("EUW1_1", 3)][1] == pytest.approx(math.log1p(1))


def test_history_is_per_player() -> None:
    first = domain_match("EUW1_0", created=0)
    strangers = domain_match("EUW1_1", created=DAY, players=[puuid(20 + i) for i in range(10)])
    assert prior_skill([first, strangers])[("EUW1_1", 1)] == (0.0, 0.0)
