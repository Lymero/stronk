import numpy as np

from stronk_pipeline.domain.logistic import expit, fit_logistic, fit_logistic_chunks


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


def test_a_fit_read_a_chunk_at_a_time_is_the_same_fit() -> None:
    """ADR-081: on one chunk, `fit_logistic`'s arithmetic exactly; on several, the same sums
    added in another order."""
    rng = np.random.default_rng(3)
    x = rng.normal(size=(5000, 3)) * [1.0, 10.0, 0.1] + [0.0, 5.0, -2.0]
    y = (rng.random(5000) < expit(x @ [0.8, -0.05, 2.0])).astype(np.float64)
    whole = fit_logistic(x, y)
    one = fit_logistic_chunks(lambda: [(x, y)])
    for field in ("mean", "scale", "coef"):
        assert np.array_equal(getattr(one, field), getattr(whole, field))
    cuts = [0, 1, 777, 2048, 4999, 5000]
    chunks = list(zip(np.split(x, cuts[1:-1]), np.split(y, cuts[1:-1]), strict=True))
    several = fit_logistic_chunks(lambda: chunks)
    for field in ("mean", "scale", "coef"):
        np.testing.assert_allclose(
            getattr(several, field), getattr(whole, field), rtol=1e-12, atol=1e-12
        )
    np.testing.assert_allclose(several.predict(x), whole.predict(x), rtol=0, atol=1e-13)
