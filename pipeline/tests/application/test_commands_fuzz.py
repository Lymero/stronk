"""Every registered command, returns a result or an error, never raises."""

import json

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from stronk_pipeline.cli import build_registry

REGISTRY = build_registry()
COMMAND_IDS = [c.id for c in REGISTRY.commands()]

json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(max_size=20),
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=10), children, max_size=4)
    ),
    max_leaves=10,
)
field_names = st.sampled_from(["decisions", "estimator", "bootstrap_samples", "seed", "x"])
params = st.dictionaries(field_names, json_values, max_size=5).map(json.dumps) | st.text(
    max_size=50
)


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(command_id=st.sampled_from([*COMMAND_IDS, "no.such.command"]), raw=params)
def test_commands_never_raise(command_id: str, raw: str) -> None:
    REGISTRY.dispatch(command_id, raw)
