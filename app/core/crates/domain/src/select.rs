//! What to import (ADR-043): the most played whole combination, unless an option is clearly
//! better than it. Pure: the service turns published build files into [`Candidate`]s.

use std::collections::BTreeMap;

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
    /// The player picked this published option instead of Stronk's choice.
    Picked,
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

/// The popular candidate (most played; ties to the smallest id), or the clearly better one
/// with the largest win impact against it. `None` without candidates.
pub fn choose<T: Clone>(candidates: &[Candidate<T>]) -> Option<Choice<T>> {
    let popular = candidates.iter().min_by(|a, b| by_popularity(a, b))?;
    let better = candidates
        .iter()
        .filter_map(|c| c.clear_against(popular.id).map(|k| (c, k)))
        .filter(|(_, k)| k.wpa > 0.0)
        .max_by(|(a, x), (b, y)| x.wpa.total_cmp(&y.wpa).then(b.id.cmp(&a.id)));
    Some(match better {
        Some((c, k)) => Choice {
            value: c.value.clone(),
            label: Label::ClearlyBetter {
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
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Confidence {
    /// Beats the most played option head to head, by the rule [`choose`] uses.
    ClearlyBetter,
    /// Loses to the most played option head to head, by the same rule.
    ClearlyWorse,
    /// The most played option: what the others are compared with.
    MostPlayed,
    /// Has a number, but isn't distinguishable from the most played option.
    NoClearDifference,
    /// `low_sample` or `low_overlap`: too few comparable games for a number to mean much.
    TooFewGames,
    /// The most played option, flagged `low_overlap`: chosen in nearly every comparable game, so
    /// there is nothing to compare it with (not a lack of games).
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
                _ if most_played && c.low_overlap => Confidence::AlmostAlways,
                _ if c.too_few => Confidence::TooFewGames,
                Some(k) if k.wpa > 0.0 => Confidence::ClearlyBetter,
                Some(k) if k.wpa < 0.0 => Confidence::ClearlyWorse,
                _ if most_played => Confidence::MostPlayed,
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

pub const FLASH: i64 = 4;

/// The chosen pair on the player's keys: Flash stays on the key it is on now (D or F); a
/// spell already on a key stays there; otherwise the pair's usual order.
pub fn arrange_spells(pair: (i64, i64), current: (i64, i64)) -> (i64, i64) {
    let (a, b) = pair;
    let other = |s: i64| if s == a { b } else { a };
    let has = |s: i64| s == a || s == b;
    if has(FLASH) {
        if current.1 == FLASH {
            return (other(FLASH), FLASH);
        }
        if current.0 == FLASH {
            return (FLASH, other(FLASH));
        }
    }
    if has(current.0) {
        (current.0, other(current.0))
    } else if has(current.1) {
        (other(current.1), current.1)
    } else {
        pair
    }
}

/// A rune page in the client, as far as ownership goes.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PageInfo {
    pub id: i64,
    pub name: String,
    pub editable: bool,
}

pub const PREFIX: &str = "Stronk: ";

/// Stronk owns a page or item set exactly when its name starts with [`PREFIX`].
pub fn is_ours(name: &str) -> bool {
    name.starts_with(PREFIX)
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PagePlan {
    /// Stronk's own pages, deleted before the new one is created.
    pub delete: Vec<i64>,
}

/// Which pages to delete so a new Stronk page fits; `None` when it would take deleting one of
/// the player's. `capacity` is how many editable pages the account may have.
pub fn plan_rune_page(pages: &[PageInfo], capacity: usize) -> Option<PagePlan> {
    let editable: Vec<&PageInfo> = pages.iter().filter(|p| p.editable).collect();
    let ours: Vec<i64> = editable
        .iter()
        .filter(|p| is_ours(&p.name))
        .map(|p| p.id)
        .collect();
    let theirs = editable.len() - ours.len();
    (theirs < capacity).then_some(PagePlan { delete: ours })
}

/// Whether a rune page is one the client accepts, by the client's own layout (ADR-059): a
/// keystone and one rune per row of the primary tree, two runes from two different rows of
/// another tree, and one shard per shard row. `trees` maps a tree to its rows, keystones first;
/// `shards` holds the shard rows. The reason when it isn't.
pub fn valid_page(
    primary: i64,
    secondary: i64,
    perks: &[i64],
    trees: &BTreeMap<i64, Vec<Vec<i64>>>,
    shards: &[Vec<i64>],
) -> Result<(), String> {
    let (Some(main), Some(side)) = (trees.get(&primary), trees.get(&secondary)) else {
        return Err("unknown rune tree".into());
    };
    if primary == secondary {
        return Err("the secondary tree must differ from the primary".into());
    }
    let [k, r1, r2, r3, s1, s2, f1, f2, f3] = perks else {
        return Err("a page has nine runes".into());
    };
    for (row, rune) in [k, r1, r2, r3].into_iter().enumerate() {
        if !main.get(row).is_some_and(|r| r.contains(rune)) {
            return Err(format!("rune {rune} isn't in row {row} of its tree"));
        }
    }
    let row_of =
        |rune: &i64| (1..side.len()).find(|&i| side.get(i).is_some_and(|r| r.contains(rune)));
    match (row_of(s1), row_of(s2)) {
        (Some(a), Some(b)) if a != b => {}
        (Some(_), Some(_)) => return Err("the two secondary runes share a row".into()),
        _ => return Err("a secondary rune isn't in its tree".into()),
    }
    for (row, shard) in [f1, f2, f3].into_iter().enumerate() {
        if !shards.get(row).is_some_and(|r| r.contains(shard)) {
            return Err(format!("shard {shard} isn't in shard row {}", row + 1));
        }
    }
    Ok(())
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
        }
    }

    #[test]
    fn the_most_played_wins_without_a_clear_alternative() {
        let c = [
            candidate(1, 10, None),
            candidate(2, 30, None),
            candidate(3, 20, Some((2, 0.03))),
        ];
        let mut unclear = c.clone();
        unclear[2].unclear = true;
        assert_eq!(
            choose(&unclear),
            Some(Choice {
                value: 2,
                label: Label::Popular
            })
        );
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

    #[test]
    fn flash_stays_on_its_key() {
        let (smite, ignite, ghost) = (11, 14, 6);
        assert_eq!(
            arrange_spells((smite, FLASH), (FLASH, ignite)),
            (FLASH, smite)
        );
        assert_eq!(
            arrange_spells((FLASH, smite), (ignite, FLASH)),
            (smite, FLASH)
        );
        assert_eq!(
            arrange_spells((FLASH, smite), (smite, ghost)),
            (smite, FLASH)
        ); // smite stays on D
        assert_eq!(
            arrange_spells((smite, FLASH), (ghost, ignite)),
            (smite, FLASH)
        ); // usual order
        assert_eq!(
            arrange_spells((ghost, ignite), (ignite, FLASH)),
            (ignite, ghost)
        ); // ignite stays on D
    }

    #[test]
    fn only_stronk_pages_make_room() {
        let page = |id, name: &str, editable| PageInfo {
            id,
            name: name.into(),
            editable,
        };
        let pages = [
            page(1, "Mine", true),
            page(2, "Stronk: Ahri MIDDLE", true),
            page(3, "Preset", false),
        ];
        assert_eq!(
            plan_rune_page(&pages, 2),
            Some(PagePlan { delete: vec![2] })
        );
        let full = [page(1, "Mine", true), page(4, "Also mine", true)];
        assert_eq!(plan_rune_page(&full, 2), None);
        assert_eq!(plan_rune_page(&full, 3), Some(PagePlan { delete: vec![] }));
        assert!(!is_ours("Stronk Ahri") && is_ours("Stronk: Ahri"));
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
        let rows = rank(&[always, rare], None).rows;
        let seen: Vec<Confidence> = rows.iter().map(|r| r.confidence).collect();
        assert_eq!(seen, [Confidence::AlmostAlways, Confidence::TooFewGames]);
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
                (Confidence::TooFewGames, false),
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

    /// Trees by id, and the shard rows.
    type Layout = (BTreeMap<i64, Vec<Vec<i64>>>, Vec<Vec<i64>>);

    fn layout() -> Layout {
        let trees = BTreeMap::from([
            (
                8000,
                vec![
                    vec![8005, 8010],
                    vec![9111, 8009],
                    vec![9104, 9105],
                    vec![8014, 8017],
                ],
            ),
            (
                8300,
                vec![
                    vec![8369],
                    vec![8304, 8321],
                    vec![8345, 8313],
                    vec![8347, 8410],
                ],
            ),
        ]);
        (
            trees,
            vec![vec![5008, 5005], vec![5008, 5010], vec![5011, 5001]],
        )
    }

    #[test]
    fn a_page_is_valid_only_in_the_clients_layout() {
        let (trees, shards) = layout();
        let ok = [8010, 9111, 9104, 8014, 8304, 8347, 5005, 5008, 5001];
        assert_eq!(valid_page(8000, 8300, &ok, &trees, &shards), Ok(()));
        let with = |i: usize, v: i64| {
            let mut p = ok;
            p[i] = v;
            valid_page(8000, 8300, &p, &trees, &shards)
        };
        assert!(with(0, 9111).is_err()); // not a keystone
        assert!(with(2, 9111).is_err()); // a row 1 rune in row 2
        assert!(with(5, 8321).is_err()); // two secondary runes from the same row
        assert!(with(5, 9104).is_err()); // a secondary rune from the primary tree
        assert!(with(8, 5005).is_err()); // an offense shard in the defense row
        assert!(valid_page(8000, 8000, &ok, &trees, &shards).is_err());
        assert!(valid_page(8000, 8100, &ok, &trees, &shards).is_err()); // unknown tree
        assert!(valid_page(8000, 8300, &ok[..8], &trees, &shards).is_err());
    }
}
