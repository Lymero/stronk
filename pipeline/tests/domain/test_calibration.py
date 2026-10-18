import numpy as np
import pytest

from stronk_pipeline.domain.calibration import calibration, calibration_error, log_loss


def test_perfectly_calibrated_bins_have_no_error() -> None:
    p = np.repeat([0.25, 0.75], 4)
    y = np.array([1, 0, 0, 0, 1, 1, 1, 0], dtype=np.float64)
    assert calibration_error(y, p) == 0
    report = calibration(y, p, np.zeros(8))
    assert [(b.n, b.predicted, b.observed) for b in report.bins] == [
        (4, 0.25, 0.25),
        (4, 0.75, 0.75),
    ]


def test_overconfidence_shows_as_error() -> None:
    y = np.array([1, 0, 1, 0], dtype=np.float64)
    assert calibration_error(y, np.full(4, 0.9)) == pytest.approx(0.4)


def test_log_loss_of_a_coin_flip() -> None:
    assert log_loss(np.array([0.0, 1.0]), np.full(2, 0.5)) == pytest.approx(np.log(2))


def test_certain_mistakes_stay_finite() -> None:
    assert np.isfinite(log_loss(np.array([0.0]), np.array([1.0])))


def test_bands_by_minute() -> None:
    minute = np.array([5.0, 15.0, 35.0])
    report = calibration(np.array([1.0, 0.0, 1.0]), np.full(3, 0.5), minute)
    assert [(b.low, b.n) for b in report.by_minute] == [(0.0, 1), (10.0, 1), (30.0, 1)]
    assert report.n == 3
