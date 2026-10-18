import numpy as np

from stronk_pipeline.domain.wpa.shrinkage import shrink


def test_identical_estimates_are_unchanged() -> None:
    result = shrink(np.array([0.01, 0.01, 0.01]), np.array([0.005, 0.005, 0.005]))
    np.testing.assert_allclose(result.estimates, [0.01, 0.01, 0.01])


def test_noisy_estimates_are_pulled_harder() -> None:
    estimates = np.array([0.0, 0.01, 0.02, 0.05])
    std_errors = np.array([0.002, 0.002, 0.002, 0.04])
    result = shrink(estimates, std_errors)
    pull = np.abs(result.estimates - estimates)
    assert pull[3] > pull[:3].max()
    assert result.weights[3] < result.weights[:3].min()


def test_spread_within_noise_shrinks_to_the_mean() -> None:
    result = shrink(np.array([-0.001, 0.0, 0.001]), np.array([0.01, 0.01, 0.01]))
    np.testing.assert_allclose(result.estimates, [0.0, 0.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(result.weights, [0.0, 0.0, 0.0])


def test_full_shrinkage_keeps_the_prior_uncertainty() -> None:
    std_errors = np.array([0.01, 0.01, 0.01])
    result = shrink(np.array([-0.001, 0.0, 0.001]), std_errors)
    # tau^2 = 0: every estimate is the prior, known to within its own standard error
    np.testing.assert_allclose(result.std_errors, [0.01 / np.sqrt(3)] * 3)


def test_no_shrinkage_keeps_the_standard_errors() -> None:
    std_errors = np.array([0.001, 0.001, 0.001])
    result = shrink(np.array([-0.5, 0.0, 0.5]), std_errors)
    np.testing.assert_allclose(result.weights, [1.0, 1.0, 1.0], atol=1e-4)
    np.testing.assert_allclose(result.std_errors, std_errors, rtol=1e-3)
