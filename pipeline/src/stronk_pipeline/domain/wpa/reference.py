"""WPA v1, reference implementation (docs/wpa-method.md, section 5).

Plain and obviously correct rather than fast; the `fast` implementation (M2) must agree with it.

For each decision point (champion, role, slot):

1. event score = outcome - WP(situation at the decision);
2. propensity of each option given the situation: P(A | situation), option A against the rest;
3. overlap population of A = decisions where epsilon <= P(A) <= 1 - epsilon, so both A and an
   alternative are realistically chosen (ADR-035);
4. effect of option A = mean score of A - mean score of the alternatives, inside A's overlap;
5. interval: percentile bootstrap, resampling matches;
6. shrinkage toward the (class, role, slot, option) mean across champions;
7. flags: low_overlap (no number), low_sample (no number under `min_estimate_decisions`),
   no_clear_difference (not distinguishable from zero after false discovery rate control
   across every estimate of the run, ADR-036).
"""

from __future__ import annotations

import zlib
from collections import defaultdict
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray

from stronk_pipeline.domain.decisions import DecisionKey, DecisionTable
from stronk_pipeline.domain.logistic import Floats, fit_logistic
from stronk_pipeline.domain.wpa.fdr import benjamini_hochberg, two_sided_p
from stronk_pipeline.domain.wpa.shrinkage import shrink
from stronk_pipeline.domain.wpa.types import Flag, OptionEstimate, WpaSettings

type Bools = NDArray[np.bool_]


class ReferenceEstimatorV1:
    id = "v1-reference"

    def estimate(
        self, table: DecisionTable, wp: Floats, settings: WpaSettings
    ) -> list[OptionEstimate]:
        return estimate(table, wp, settings)


@dataclass(frozen=True)
class _Raw:
    estimate: OptionEstimate
    std_error: float | None


def estimate(
    table: DecisionTable, wp: Floats, settings: WpaSettings | None = None
) -> list[OptionEstimate]:
    """Estimate every option at every decision point. `wp` is P(win) for each row of `table`."""
    settings = settings or WpaSettings()
    if wp.shape != (len(table),):
        raise ValueError(f"wp has shape {wp.shape}, expected ({len(table)},)")
    if not ((wp >= 0.0) & (wp <= 1.0)).all():
        raise ValueError("wp must lie in [0, 1]")
    score = event_scores(table, wp)
    raw: list[_Raw] = []
    for key, rows in table.decision_points():
        raw.extend(_estimate_point(table, rows, score, key, settings))
    return _flag_unclear(_shrink_across_champions(raw, settings), settings)


def event_scores(table: DecisionTable, wp: Floats) -> Floats:
    """outcome - WP at the decision: in [-1, 1] because both lie in [0, 1]."""
    return table.outcome - wp


def _estimate_point(
    table: DecisionTable,
    rows: NDArray[np.intp],
    score: Floats,
    key: DecisionKey,
    settings: WpaSettings,
) -> list[_Raw]:
    champion, role, slot = key
    champion_class = str(table.champion_class[rows[0]])
    chosen = table.option[rows]
    options = sorted({str(o) for o in chosen})
    scores = score[rows]

    def result(
        option: str,
        n: int,
        flags: set[Flag],
        *,
        wpa: float | None = None,
        ci: tuple[float, float] | None = None,
        std_error: float | None = None,
    ) -> _Raw:
        estimate = OptionEstimate(
            champion, champion_class, role, slot, option, wpa, ci, n, frozenset(flags)
        )
        return _Raw(estimate, std_error)

    if len(options) < 2:
        return [result(options[0], len(rows), {Flag.LOW_OVERLAP})]

    features = table.features[rows]
    weights = _bootstrap_weights(table.match_id[rows], key, settings)
    out: list[_Raw] = []
    for option in options:
        mine: Bools = chosen == option
        propensity = fit_logistic(features, mine.astype(np.float64)).predict(features)
        eps = settings.overlap_epsilon
        overlap: Bools = (propensity >= eps) & (propensity <= 1.0 - eps)
        n_total = int(mine.sum())
        n_in = int((mine & overlap).sum())
        n_alt = int((~mine & overlap).sum())
        if n_in == 0 or n_alt == 0 or n_in / n_total < settings.min_overlap_share:
            out.append(result(option, n_total, {Flag.LOW_OVERLAP}))
            continue
        if min(n_in, n_alt) < settings.min_estimate_decisions:
            out.append(result(option, n_in, {Flag.LOW_SAMPLE}))
            continue
        point = float(scores[mine & overlap].mean() - scores[~mine & overlap].mean())
        boot = _weighted_means(weights[:, mine & overlap], scores[mine & overlap]) - (
            _weighted_means(weights[:, ~mine & overlap], scores[~mine & overlap])
        )
        alpha = 1.0 - settings.confidence
        low, high = np.nanpercentile(boot, [100 * alpha / 2, 100 * (1 - alpha / 2)])
        flags = {Flag.LOW_SAMPLE} if n_in < settings.min_decisions else set[Flag]()
        std_error = float(np.nanstd(boot, ddof=1))
        ci = (float(low), float(high))
        out.append(result(option, n_in, flags, wpa=point, ci=ci, std_error=std_error))
    return out


def _bootstrap_weights(
    match_ids: NDArray[np.str_], key: DecisionKey, settings: WpaSettings
) -> NDArray[np.float64]:
    """(samples, rows) weights: how often each row's match is drawn in each resample."""
    matches, match_of_row = np.unique(match_ids, return_inverse=True)
    if len(matches) == 0:
        return np.zeros((settings.bootstrap_samples, 0))
    # Seeded per decision point, so adding a champion never changes another's interval.
    point_seed = zlib.crc32(repr(key).encode())
    rng = np.random.default_rng(np.random.SeedSequence([settings.seed, point_seed]))
    uniform = np.full(len(matches), 1.0 / len(matches))
    draws = rng.multinomial(len(matches), uniform, size=settings.bootstrap_samples)
    return draws[:, match_of_row].astype(np.float64)


def _weighted_means(weights: NDArray[np.float64], values: Floats) -> Floats:
    totals = weights.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(totals > 0, (weights @ values) / totals, np.nan)


def _shrink_across_champions(raw: list[_Raw], settings: WpaSettings) -> list[_Raw]:
    groups: defaultdict[tuple[str, str, int, str], list[int]] = defaultdict(list)
    for i, r in enumerate(raw):
        e = r.estimate
        if e.wpa is not None and r.std_error is not None:
            groups[(e.champion_class, e.role, e.slot, e.option)].append(i)

    out = list(raw)
    for members in groups.values():
        if len(members) < settings.min_shrinkage_group:
            continue
        estimates = np.array([raw[i].estimate.wpa for i in members], dtype=np.float64)
        std_errors = np.array([raw[i].std_error for i in members], dtype=np.float64)
        shrunk = shrink(estimates, std_errors)
        for j, i in enumerate(members):
            e, std_error = raw[i].estimate, raw[i].std_error
            if e.wpa is None or e.ci is None or not std_error:
                continue
            # Keep the bootstrap interval's shape, rescaled to the shrunk standard error.
            wpa, scale = float(shrunk.estimates[j]), float(shrunk.std_errors[j]) / std_error
            low, high = wpa - (e.wpa - e.ci[0]) * scale, wpa + (e.ci[1] - e.wpa) * scale
            shrunk_error = float(shrunk.std_errors[j])
            out[i] = _Raw(replace(e, wpa=wpa, ci=(low, high)), shrunk_error)
    return out


def _flag_unclear(raw: list[_Raw], settings: WpaSettings) -> list[OptionEstimate]:
    """Benjamini-Hochberg across every estimate with a number: `q` is the adjusted p-value of
    "no effect"; above `settings.fdr`, the estimate gets `no_clear_difference`."""
    tested = [i for i, r in enumerate(raw) if r.estimate.wpa is not None]
    p = np.array([two_sided_p(raw[i].estimate.wpa or 0.0, raw[i].std_error or 0.0) for i in tested])
    out = [r.estimate for r in raw]
    for i, q in zip(tested, benjamini_hochberg(p).tolist(), strict=True):
        flags = out[i].flags | {Flag.NO_CLEAR_DIFFERENCE} if q > settings.fdr else out[i].flags
        out[i] = replace(out[i], q=q, flags=flags)
    return out
