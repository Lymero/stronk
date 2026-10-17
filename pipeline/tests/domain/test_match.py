from dataclasses import replace

import pytest
from riot_builders import buy, domain_match

from stronk_pipeline.domain.match import InvalidMatchError, patch_of


def test_participants_are_indexed_by_id() -> None:
    match = domain_match()
    assert [match.participant(i).participant_id for i in range(1, 11)] == list(range(1, 11))


@pytest.mark.parametrize(
    ("version", "patch"),
    [("16.20.717.2831", "16.20"), ("16.3.1", "16.3"), ("16", None), ("x.y.z", None), ("", None)],
)
def test_patch_of(version: str, patch: str | None) -> None:
    assert patch_of(version) == patch


def test_pseudonyms_are_stable_and_depend_on_the_salt() -> None:
    match = domain_match()
    once, twice = match.pseudonymized(b"a"), match.pseudonymized(b"a")
    other = match.pseudonymized(b"b")
    assert once == twice
    assert once.participants[0].player != match.participants[0].player
    assert once.participants[0].player != other.participants[0].player
    assert len({p.player for p in once.participants}) == 10


def test_wrong_team_size_is_rejected() -> None:
    match = domain_match()
    participants = list(match.participants)
    participants[0] = replace(participants[0], team=200)
    with pytest.raises(InvalidMatchError, match="players"):
        replace(match, participants=tuple(participants))


def test_result_must_agree_with_players() -> None:
    with pytest.raises(InvalidMatchError, match="disagree"):
        replace(domain_match(), winning_team=200)


def test_events_must_be_in_order() -> None:
    match = domain_match(events=[buy(100_000, 1, 1036), buy(200_000, 1, 1036)])
    with pytest.raises(InvalidMatchError, match="out of order"):
        replace(match, items=tuple(reversed(match.items)))


def test_events_must_name_real_participants() -> None:
    match = domain_match(events=[buy(100_000, 1, 1036)])
    with pytest.raises(InvalidMatchError, match="participant"):
        replace(match, items=(replace(match.items[0], participant_id=11),))
