import json
from pathlib import Path

import numpy as np
from winprob_builders import frames

from stronk_pipeline.adapters.json_report import JsonReportWriter
from stronk_pipeline.adapters.lightgbm_winprob import LightGbmLearner
from stronk_pipeline.adapters.parquet_store import ParquetFrameStore
from stronk_pipeline.adapters.winprob_store import JsonWinProbStore
from stronk_pipeline.application.registry import CommandError
from stronk_pipeline.application.winprob_train import (
    WinProbTrainParams,
    WinProbTrainResult,
    winprob_train_command,
)
from stronk_pipeline.domain.frames import FrameTable
from stronk_pipeline.domain.logistic import Floats
from stronk_pipeline.domain.result import Err, Ok, Result
from stronk_pipeline.domain.winprob import LogisticLearner, LogisticWinProb
from stronk_pipeline.ports import WinProbLearner, WinProbModel


class CoinFlip:
    """A learner that ignores the data: always 50%."""

    id = "coin"

    def fit(
        self,
        train: tuple[Floats, Floats, Floats],
        valid: tuple[Floats, Floats, Floats],
        feature_names: tuple[str, ...],
        monotone: tuple[int, ...],
        seed: int,
    ) -> WinProbModel:
        return Fifty()


class Fifty:
    feature_names: tuple[str, ...] = ()

    def predict(self, features: Floats, minute: Floats) -> Floats:
        return np.full(len(features), 0.5)


def train(
    table: FrameTable, tmp_path: Path, learners: tuple[WinProbLearner, ...] | None = None
) -> Result[WinProbTrainResult, CommandError]:
    path = tmp_path / "frames.parquet"
    ParquetFrameStore().write_frames(table, path)
    command = winprob_train_command(
        ParquetFrameStore(),
        learners if learners is not None else (LogisticLearner(), LightGbmLearner()),
        JsonWinProbStore(),
        JsonReportWriter(),
    )
    return command.run(WinProbTrainParams(frames=str(path), out=str(tmp_path / "out")))


def test_keeps_the_best_candidate_on_validation(tmp_path: Path) -> None:
    result = train(frames(200, seed=1), tmp_path, (CoinFlip(), LogisticLearner()))
    assert isinstance(result, Ok)
    value = result.value
    assert value.chosen == "logistic"
    assert value.candidates["logistic"].valid_log_loss < value.candidates["coin"].valid_log_loss
    assert value.test == value.candidates["logistic"].test
    model = JsonWinProbStore().load(tmp_path / "out" / "model.json")
    assert isinstance(model, Ok)
    assert isinstance(model.value, LogisticWinProb)


def test_reports_every_candidate_on_unseen_matches(tmp_path: Path) -> None:
    result = train(frames(200, seed=1), tmp_path)
    assert isinstance(result, Ok)
    assert set(result.value.candidates) == {"logistic", "lightgbm"}
    assert result.value.matches == {"train": 140, "valid": 30, "test": 30}
    assert result.value.test.n == 30 * 25 * 2
    assert result.value.test.calibration_error < 0.1
    report = json.loads((tmp_path / "out" / "report.json").read_text())
    assert report["stage"] == "winprob"
    assert report["result"]["chosen"] == result.value.chosen


def test_too_few_matches_is_invalid_input(tmp_path: Path) -> None:
    result = train(frames(2), tmp_path)
    assert isinstance(result, Err)
    assert result.error.code == "invalid_input"


def test_frames_without_the_model_features_are_invalid_input(tmp_path: Path) -> None:
    table = frames(10)
    narrow = FrameTable(
        match_id=table.match_id,
        team=table.team,
        minute=table.minute,
        outcome=table.outcome,
        features=table.features[:, :1],
        feature_names=table.feature_names[:1],
    )
    result = train(narrow, tmp_path)
    assert isinstance(result, Err)
    assert "missing features" in result.error.message


def test_missing_frames_are_not_found(tmp_path: Path) -> None:
    command = winprob_train_command(
        ParquetFrameStore(), (LogisticLearner(),), JsonWinProbStore(), JsonReportWriter()
    )
    params = WinProbTrainParams(frames=str(tmp_path / "nope.parquet"), out=str(tmp_path))
    result = command.run(params)
    assert isinstance(result, Err)
    assert result.error.code == "not_found"
