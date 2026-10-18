"""WPA v1, reference implementation (docs/wpa-method.md, section 5).

Plain and obviously correct rather than fast; the `fast` implementation (M2) must agree with it.

For each decision point (champion, role, slot):

1. event score = outcome - WP(situation at the decision);
2. propensity of each option given the situation: P(A | situation), option A against the rest;
3. overlap population of A = decisions where epsilon <= P(A) <= 1 - epsilon, so both A and an
   alternative are realistically chosen (ADR-035);
4. effect of option A against the alternatives, inside A's overlap: an `Effect`. v1 takes the
   difference of mean scores; `overlap_weighted` weighs choosers by 1 - P(A), others by P(A);
5. interval: percentile bootstrap, resampling matches;
6. shrinkage toward the (class, role, slot, option) mean across champions;
7. flags: low_overlap (no number), low_sample (no number under `min_estimate_decisions`);
8. claims (ADR-036): options eligible to be claimed (a number, neither low_sample nor
   low_overlap) are compared head to head with the point's most played eligible option, the
   same `Effect` on the rows of the two. Benjamini-Hochberg across every such contrast of the
   run; one with q above `settings.fdr`, and a most played option with no clear contrast, get
   no_clear_difference.
"""

from __future__ import annotations

import zlib
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray

from stronk_pipeline.domain.decisions import DecisionKey, DecisionTable
from stronk_pipeline.domain.logistic import Floats, fit_logistic
from stronk_pipeline.domain.wpa.fdr import benjamini_hochberg, two_sided_p
from stronk_pipeline.domain.wpa.shrinkage import shrink
from stronk_pipeline.domain.wpa.types import Flag, OptionEstimate, WpaSettings

type Bools = NDArray[np.bool_]
type Weights = NDArray[np.float64]
type Effect = Callable[[Floats, Bools, Floats, Weights], tuple[float, Floats]]
"""(scores, chose the option, P(option), bootstrap weights (samples, rows)) -> (effect,
bootstrap effects), all over the rows of one comparison inside its overlap."""


def difference_of_means(
    scores: Floats, mine: Bools, propensity: Floats, weights: Weights
) -> tuple[float, Floats]:
    """v1: mean score of the option - mean score of the others. Targets
    E[e(1-e)D] / (E[e] E[1-e]), so effects of choices the situation predicts shrink (ADR-036)."""
    del propensity
    point = float(scores[mine].mean() - scores[~mine].mean())
    boot = weighted_means(weights[:, mine], scores[mine]) - weighted_means(
        weights[:, ~mine], scores[~mine]
    )
    return point, boot


class ReferenceEstimatorV1:
    id = "v1-reference"

    def estimate(
        self,
        table: DecisionTable,
        wp: Floats,
        settings: WpaSettings,
        outcome: Floats | None = None,
        strata: NDArray[np.str_] | None = None,
    ) -> list[OptionEstimate]:
        return estimate(table, wp, settings, outcome=outcome, strata=strata)


@dataclass(frozen=True)
class _Raw:
    estimate: OptionEstimate
    std_error: float | None
    chosen: int = 0
    """Decisions choosing the option at its point, inside the overlap or not."""
    eligible: bool = False
    """Can be claimed: a number, neither low_sample nor low_overlap. Depends on counts only."""
    contrast_p: float | None = None
    """p-value of no difference with `versus`; None for the most played or an ineligible option."""
    versus: str | None = None


def estimate(
    table: DecisionTable,
    wp: Floats,
    settings: WpaSettings | None = None,
    *,
    effect: Effect = difference_of_means,
    outcome: Floats | None = None,
    strata: NDArray[np.str_] | None = None,
) -> list[OptionEstimate]:
    """Estimate every option at every decision point. `wp` is P(win) for each row of `table`;
    `outcome`, what the score measures against it, defaults to the final result. With
    `strata` (one label per row), scores are centred within each stratum at each point, so
    options are compared within strata (fixed effects; `pooling.pool_by_class`)."""
    settings = settings or WpaSettings()
    if wp.shape != (len(table),):
        raise ValueError(f"wp has shape {wp.shape}, expected ({len(table)},)")
    if not ((wp >= 0.0) & (wp <= 1.0)).all():
        raise ValueError("wp must lie in [0, 1]")
    if strata is not None and strata.shape != (len(table),):
        raise ValueError(f"strata has shape {strata.shape}, expected ({len(table)},)")
    score = event_scores(table, wp, outcome)
    raw: list[_Raw] = []
    for key, rows in table.decision_points():
        if strata is not None:
            score[rows] = _centred(score[rows], strata[rows])
        raw.extend(_estimate_point(table, rows, score, key, settings, effect=effect))
    return _flag_unclear(_shrink_across_champions(raw, settings), settings)


def _centred(scores: Floats, strata: NDArray[np.str_]) -> Floats:
    labels, group = np.unique(strata, return_inverse=True)
    means = np.bincount(group, weights=scores, minlength=len(labels)) / np.bincount(group)
    return scores - means[group]


def event_scores(table: DecisionTable, wp: Floats, outcome: Floats | None = None) -> Floats:
    """outcome - WP at the decision: in [-1, 1] because both lie in [0, 1]. The outcome is the
    final result unless given (a windowed WP, `outcome.windowed_outcome`)."""
    if outcome is None:
        return table.outcome - wp
    if outcome.shape != (len(table),) or not ((outcome >= 0.0) & (outcome <= 1.0)).all():
        raise ValueError("outcome must lie in [0, 1], one per row")
    return outcome - wp


def _estimate_point(
    table: DecisionTable,
    rows: NDArray[np.intp],
    score: Floats,
    key: DecisionKey,
    settings: WpaSettings,
    *,
    effect: Effect,
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
        count = int((chosen == option).sum())
        eligible = wpa is not None and not flags & {Flag.LOW_SAMPLE, Flag.LOW_OVERLAP}
        return _Raw(estimate, std_error, count, eligible)

    if len(options) < 2:
        return [result(options[0], len(rows), {Flag.LOW_OVERLAP})]

    features = table.features[rows]
    # Columns constant at this point (another champion's indicator) carry nothing: dropping them
    # leaves every fit unchanged and keeps pooled points fast.
    features = features[:, features.std(axis=0) > 0.0]
    weights = _bootstrap_weights(table.match_id[rows], key, settings)
    alpha = 1.0 - settings.confidence

    def compare(
        subset: Bools, mine: Bools, propensity: Floats | None = None
    ) -> tuple[float, Floats, Bools] | None:
        """`effect` of `mine` against the rest of `subset`, inside its overlap; None when
        either side has fewer than `min_estimate_decisions` there. `propensity`, if given, is
        P(mine) already fitted on `subset`."""
        if propensity is None:
            model = fit_logistic(features[subset], mine[subset].astype(np.float64))
            propensity = model.predict(features[subset])
        eps = settings.overlap_epsilon
        inside = np.zeros(len(rows), dtype=np.bool_)
        inside[subset] = (propensity >= eps) & (propensity <= 1.0 - eps)
        if min(int((mine & inside).sum()), int((~mine & inside).sum())) < (
            settings.min_estimate_decisions
        ):
            return None
        point, boot = effect(
            scores[inside], mine[inside], propensity[inside[subset]], weights[:, inside]
        )
        return point, boot, inside

    out: list[_Raw] = []
    everyone = np.ones(len(rows), dtype=np.bool_)
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
        compared = compare(everyone, mine, propensity)
        if compared is None:
            out.append(result(option, n_in, {Flag.LOW_SAMPLE}))
            continue
        point, boot, _ = compared
        low, high = np.nanpercentile(boot, [100 * alpha / 2, 100 * (1 - alpha / 2)])
        flags = {Flag.LOW_SAMPLE} if n_in < settings.min_decisions else set[Flag]()
        std_error = float(np.nanstd(boot, ddof=1))
        ci = (float(low), float(high))
        out.append(result(option, n_in, flags, wpa=point, ci=ci, std_error=std_error))
    return _contrast_with_most_played(out, chosen, compare)


def _contrast_with_most_played(
    out: list[_Raw],
    chosen: NDArray[np.str_],
    compare: Callable[[Bools, Bools], tuple[float, Floats, Bools] | None],
) -> list[_Raw]:
    """Head-to-head p-values of eligible options against the most played eligible one.

    Which options are compared depends on counts only, never on results, so the family of
    hypotheses is fixed before any is tested. A contrast that can't be measured (too few
    decisions in the pair's overlap) stays in the family with p = 1."""
    eligible = [r for r in out if r.eligible]
    if not eligible:
        return out
    most_played = min(eligible, key=lambda r: (-r.chosen, r.estimate.option)).estimate.option
    contrasted: list[_Raw] = []
    for r in out:
        option = r.estimate.option
        if not r.eligible or option == most_played:
            contrasted.append(r)
            continue
        pair = (chosen == option) | (chosen == most_played)
        compared = compare(pair, chosen == option)
        p = 1.0
        if compared is not None:
            point, boot, _ = compared
            p = two_sided_p(point, float(np.nanstd(boot, ddof=1)))
        contrasted.append(replace(r, contrast_p=p, versus=most_played))
    return contrasted


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


def weighted_means(weights: NDArray[np.float64], values: Floats) -> Floats:
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
            out[i] = replace(raw[i], estimate=replace(e, wpa=wpa, ci=(low, high)),
                             std_error=shrunk_error)  # fmt: skip
    return out


def _flag_unclear(raw: list[_Raw], settings: WpaSettings) -> list[OptionEstimate]:
    """Benjamini-Hochberg across every contrast of the run (ADR-036). A contrast with q above
    `settings.fdr` is no clear difference; so is a most played option none of whose
    alternatives differs clearly from it."""
    tested = [i for i, r in enumerate(raw) if r.contrast_p is not None]
    q = benjamini_hochberg(np.array([raw[i].contrast_p for i in tested], dtype=np.float64))
    q_of = dict(zip(tested, q.tolist(), strict=True))
    clear_points = {_point(raw[i].estimate) for i, value in q_of.items() if value <= settings.fdr}
    out: list[OptionEstimate] = []
    for i, r in enumerate(raw):
        e = r.estimate
        if not r.eligible:
            out.append(e)
        elif i in q_of:
            unclear = q_of[i] > settings.fdr
            flags = e.flags | {Flag.NO_CLEAR_DIFFERENCE} if unclear else e.flags
            out.append(replace(e, q=q_of[i], versus=r.versus, flags=flags))
        elif _point(e) in clear_points:
            out.append(e)  # the most played, and something differs clearly from it
        else:
            out.append(replace(e, flags=e.flags | {Flag.NO_CLEAR_DIFFERENCE}))
    return out


def _point(e: OptionEstimate) -> DecisionKey:
    return (e.champion, e.role, e.slot)
