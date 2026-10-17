"""Riot payload parsing on malformed input: always a result or an error, never an exception."""

import copy
from typing import Any, cast

import httpx
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from riot_builders import buy, kill, match_payload, timeline_payload, tower
from riot_server import FakeRiot, run, source

from stronk_pipeline.domain.result import Err, Ok
from stronk_pipeline.ports import Rejected

MATCH = "/lol/match/v5/matches/EUW1_1"
BASE_MATCH = match_payload()
BASE_TIMELINE = timeline_payload(
    minutes=3, events=[buy(70_000, 1, 1036), kill(80_000, 1, 6), tower(90_000, 200)]
)

json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=8),
    lambda children: (
        st.lists(children, max_size=3) | st.dictionaries(st.text(max_size=8), children, max_size=3)
    ),
    max_leaves=6,
)


def paths(value: Any, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    found = [prefix] if prefix else []
    if isinstance(value, dict):
        for k, v in cast("dict[str, Any]", value).items():
            found += paths(v, (*prefix, k))
    elif isinstance(value, list):
        for i, v in enumerate(cast("list[Any]", value)[:3]):
            found += paths(v, (*prefix, i))
    return found


MATCH_PATHS = paths(BASE_MATCH)
TIMELINE_PATHS = paths(BASE_TIMELINE)


def mutate(base: Any, path: tuple[Any, ...], value: Any, delete: bool) -> Any:
    copied = copy.deepcopy(base)
    target = copied
    for key in path[:-1]:
        target = target[key]
    if delete and isinstance(target, dict):
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return copied


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    in_timeline=st.booleans(),
    index=st.integers(min_value=0),
    value=json_values,
    delete=st.booleans(),
)
def test_mutated_payloads_never_raise(
    in_timeline: bool, index: int, value: Any, delete: bool
) -> None:
    match, timeline = BASE_MATCH, BASE_TIMELINE
    if in_timeline:
        timeline = mutate(timeline, TIMELINE_PATHS[index % len(TIMELINE_PATHS)], value, delete)
    else:
        match = mutate(match, MATCH_PATHS[index % len(MATCH_PATHS)], value, delete)
    riot = FakeRiot({MATCH: match, f"{MATCH}/timeline": timeline})
    result = run(source(riot).fetch("EUW1_1", lambda _: None))
    assert isinstance(result, Ok | Err)


@settings(max_examples=100, deadline=None)
@given(body=st.binary(max_size=200))
def test_arbitrary_bodies_never_raise(body: bytes) -> None:
    riot = FakeRiot({MATCH: [httpx.Response(200, content=body)]})
    result = run(source(riot).fetch("EUW1_1", lambda _: None))
    assert isinstance(result, Err) or isinstance(result.value, Rejected)  # JSON is kept
