"""`stronk-pipeline`: dispatches registered commands. Also the composition root."""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from stronk_pipeline.adapters.parquet_store import ParquetDecisionStore
from stronk_pipeline.application.registry import CommandRegistry
from stronk_pipeline.application.wpa_estimate import wpa_estimate_command
from stronk_pipeline.domain.result import Err, Ok
from stronk_pipeline.domain.wpa.reference import ReferenceEstimatorV1

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)


def build_registry() -> CommandRegistry:
    store = ParquetDecisionStore()
    estimators = {e.id: e for e in (ReferenceEstimatorV1(),)}
    return CommandRegistry([wpa_estimate_command(store, estimators)])


@app.command("commands")
def list_commands() -> None:
    """List registered commands."""
    for command in build_registry().commands():
        typer.echo(f"{command.id}\t{command.summary}")


@app.command()
def run(
    command_id: Annotated[str, typer.Argument(help="Command id, for example wpa.estimate")],
    params: Annotated[str, typer.Option(help="Parameters as a JSON object")] = "{}",
) -> None:
    """Run a command and print its JSON result. Errors go to stderr as JSON, exit code 1."""
    match build_registry().dispatch(command_id, params):
        case Ok(value=result):
            typer.echo(result.model_dump_json(indent=2))
        case Err(error=error):
            sys.stderr.write(error.model_dump_json() + "\n")
            raise typer.Exit(code=1)


def main() -> None:
    app()
