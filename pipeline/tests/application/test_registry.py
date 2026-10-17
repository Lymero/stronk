import pytest
from pydantic import BaseModel

from stronk_pipeline.application.registry import Command, CommandError, CommandRegistry
from stronk_pipeline.domain.result import Err, Ok, Result


class EchoParams(BaseModel):
    text: str


class EchoResult(BaseModel):
    text: str


def echo(params: EchoParams) -> Result[EchoResult, CommandError]:
    return Ok(EchoResult(text=params.text))


def boom(params: EchoParams) -> Result[EchoResult, CommandError]:
    raise RuntimeError("bug")


def registry() -> CommandRegistry:
    return CommandRegistry(
        [
            Command("test.echo", "Echo", EchoParams, EchoResult, echo),
            Command("test.boom", "Raise", EchoParams, EchoResult, boom),
        ]
    )


def test_dispatches_json_and_mapping_params() -> None:
    assert registry().dispatch("test.echo", '{"text": "hi"}') == Ok(EchoResult(text="hi"))
    assert registry().dispatch("test.echo", {"text": "hi"}) == Ok(EchoResult(text="hi"))


@pytest.mark.parametrize(
    ("command_id", "params", "code"),
    [
        ("test.nope", "{}", "unknown_command"),
        ("test.echo", "{}", "invalid_params"),
        ("test.echo", "not json", "invalid_params"),
        ("test.echo", '{"text": 3}', "invalid_params"),
        ("test.boom", '{"text": "x"}', "internal"),
    ],
)
def test_failures_become_errors(command_id: str, params: str, code: str) -> None:
    result = registry().dispatch(command_id, params)
    assert isinstance(result, Err)
    assert result.error.code == code


def test_duplicate_ids_are_rejected() -> None:
    command = Command("test.echo", "Echo", EchoParams, EchoResult, echo)
    with pytest.raises(ValueError, match="duplicate"):
        CommandRegistry([command, command])
