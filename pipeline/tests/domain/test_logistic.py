import numpy as np

from stronk_pipeline.domain.logistic import expit, fit_logistic


def test_recovers_known_coefficients() -> None:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(50_000, 2))
    y = (rng.random(50_000) < expit(0.5 + 1.0 * x[:, 0] - 2.0 * x[:, 1])).astype(np.float64)
    model = fit_logistic(x, y)
    p = model.predict(np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]))
    np.testing.assert_allclose(p, expit(np.array([0.5, 1.5, -1.5])), atol=0.02)


def test_separable_data_stays_finite() -> None:
    x = np.array([[-2.0], [-1.0], [1.0], [2.0]])
    y = np.array([0.0, 0.0, 1.0, 1.0])
    model = fit_logistic(x, y)
    assert np.isfinite(model.coef).all()
    assert model.predict(np.array([[3.0]]))[0] > 0.9


def test_constant_feature_is_harmless() -> None:
    model = fit_logistic(np.ones((10, 1)), np.array([1.0, 0.0] * 5))
    np.testing.assert_allclose(model.predict(np.ones((1, 1))), [0.5], atol=1e-6)
