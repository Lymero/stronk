"""The command registry: every use case, addressable by id, with typed params, result and errors.

Entry points (CLI, later an MCP server) only dispatch here. `dispatch` never raises: unknown
ids, invalid params and unexpected failures all come back as a `CommandError`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from stronk_pipeline.domain.result import Err, Result

log = logging.getLogger(__name__)

type ErrorCode = Literal[
    "unknown_command", "invalid_params", "not_found", "invalid_input", "internal"
]


class CommandError(BaseModel):
    code: ErrorCode
    message: str


@dataclass(frozen=True)
class Command[P: BaseModel, R: BaseModel]:
    id: str
    summary: str
    params: type[P]
    result: type[R]
    run: Callable[[P], Result[R, CommandError]]


type AnyCommand = Command[Any, Any]


class CommandRegistry:
    def __init__(self, commands: Iterable[AnyCommand]) -> None:
        self._commands: dict[str, AnyCommand] = {}
        for command in commands:
            if command.id in self._commands:
                raise ValueError(f"duplicate command id: {command.id}")
            self._commands[command.id] = command

    def commands(self) -> list[AnyCommand]:
        return [self._commands[k] for k in sorted(self._commands)]

    def dispatch(
        self, command_id: str, params: str | Mapping[str, object]
    ) -> Result[BaseModel, CommandError]:
        command = self._commands.get(command_id)
        if command is None:
            known = ", ".join(sorted(self._commands))
            return Err(
                CommandError(code="unknown_command", message=f"{command_id!r}; known: {known}")
            )
        try:
            parsed: BaseModel = (
                command.params.model_validate_json(params)
                if isinstance(params, str)
                else command.params.model_validate(params)
            )
        except ValidationError as e:
            return Err(CommandError(code="invalid_params", message=_describe(e)))
        try:
            return command.run(parsed)
        except Exception:  # The never-crash boundary: report, don't propagate.
            log.exception("command %s failed", command_id)
            return Err(CommandError(code="internal", message=f"{command_id} failed unexpectedly"))


def _describe(error: ValidationError) -> str:
    return json.dumps(
        [{"loc": list(e["loc"]), "msg": e["msg"]} for e in error.errors(include_url=False)]
    )
