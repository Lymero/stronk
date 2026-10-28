import json
from pathlib import Path

from stronk_pipeline.adapters.json_estimates import JsonEstimateStore
from stronk_pipeline.adapters.json_report import JsonReportWriter
from stronk_pipeline.application.backtest import BacktestParams, backtest_command
from stronk_pipeline.domain.result import Err, Ok
from stronk_pipeline.domain.wpa.types import OptionEstimate

COMMAND = backtest_command(JsonEstimateStore(), JsonReportWriter())


def write(path: Path, effects: dict[str, tuple[float, float]]) -> str:
    rows = [OptionEstimate("Champ1", "fighter", "TOP", 0, "A", 0.0, (-0.01, 0.01), 900)] + [
        OptionEstimate(
            "Champ1",
            "fighter",
            "TOP",
            0,
            option,
            effect,
            (effect - 0.05, effect + 0.05),
            400,
            q=q,
            versus="A",
            contrast=effect,
            contrast_ci=(effect - 0.05, effect + 0.05),
        )
        for option, (effect, q) in effects.items()
    ]
    JsonEstimateStore().write_estimates("v1-reference", rows, path)
    return str(path)


def test_compares_two_estimate_files_and_writes_the_report(tmp_path: Path) -> None:
    earlier = write(tmp_path / "a.json", {"B": (0.1, 0.01), "C": (-0.02, 0.8)})
    later = write(tmp_path / "b.json", {"B": (0.08, 0.03), "C": (0.01, 0.9)})
    params = BacktestParams(earlier=earlier, later=later, out=str(tmp_path / "bt"))
    result = COMMAND.run(params)
    assert isinstance(result, Ok)
    assert (result.value.paired, result.value.sign_agreement) == (2, 0.5)
    assert (result.value.claims_held, result.value.claims_replicated) == (1, 1)
    report = json.loads((tmp_path / "bt" / "report.json").read_text())
    assert report["stage"] == "backtest"
    assert report["result"]["sign_agreement"] == 0.5


def test_missing_estimates_are_not_found(tmp_path: Path) -> None:
    earlier = write(tmp_path / "a.json", {"B": (0.1, 0.01)})
    result = COMMAND.run(BacktestParams(earlier=earlier, later=str(tmp_path / "none.json")))
    assert isinstance(result, Err)
    assert result.error.code == "not_found"


def test_a_file_that_is_not_estimates_is_invalid(tmp_path: Path) -> None:
    (tmp_path / "x.json").write_text('{"nope": 1}')
    earlier = write(tmp_path / "a.json", {"B": (0.1, 0.01)})
    result = COMMAND.run(BacktestParams(earlier=str(tmp_path / "x.json"), later=earlier))
    assert isinstance(result, Err)
    assert result.error.code == "invalid_input"
