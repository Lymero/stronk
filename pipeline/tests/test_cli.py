import json
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

from stronk_pipeline.adapters.parquet_store import ParquetDecisionStore
from stronk_pipeline.cli import app
from stronk_synth.generator import SynthConfig, generate

runner = CliRunner()


def test_lists_commands() -> None:
    result = runner.invoke(app, ["commands"])
    assert result.exit_code == 0
    assert {"crawl.run", "extract.run", "wpa.estimate"} <= {
        line.split("\t")[0] for line in result.stdout.splitlines()
    }


def test_runs_a_command(tmp_path: Path) -> None:
    path = tmp_path / "d.parquet"
    ParquetDecisionStore().write_decisions(generate(SynthConfig(games=2000)).decisions, path)
    params = json.dumps({"decisions": str(path), "bootstrap_samples": 20})
    result = runner.invoke(app, ["run", "wpa.estimate", "--params", params])
    assert result.exit_code == 0
    estimates = json.loads(result.stdout)["estimates"]
    assert {e["option"] for e in estimates} == set("ABCDEF")
    assert all(e["wpa"] is None or np.isfinite(e["wpa"]) for e in estimates)


def test_errors_go_to_stderr_with_exit_code_1() -> None:
    result = runner.invoke(app, ["run", "no.such.command"])
    assert result.exit_code == 1
    assert json.loads(result.stderr)["code"] == "unknown_command"
