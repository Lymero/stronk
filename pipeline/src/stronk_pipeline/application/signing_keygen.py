"""`signing.keygen`: a new data signing key, outside the repository (docs/security.md).

The secret key stays where it is written; the public key (`<out>.pub`, also in the result) is
what the app needs to trust published data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from stronk_pipeline.application.registry import Command, CommandError
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.ports import SigningKeys


class KeygenParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    out: Annotated[str, Field(min_length=1, description="Secret key file to create")]


class KeygenResult(BaseModel):
    key_id: str
    public_key: str
    outputs: list[str]


def signing_keygen_command(keys: SigningKeys) -> Command[KeygenParams, KeygenResult]:
    def run(params: KeygenParams) -> Result[KeygenResult, CommandError]:
        path = Path(params.out)
        match keys.generate(path):
            case Err(error=e):
                return Err(CommandError(code="invalid_input", message=e.message))
            case Ok(value=signer):
                pass
        public = path.with_name(path.name + ".pub")
        return Ok(
            KeygenResult(
                key_id=signer.key_id,
                public_key=signer.public_key(),
                outputs=[str(path), str(public)],
            )
        )

    return Command(
        id="signing.keygen",
        summary="Create a data signing key (the secret stays outside the repository)",
        params=KeygenParams,
        result=KeygenResult,
        run=run,
    )
