"""`stronk-synth`: generate synthetic decision tables and compute synthetic-truth metrics."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer

from stronk_pipeline.adapters.parquet_store import ParquetDecisionStore
from stronk_pipeline.domain.result import Err
from stronk_synth.evaluate import evaluate
from stronk_synth.generator import SynthConfig, generate

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)


@app.command("generate")
def generate_cmd(
    out: Annotated[Path, typer.Option(help="Parquet file to write")],
    games: Annotated[int, typer.Option(min=1)] = SynthConfig.games,
    seed: int = SynthConfig.seed,
    hidden_skill_choice: float = SynthConfig.hidden_skill_choice,
) -> None:
    """Write a synthetic decision table and print the planted truth."""
    config = replace(SynthConfig(), games=games, seed=seed, hidden_skill_choice=hidden_skill_choice)
    synth = generate(config)
    if isinstance(result := ParquetDecisionStore().write_decisions(synth.decisions, out), Err):
        typer.echo(result.error.message, err=True)
        raise typer.Exit(code=1)
    truth = {f"slot{slot}:{option}": v for (slot, option), v in sorted(synth.truth.items())}
    typer.echo(json.dumps({"decisions": str(out), "truth": truth}, indent=2))


@app.command("eval")
def eval_cmd(
    out: Annotated[Path | None, typer.Option(help="JSON file for the metrics")] = None,
) -> None:
    """Compute synthetic-truth metrics (checked against metrics/floors.toml)."""
    text = json.dumps(evaluate(), indent=2, sort_keys=True)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n")
    typer.echo(text)


def main() -> None:
    app()
