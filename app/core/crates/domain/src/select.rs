//! What to import (ADR-043, ADR-065): the most played option, unless another is the best bet
//! against it: the highest estimate once shrunk toward 0 by its uncertainty, among the options
//! compared with it head to head. A best bet that survives false discovery control is "clearly
//! better". Pure: the service turns published build files into [`Candidate`]s.

use serde::Serialize;

/// Why an option was chosen; shown next to it in the UI.
#[derive(Clone, Copy, Debug, PartialEq, Serialize, schemars::JsonSchema)]
#[serde(tag = "label", rename_all = "snake_case")]
pub enum Label {
    /// The most played option (whole page, whole pair, or most picked item).
    Popular,
    /// Beats the popular option head to head and survives false discovery control.
    ClearlyBetter {
        /// Win probability added against the popular option.
        wpa: f64,
        /// Its 95% interval, when published.
        ci: Option<(f64, f64)>,
        /// Games (or picks) with this option.
        games: u64,
    },
    /// The best bet against the popular option (ADR-065): the highest shrunk estimate, not yet
    /// clear once false discoveries are controlled.
    BestBet {
        /// Win probability added against the popular option, as published (not shrunk).
        wpa: f64,
        ci: Option<(f64, f64)>,
        games: u64,
    },
    /// The player picked this published option instead of Stronk's choice.
    Picked,
}

/// The spread of true win impacts the shrinkage assumes (ADR-065): a difference of two wins per
/// 100 games between options of one decision is already large. An estimate keeps the share
/// `TAU² / (TAU² + se²)` of itself, so a precise one keeps most and a noisy one little.
pub const TAU: f64 = 0.02;

/// The smallest shrunk gain worth leaving the most played option for: half a win per 100 games.
pub const BEST_BET_MIN: f64 = 0.005;

/// `wpa` shrunk toward 0 by the uncertainty its 95% interval gives; without an interval, no
/// shrunk estimate.
pub fn shrunk(wpa: f64, ci: Option<(f64, f64)>) -> Option<f64> {
    let (low, high) = ci?;
    let se = (high - low).abs() / (2.0 * 1.96);
    Some(wpa * TAU * TAU / (TAU * TAU + se * se))
}

/// The head-to-head comparison of an option with the most played one.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Comparison {
    /// The most played option's id.
    pub versus: i64,
    /// Win probability added against it.
    pub wpa: f64,
    pub ci: Option<(f64, f64)>,
}

/// One published option, reduced to what the choice needs.
#[derive(Clone, Debug, PartialEq)]
pub struct Candidate<T> {
    pub value: T,
    /// The option's id in comparisons: keystone for rune pages, item id for items.
    pub id: i64,
    /// Games (or picks) with exactly this option: popularity.
    pub played: u64,
    /// Its own win impact against the alternatives at this decision; `None` when not estimated.
    pub wpa: Option<f64>,
    pub ci: Option<(f64, f64)>,
    /// Flagged `low_sample` or `low_overlap`: too few comparable games.
    pub too_few: bool,
    /// Flagged `low_overlap`: chosen in nearly every comparable game, or in nearly none.
    pub low_overlap: bool,
    /// Flagged `no_clear_difference`.
    pub unclear: bool,
    /// Flagged `fragile`: a modest hidden confounder could overturn it.
    pub fragile: bool,
    pub comparison: Option<Comparison>,
    /// The patch that last changed the item, or one of the purchase's items, among the
    /// patches the build counts (ADR-088).
    pub changed_in: Option<String>,
}

impl<T> Candidate<T> {
    /// Has a number and is neither `low_sample` nor `low_overlap`.
    pub fn claimable(&self) -> bool {
        self.wpa.is_some() && !self.too_few
    }

    /// Its comparison with `popular` when the published flags make the difference clear:
    /// claimable and not `no_clear_difference`. The one rule behind [`choose`] and [`rank`].
    fn clear_against(&self, popular: i64) -> Option<Comparison> {
        self.comparison
            .filter(|k| k.versus == popular && self.claimable() && !self.unclear)
    }

    /// Stronk's judgement of it against `popular`, for ordering (ADR-070): its head-to-head
    /// gain shrunk toward 0 by its uncertainty when compared and claimable (a clear one without
    /// an interval at its estimate), else 0: the popular one, and any option not measured
    /// against it, is no better or worse as far as Stronk knows.
    fn judged_against(&self, popular: i64) -> f64 {
        self.comparison
            .filter(|k| k.versus == popular && self.claimable())
            .and_then(|k| shrunk(k.wpa, k.ci).or(Some(k.wpa)))
            .unwrap_or(0.0)
    }

    /// Its comparison with `popular` and how much it stands to gain, when it may be the best
    /// bet: compared head to head and claimable, and either clear or with a shrunk gain of at
    /// least [`BEST_BET_MIN`]. A clear one without an interval counts at its estimate.
    fn bet_against(&self, popular: i64) -> Option<(Comparison, f64, bool)> {
        let k = self
            .comparison
            .filter(|k| k.versus == popular && self.claimable())?;
        let clear = !self.unclear && k.wpa > 0.0;
        let gain = shrunk(k.wpa, k.ci).or(clear.then_some(k.wpa))?;
        (clear || gain >= BEST_BET_MIN).then_some((k, gain, clear))
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, schemars::JsonSchema)]
#[schemars(rename = "{T}Choice")]
pub struct Choice<T> {
    pub value: T,
    #[serde(flatten)]
    pub label: Label,
}

/// Popularity order: most played first, ties to the smallest id.
fn by_popularity<T>(a: &Candidate<T>, b: &Candidate<T>) -> std::cmp::Ordering {
    b.played.cmp(&a.played).then(a.id.cmp(&b.id))
}

/// The popular candidate (most played; ties to the smallest id), or the best bet against it:
/// the largest shrunk gain among those that may be ([`Candidate::bet_against`]), labelled
/// clearly better when it survives false discovery control. `None` without candidates.
pub fn choose<T: Clone>(candidates: &[Candidate<T>]) -> Option<Choice<T>> {
    let popular = candidates.iter().min_by(|a, b| by_popularity(a, b))?;
    let bet = candidates
        .iter()
        .filter(|c| c.id != popular.id)
        .filter_map(|c| c.bet_against(popular.id).map(|b| (c, b)))
        .max_by(|(a, (_, x, _)), (b, (_, y, _))| x.total_cmp(y).then(b.id.cmp(&a.id)));
    Some(match bet {
        Some((c, (k, _, true))) => Choice {
            value: c.value.clone(),
            label: Label::ClearlyBetter {
                wpa: k.wpa,
                ci: k.ci,
                games: c.played,
            },
        },
        Some((c, (k, _, false))) => Choice {
            value: c.value.clone(),
            label: Label::BestBet {
                wpa: k.wpa,
                ci: k.ci,
                games: c.played,
            },
        },
        None => Choice {
            value: popular.value.clone(),
            label: Label::Popular,
        },
    })
}

/// How far an option's numbers can be trusted (docs/wpa-method.md, section 7).
/// Games above which an option without a number isn't short of games, only of comparable ones:
/// the pipeline's `low_sample` line (`WpaSettings`). It decides [`Confidence::AlmostAlways`] and
/// [`Confidence::TooFewToCompare`] against [`Confidence::TooFewGames`].
pub const ENOUGH_GAMES: u64 = 300;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Confidence {
    /// Beats the most played option head to head, by the rule [`choose`] uses.
    ClearlyBetter,
    /// Loses to the most played option head to head, by the same rule.
    ClearlyWorse,
    /// The most played option: what the others are compared with.
    MostPlayed,
    /// Stronk's choice by the best bet rule (ADR-065): ahead of the most played option on the
    /// numbers, not yet clear.
    BestBet,
    /// Has a number, but isn't distinguishable from the most played option.
    NoClearDifference,
    /// `low_sample` or `low_overlap`: too few comparable games for a number to mean much.
    TooFewGames,
    /// The same flags on an option with at least [`ENOUGH_GAMES`]: plenty of games, too few of
    /// them in situations comparable with the alternatives'.
    TooFewToCompare,
    /// The most played option, flagged `low_overlap` with at least [`ENOUGH_GAMES`]: chosen
    /// in nearly every comparable game, so there is nothing to compare it with (not a lack of
    /// games). On a thin board the same flag means too little data: [`Confidence::TooFewGames`].
    AlmostAlways,
    /// No estimate is published for it (spells have none yet).
    NotEstimated,
}

/// What a row's win impact is measured against.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Versus {
    /// Head to head with the slot's most played option.
    MostPlayed,
    /// The alternatives at this decision point: the option's own estimate.
    Alternatives,
}

/// One option of a slot, as the champion select view shows it (ADR-049).
#[derive(Clone, Debug, PartialEq, Serialize, schemars::JsonSchema)]
#[schemars(rename = "{T}Row")]
pub struct Row<T> {
    pub value: T,
    /// Games (or picks) with this option.
    pub played: u64,
    /// Its share of the slot's games, 0 to 1.
    pub share: f64,
    /// Win probability added, against what `versus` says.
    pub wpa: Option<f64>,
    pub ci: Option<(f64, f64)>,
    pub versus: Versus,
    pub confidence: Confidence,
    pub fragile: bool,
    /// Stronk's choice for the slot.
    pub chosen: bool,
    /// Listed before the player asks for every option: one of the [`SHOWN`] most played, or
    /// Stronk's choice.
    pub listed: bool,
    /// Stronk's judgement against the most played option, for ordering (ADR-070): the gain the
    /// best bet is chosen by, 0 when not measured against it. See [`by_judgement`].
    pub judged: f64,
    /// The patch that last changed the item, or one of the purchase's items (ADR-088): in a
    /// pooled build, measured on that patch's games and later ones only.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub changed_in: Option<String>,
}

/// Stronk's order of a slot's options (ADR-070): its choice, then the larger judged gain
/// first, ties to the more played (rows come most played first; the sort is stable).
pub fn by_judgement<T>(rows: &mut [&Row<T>]) {
    rows.sort_by(|a, b| b.chosen.cmp(&a.chosen).then(b.judged.total_cmp(&a.judged)));
}

/// Every option of a slot, and how many of them are left out of the short list.
#[derive(Clone, Debug, PartialEq, Serialize, schemars::JsonSchema)]
#[schemars(rename = "{T}Ranked")]
pub struct Ranked<T> {
    pub rows: Vec<Row<T>>,
    /// Options played less, not listed until the player asks for every option.
    pub more: usize,
}

/// Options listed per slot: the most played, plus the chosen one when it is rarer.
pub const SHOWN: usize = 3;

/// Every option of a slot in popularity order with its share, win impact and confidence, the
/// [`SHOWN`] most played and `chosen` marked `listed`. "Clearly better/worse" comes from the
/// published flags by the rule [`choose`] uses, with no threshold of its own.
pub fn rank<T: Clone + PartialEq>(candidates: &[Candidate<T>], chosen: Option<&T>) -> Ranked<T> {
    let mut sorted: Vec<&Candidate<T>> = candidates.iter().collect();
    sorted.sort_by(|a, b| by_popularity(a, b));
    let popular = sorted.first().map_or(0, |c| c.id);
    let total: u64 = sorted.iter().map(|c| c.played).sum();
    let is_chosen = |c: &Candidate<T>| chosen.is_some_and(|v| *v == c.value);
    let rows: Vec<Row<T>> = sorted
        .iter()
        .enumerate()
        .map(|(i, c)| {
            let most_played = i == 0;
            let compared = c.comparison.filter(|k| k.versus == popular && !most_played);
            let clear = c.clear_against(popular).filter(|_| !most_played);
            let confidence = match clear {
                _ if most_played && c.low_overlap && c.played >= ENOUGH_GAMES => {
                    Confidence::AlmostAlways
                }
                _ if c.too_few && c.played >= ENOUGH_GAMES => Confidence::TooFewToCompare,
                _ if c.too_few => Confidence::TooFewGames,
                Some(k) if k.wpa > 0.0 => Confidence::ClearlyBetter,
                Some(k) if k.wpa < 0.0 => Confidence::ClearlyWorse,
                _ if most_played => Confidence::MostPlayed,
                _ if is_chosen(c) && c.bet_against(popular).is_some() => Confidence::BestBet,
                _ if c.wpa.is_none() => Confidence::NotEstimated,
                _ => Confidence::NoClearDifference,
            };
            Row {
                value: c.value.clone(),
                played: c.played,
                share: share(c.played, total),
                wpa: compared.map_or(c.wpa, |k| Some(k.wpa)),
                ci: compared.map_or(c.ci, |k| k.ci),
                versus: if compared.is_some() {
                    Versus::MostPlayed
                } else {
                    Versus::Alternatives
                },
                confidence,
                fragile: c.fragile,
                chosen: is_chosen(c),
                listed: i < SHOWN || is_chosen(c),
                judged: c.judged_against(popular),
                changed_in: c.changed_in.clone(),
            }
        })
        .collect();
    Ranked {
        more: rows.iter().filter(|r| !r.listed).count(),
        rows,
    }
}

#[allow(clippy::cast_precision_loss)] // game counts stay far below 2^52
fn share(played: u64, total: u64) -> f64 {
    if total == 0 {
        0.0
    } else {
        played as f64 / total as f64
    }
}

/// One choice per item slot, in slot order, never repeating an item: an item chosen for an
/// earlier slot is left out of the later slots' candidates (a full build has six different
/// items). Slots left without candidates get no choice.
pub fn choose_items(slots: &[(u64, Vec<Candidate<i64>>)]) -> Vec<(u64, Choice<i64>)> {
    let mut slots: Vec<&(u64, Vec<Candidate<i64>>)> = slots.iter().collect();
    slots.sort_by_key(|(slot, _)| *slot);
    let mut taken: Vec<i64> = Vec::new();
    let mut chosen = Vec::new();
    for (slot, candidates) in slots {
        let left: Vec<Candidate<i64>> = candidates
            .iter()
            .filter(|c| !taken.contains(&c.value))
            .cloned()
            .collect();
        if let Some(choice) = choose(&left) {
            taken.push(choice.value);
            chosen.push((*slot, choice));
        }
    }
    chosen
}

#[cfg(test)]
mod tests {
    use super::*;

    fn candidate(id: i64, played: u64, comparison: Option<(i64, f64)>) -> Candidate<i64> {
        let comparison = comparison.map(|(versus, wpa)| Comparison {
            versus,
            wpa,
            ci: Some((0.01, 0.05)),
        });
        Candidate {
            value: id,
            id,
            played,
            wpa: Some(0.01),
            ci: Some((-0.01, 0.03)),
            too_few: false,
            low_overlap: false,
            unclear: false,
            fragile: false,
            comparison,
            changed_in: None,
        }
    }

    #[test]
    fn the_most_played_stays_without_a_best_bet() {
        let c = [
            candidate(1, 10, None),
            candidate(2, 30, None),
            candidate(3, 20, Some((2, 0.03))),
        ];
        // Unclear and too uncertain to matter: +3.0 likely between −7 and +13 shrinks to +0.1.
        let mut noisy = c.clone();
        noisy[2].unclear = true;
        noisy[2].comparison = Some(Comparison {
            versus: 2,
            wpa: 0.03,
            ci: Some((-0.07, 0.13)),
        });
        let popular = Some(Choice {
            value: 2,
            label: Label::Popular,
        });
        assert_eq!(choose(&noisy), popular);
        // Behind the most played one, or too few games to claim anything: never a bet.
        let mut behind = noisy.clone();
        behind[2].comparison = Some(Comparison {
            versus: 2,
            wpa: -0.03,
            ci: Some((-0.04, -0.02)),
        });
        assert_eq!(choose(&behind), popular);
        let mut few = c.clone();
        (few[2].unclear, few[2].too_few) = (true, true);
        assert_eq!(choose(&few), popular);
        // Compared with another option than the most played: not on its scale.
        let mut elsewhere = c.clone();
        elsewhere[2].comparison = Some(Comparison {
            versus: 1,
            wpa: 0.03,
            ci: Some((0.02, 0.04)),
        });
        assert_eq!(choose(&elsewhere), popular);
    }

    #[test]
    fn the_best_bet_replaces_the_most_played_before_it_is_clear() {
        // Cut Down against Coup de Grace on Lee Sin: +2.7, likely between 0.0 and +5.6, q 0.61.
        let mut cut_down = candidate(8017, 1704, None);
        cut_down.unclear = true;
        cut_down.comparison = Some(Comparison {
            versus: 8014,
            wpa: 0.027,
            ci: Some((-0.000_05, 0.055_55)),
        });
        let c = [
            candidate(8014, 2194, None),
            cut_down,
            candidate(8299, 181, None),
        ];
        assert_eq!(
            choose(&c),
            Some(Choice {
                value: 8017,
                label: Label::BestBet {
                    wpa: 0.027,
                    ci: Some((-0.000_05, 0.055_55)),
                    games: 1704
                },
            })
        );
        // A rarer option with a bigger but much noisier estimate loses to it once shrunk.
        let mut lucky = candidate(8299, 181, None);
        lucky.unclear = true;
        lucky.comparison = Some(Comparison {
            versus: 8014,
            wpa: 0.08,
            ci: Some((-0.1, 0.26)),
        });
        let c = [candidate(8014, 2194, None), c[1].clone(), lucky];
        assert_eq!(choose(&c).map(|x| x.value), Some(8017));
    }

    #[test]
    fn shrinking_keeps_most_of_a_precise_estimate_and_little_of_a_noisy_one() {
        let precise = shrunk(0.027, Some((-0.000_05, 0.055_55))).unwrap();
        assert!((precise - 0.018).abs() < 0.001, "{precise}");
        let noisy = shrunk(0.08, Some((-0.1, 0.26))).unwrap();
        assert!(noisy < BEST_BET_MIN, "{noisy}");
        assert_eq!(shrunk(0.03, None), None);
    }

    #[test]
    fn a_clearly_better_option_replaces_the_popular_one() {
        let c = [
            candidate(1, 10, Some((2, 0.01))),
            candidate(2, 30, None),
            candidate(3, 20, Some((2, 0.03))),
        ];
        assert_eq!(
            choose(&c),
            Some(Choice {
                value: 3,
                label: Label::ClearlyBetter {
                    wpa: 0.03,
                    ci: Some((0.01, 0.05)),
                    games: 20
                }
            })
        );
    }

    #[test]
    fn better_means_against_the_popular_option_positive_and_claimable() {
        let worse = [candidate(2, 30, None), candidate(3, 20, Some((2, -0.03)))];
        let elsewhere = [candidate(2, 30, None), candidate(3, 20, Some((9, 0.03)))];
        let mut low_sample = [candidate(2, 30, None), candidate(3, 20, Some((2, 0.03)))];
        low_sample[1].too_few = true;
        for c in [&worse[..], &elsewhere[..], &low_sample[..]] {
            assert_eq!(choose(c).map(|c| c.label), Some(Label::Popular));
        }
        assert_eq!(choose::<i64>(&[]), None);
    }

    #[test]
    fn ties_go_to_the_smallest_id() {
        assert_eq!(
            choose(&[candidate(5, 10, None), candidate(4, 10, None)]).map(|c| c.value),
            Some(4)
        );
    }

    #[test]
    fn an_item_fills_one_slot_only() {
        let guardian = 3026;
        let slots = vec![
            (
                5,
                vec![candidate(guardian, 55, None), candidate(7, 43, None)],
            ),
            (
                4,
                vec![candidate(guardian, 331, None), candidate(7, 185, None)],
            ),
            (6, vec![candidate(guardian, 5, None), candidate(7, 3, None)]),
        ];
        let chosen: Vec<(u64, i64)> = choose_items(&slots)
            .into_iter()
            .map(|(slot, c)| (slot, c.value))
            .collect();
        assert_eq!(chosen, [(4, guardian), (5, 7)]); // slot 6 has nothing left
    }

    fn compared(mut c: Candidate<i64>, versus: i64, wpa: f64) -> Candidate<i64> {
        c.comparison = Some(Comparison {
            versus,
            wpa,
            ci: Some((wpa - 0.01, wpa + 0.01)),
        });
        c
    }

    #[test]
    fn rank_lists_a_slot_by_popularity_with_shares() {
        let c = [
            candidate(30, 100, None),
            candidate(10, 600, None),
            candidate(20, 300, None),
        ];
        let ranked = rank(&c, Some(&10));
        let rows: Vec<(i64, f64, bool)> = ranked
            .rows
            .iter()
            .map(|r| (r.value, r.share, r.chosen))
            .collect();
        assert_eq!(rows, [(10, 0.6, true), (20, 0.3, false), (30, 0.1, false)]);
        assert_eq!(ranked.rows[0].confidence, Confidence::MostPlayed);
        assert_eq!(ranked.rows[1].versus, Versus::Alternatives); // its own estimate
        assert_eq!(ranked.rows[1].wpa, Some(0.01));
        assert_eq!(ranked.more, 0);
        assert_eq!(rank::<i64>(&[], None).rows, []);
    }

    #[test]
    fn rank_calls_a_difference_clear_only_as_choose_would() {
        let c = [
            candidate(10, 500, None),
            compared(candidate(20, 300, None), 10, 0.02),
            compared(candidate(30, 150, None), 10, -0.02),
        ];
        let rows = rank(&c, None).rows;
        let confidence: Vec<Confidence> = rows.iter().map(|r| r.confidence).collect();
        assert_eq!(
            confidence,
            [
                Confidence::MostPlayed,
                Confidence::ClearlyBetter,
                Confidence::ClearlyWorse
            ]
        );
        assert_eq!(
            (rows[1].wpa, rows[1].ci, rows[1].versus),
            (Some(0.02), Some((0.01, 0.03)), Versus::MostPlayed)
        );
        assert_eq!(rows[2].wpa, Some(-0.02));
        // The same rule picks the clearly better option.
        assert_eq!(choose(&c).map(|c| c.value), Some(20));

        // Compared with another option: its own estimate, no claim.
        let elsewhere = [
            candidate(10, 500, None),
            compared(candidate(40, 50, None), 99, 0.05),
        ];
        let row = &rank(&elsewhere, None).rows[1];
        assert_eq!(
            (row.confidence, row.versus, row.wpa),
            (
                Confidence::NoClearDifference,
                Versus::Alternatives,
                Some(0.01)
            )
        );
    }

    #[test]
    fn rank_tells_an_option_nearly_everyone_takes_from_one_with_too_few_games() {
        // Triumph on Lee Sin: 97% of games, flagged low_overlap: nothing to compare it with.
        let mut always = candidate(10, 4067, None);
        (always.too_few, always.low_overlap, always.wpa) = (true, true, None);
        let mut rare = candidate(20, 9, None);
        (rare.too_few, rare.low_overlap, rare.wpa) = (true, true, None);
        let rows = rank(&[always, rare.clone()], None).rows;
        let seen: Vec<Confidence> = rows.iter().map(|r| r.confidence).collect();
        assert_eq!(seen, [Confidence::AlmostAlways, Confidence::TooFewGames]);
        // Ahri jungle: one game, flagged the same way, is too little data, not "almost always".
        let mut once = candidate(10, 1, None);
        (once.too_few, once.low_overlap, once.wpa) = (true, true, None);
        let rows = rank(&[once, rare], None).rows;
        assert_eq!(rows[0].confidence, Confidence::TooFewGames);
        // Ashe's first shard: 594 games, under 300 of them comparable: not "few games".
        let mut many = candidate(30, 594, None);
        (many.too_few, many.wpa) = (true, None);
        let rows = rank(&[candidate(40, 3000, None), many], None).rows;
        assert_eq!(rows[1].confidence, Confidence::TooFewToCompare);
    }

    #[test]
    fn rank_marks_stronks_best_bet() {
        let mut bet = compared(candidate(20, 300, None), 10, 0.027);
        bet.unclear = true;
        let rows = rank(&[candidate(10, 500, None), bet], Some(&20)).rows;
        assert_eq!(rows[1].confidence, Confidence::BestBet);
        // The same option, not chosen, is just unclear.
        let rows = rank(&[candidate(10, 500, None), rows_unclear()], Some(&10)).rows;
        assert_eq!(rows[1].confidence, Confidence::NoClearDifference);
    }

    fn rows_unclear() -> Candidate<i64> {
        let mut c = compared(candidate(20, 300, None), 10, 0.027);
        c.unclear = true;
        c
    }

    #[test]
    fn rank_flags_too_few_games_unclear_and_fragile_options() {
        let mut rare = candidate(10, 500, None);
        rare.too_few = true;
        rare.wpa = None;
        let mut fragile = compared(candidate(20, 300, None), 10, 0.01);
        fragile.unclear = true;
        fragile.fragile = true;
        let mut unclear = compared(candidate(30, 200, None), 10, 0.03);
        unclear.unclear = true;
        let mut spell = candidate(40, 100, None);
        spell.wpa = None;
        let rows = rank(&[rare, fragile, unclear, spell], None).rows;
        let seen: Vec<(Confidence, bool)> =
            rows.iter().map(|r| (r.confidence, r.fragile)).collect();
        assert_eq!(
            seen,
            [
                (Confidence::TooFewToCompare, false), // 500 games, too few comparable ones
                (Confidence::NoClearDifference, true),
                (Confidence::NoClearDifference, false),
                (Confidence::NotEstimated, false),
            ]
        );
        let mut alone = candidate(40, 100, None);
        alone.wpa = None;
        let rows = rank(&[candidate(1, 900, None), alone], None).rows;
        assert_eq!(rows[1].confidence, Confidence::NotEstimated);
    }

    #[test]
    fn rank_lists_the_most_played_and_the_chosen_one_when_rarer() {
        let c: Vec<Candidate<i64>> = [(10, 500), (20, 400), (30, 300), (40, 200), (50, 100)]
            .into_iter()
            .map(|(id, played)| candidate(id, played, None))
            .collect();
        let ranked = rank(&c, Some(&50));
        let rows: Vec<(i64, bool, bool)> = ranked
            .rows
            .iter()
            .map(|r| (r.value, r.chosen, r.listed))
            .collect();
        // Every option comes back, so the player can pick any of them; the rest are counted.
        assert_eq!(
            rows,
            [
                (10, false, true),
                (20, false, true),
                (30, false, true),
                (40, false, false),
                (50, true, true)
            ]
        );
        assert_eq!(ranked.more, 1);
        assert_eq!(rank(&c, Some(&20)).more, 2);
        // A rare option keeps its numbers and confidence like the listed ones.
        assert_eq!(ranked.rows[3].confidence, Confidence::NoClearDifference);
    }
}
