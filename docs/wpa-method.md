# WPA method

How we estimate the true power of an item, rune or build path from match data, as close to unbiased as the data allows.

## 1. The question

> If the same player, in the same situation, had chosen option B instead of option A, how much would their chance of winning change?

This is a **causal** question asked of **observational** data: nobody randomizes builds. Raw win rates answer a different question and are badly biased. Items bought by players who are already ahead look strong whatever their real effect.

No method makes observational data fully unbiased. The goal is to remove every bias the data lets us remove, and to say honestly how solid each number is.

## 2. What we estimate

- **Decision point:** the moment a player starts a new item slot (first component bought after the previous item is completed), or champion select for runes and spells. Exact definitions in ADR-026.
- **Options:** the items realistically chosen at that decision point for that champion and role.
- **Estimand:** the average effect on win probability of choosing option A instead of the alternatives, **in situations where both are realistically chosen** (the overlap population).
- **Result per option:** effect, 95% interval, number of decisions, and flags.

Anchoring at the decision point, not at item completion, means:
- every option is compared from the same game state;
- an item's cost and timing are part of its measured value (a cheaper item that spikes earlier gets credit for it);
- games that end before the item is finished are still counted, so late items are not biased toward long games.

## 3. Data

### Available from the Riot API (2 calls per game: match + timeline)

- Final items, runes, spells, champions, roles and result for all 10 players.
- Per-minute snapshots per player: gold, XP, level, CS, position, damage stats.
- Timestamped events: item purchases, sells and undos; skill level-ups; kills; dragons (by type), heralds, barons, towers, inhibitors.

### Derived without extra calls

- **Game state** at any minute: gold, XP, kill, tower and objective differences, dragon soul state, active buffs.
- **Situation:** enemy damage profile (AD/AP), healing, crowd control and tankiness, from champions and items; lane matchup; items already bought.
- **Player skill:** the player's prior win rate and games on the champion, computed from our own crawl using **only games before** the one being analyzed.

### Not available

Voice and chat, intent, full vision, anything between minute snapshots. These are the confounders no method removes; sensitivity analysis (section 6) shows how much they could matter.

### Collection notes

- Rank and mastery lookups cost one extra call per player; avoid them and use crawl-derived skill instead.
- Extract features at download time and discard raw JSON: about a few GB of Parquet per million games instead of about a terabyte.

## 4. How much precision the data allows

Uncertainty shrinks with the square root of the sample size, whatever the method:

| Decisions per option | Uncertainty (± at 95%, approximate) |
|---|---|
| 1,000 | ±3% |
| 10,000 | ±1% |
| 50,000 | ±0.5% |

Real differences between good items are often 0.5–2%. Therefore:

- Popular champions in high elo can separate options about 1% apart.
- Niche champions and rare items often cannot. The output is then **"no clear difference"**, never a winner picked from noise.
- More data beats a fancier method: pool across regions, across patches without relevant changes, and across similar champions (section 5, shrinkage).

## 5. Estimators

Methods are introduced in versions. Each version keeps the previous one available for comparison.

### v1 · Adjusted WPA (M2)

1. **Win probability model.** Predicts P(win) for a team at a given minute from team leads (gold, XP, kills, towers, inhibitors, dragons, barons, heralds, grubs) and the minute. Skill features aren't in frames yet, so the model doesn't use them.
   - Calibration matters more than accuracy: predicted 60% must win about 60% of the time.
   - Train, validation and test split **by match**, never by frame.
   - Candidates (logistic on leads, minute and lead × minute; LightGBM with every lead monotone) are fitted on the training matches; the lowest validation log loss is kept, and the test matches only report. Predictions are made symmetric, so both teams' probabilities of one moment add up to 1 (ADR-030).
2. **Event score** for a decision at minute t:
   `score = outcome − WP(state at t)`
   with outcome the final result, or WP at t + Δ (Δ about 5–8 minutes) for a less noisy, shorter-term measure. Both are computed and compared.
3. **Effect of option A** = mean score for A − mean score for the alternatives at the same decision point, champion and role.
4. **Overlap check.** A propensity model (LightGBM, multiclass) estimates how likely each option is given the situation. Decisions where an option is almost never chosen are excluded; options with too little overlap get the `low_overlap` flag instead of a number.
5. **Shrinkage.** Empirical Bayes shrinkage toward the champion-class average, so small samples don't produce extreme values.
6. **Intervals.** Bootstrap by match.
7. **Multiple comparisons.** Only options eligible to be claimed (a number, neither `low_sample` nor `low_overlap`) are tested, each head to head with its decision point's most played eligible option; the family is fixed by counts before any result. Benjamini-Hochberg across every contrast of the run gives `q`; only q ≤ 0.05 is called clear (ADR-036).

**Known bias of v1 (ADR-036).** Comparing mean scores of choosers and non-choosers estimates E[π(1−π)Δ] / (E[π]·E[1−π]), with π the option's choice probability in the situation and Δ its effect there: when the situation predicts the choice, the effect shrinks toward zero (in synthetic games, an item bought when ahead keeps about half of its effect). The `overlap-weighted` estimator (choosers weighted 1 − π, others π) removes it but lets more hidden confounding through; it runs alongside v1 and isn't the default (ADR-037).

**Reference defaults** (`WpaSettings`): an option's overlap is where its propensity against the rest lies in [0.05, 0.95] (ADR-035); `low_overlap` when under half of an option's decisions are in the overlap; `low_sample` under 300 overlap decisions, and no number at all under 30 for the option or its alternatives; 200 bootstrap resamples by match with the models held fixed; shrinkage only when at least 3 champions of the class have an estimate. `wpa.estimate` takes the model from `winprob.train`; without one (synthetic games have no frames) it fits the logistic form on the decisions themselves (ADR-024).

### v2 · Doubly robust (after v1 is validated)

- Augmented inverse probability weighting with cross-fitting (double machine learning), combining the win probability model and the propensity model.
- Approximately unbiased if either model is right; valid confidence intervals.
- Libraries: DoubleML or EconML. Cost: about 10 tree-model trainings per run.

### v3 · Situational and sequences (only if tests show a gain)

- **Situation buckets:** v2 estimates split by a few situations (ahead or behind, AD-heavy or AP-heavy enemy team), for popular champions only.
- **Build paths:** the top few paths of the first three items, evaluated with g-computation, for popular champions only.

### Not planned

- Deep learning on game sequences.
- Causal forests across all champions.
- Full Bayesian hierarchical models (empirical Bayes gives most of the benefit instantly).
- Tuning the win probability model past the point where item rankings stop changing.

### Compute

All models are gradient-boosted trees on tabular data. A full patch runs in well under a few hours on a normal machine or small server, with no GPU.

## 6. Validation

| Check | What it shows |
|---|---|
| **Synthetic truth** (`tools/synth`) | Planted effects are recovered, including when hidden skill and situational buying are simulated |
| **Oracle agreement** | `reference` and `fast` implementations give the same results |
| **Calibration** | The win probability model's predictions match observed win rates |
| **Patch backtests** | When an item is nerfed or buffed, its estimate moves in the right direction and by a plausible amount, while unchanged items stay stable (difference-in-differences) |
| **Within-player check** | For players who vary their builds, within-player comparisons agree with the main estimate |
| **Sensitivity (E-values)** | How strong a hidden confounder would need to be to overturn a result; fragile results get the `fragile` flag |
| **Damage sanity check** | Large disagreements with damage calculations are investigated (damage measures raw power, not winning, so it is never the truth) |

### Rule for method changes

A new method, feature or model ships **only if it measurably improves** synthetic-truth recovery or patch backtests, without breaking any floor in `metrics/floors.toml`. Added complexity without a measured gain is reverted.

## 7. Flags

| Flag | Meaning |
|---|---|
| `low_sample` | Too few decisions for a useful interval |
| `low_overlap` | The option is rarely chosen in comparable situations; no reliable comparison exists |
| `no_clear_difference` | Not distinguishable from the most played option once false discoveries are controlled: Benjamini-Hochberg across the patch's eligible contrasts, q > 0.05; on the most played option, no alternative differs clearly from it (ADR-036) |
| `fragile` | A modest hidden confounder could overturn the result |

The UI always shows the flag instead of hiding uncertainty.

## 8. Required tests (must stay green)

1. **Synthetic truth:** games where item A truly adds +2% win probability, item B adds nothing but is bought mostly when ahead, and a hidden skill variable affects both builds and wins.
   - A's interval contains +2%;
   - B's estimate is about 0;
   - a 97% pick-rate choice gets `low_overlap`, not a confident number;
   - at a slot with four common options and a long tail of rare ones, the common options keep their numbers, the rare ones get `low_overlap`, and the planted +3% is positive and clear (ADR-035);
   - planted effects survive false discovery control against the most played option; null ones don't (ADR-036).
2. **Oracle agreement:** `reference` and `fast` agree on fixtures within tolerance.
3. **Calibration:** calibration error on fixtures stays within its limit in `metrics/floors.toml`.
4. **Decision anchoring:** a cheaper item with the same per-minute power as a pricier one scores higher in synthetic games, because it completes earlier.
5. **Properties:** each event score lies in [−1, 1]; results don't depend on row order; duplicated matches don't change means.

## 9. Open questions

- Best Δ for the windowed outcome (choose by backtest).
- Defining the option set per decision point (pick-rate threshold vs propensity threshold). Today every option seen is estimated, and overlap is decided per option (ADR-035).
- Components vs completed items; boots tiers. v1 scores completed items only and leaves boots out (ADR-026).
- How long a pooling window across patches can be before item changes make it misleading.
