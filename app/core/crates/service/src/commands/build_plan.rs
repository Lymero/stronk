//! `build.plan`: what an import would write for a champion and role, each choice labelled
//! "popular" or "clearly better" (ADR-043), and each slot's alternatives ranked by the same
//! rule (ADR-049). Writes nothing.

use serde::{Deserialize, Serialize};
use stronk_contracts::build_v1::{
    Build, Comparison, Flag, Interval, RuneChoice, RuneChoiceComparison, RuneChoiceKind,
};
use stronk_domain::Role;
use stronk_domain::select::{self, Candidate, Choice, Label, Ranked, choose, choose_items, rank};

use crate::commands::build_get;
use crate::registry::Command;
use crate::{CommandError, Context};

#[derive(Debug, Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "PlanParams")]
pub struct Params {
    pub champion: String,
    pub role: Role,
    pub patch: Option<String>,
    pub region: Option<String>,
    pub elo: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Page {
    pub primary_style: i64,
    pub sub_style: i64,
    pub perks: Vec<i64>,
}

#[derive(Clone, Debug, PartialEq, Serialize, schemars::JsonSchema)]
pub struct SlotChoice {
    pub slot: u64,
    #[serde(flatten)]
    pub choice: Choice<i64>,
    /// The late slot only (ADR-067): the other late items the import lists after the choice,
    /// most played first.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub then: Vec<i64>,
}

/// Items in the late slot's block: its choice, then the most played others.
pub const LATE_ITEMS: usize = 6;

#[derive(Clone, Debug, PartialEq, Serialize, schemars::JsonSchema)]
pub struct SlotRanked {
    pub slot: u64,
    #[serde(flatten)]
    pub ranked: Ranked<i64>,
}

/// Every option of each slot, the most played and the chosen one marked as listed.
#[derive(Clone, Debug, PartialEq, Serialize, schemars::JsonSchema)]
pub struct Alternatives {
    pub runes: Ranked<Page>,
    pub spells: Ranked<(i64, i64)>,
    pub items: Vec<SlotRanked>,
    /// Each rune row on its own, for information (ADR-057): imports write whole pages.
    pub rune_rows: Vec<RuneRow>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum RowKind {
    Primary,
    Secondary,
    Shard,
}

/// The choices of one rune row: a primary tree's row, a secondary tree's pair, or a shard row.
/// Values are the runes chosen (two for a pair, smallest first); `chosen` marks the one in the
/// page Stronk imports.
#[derive(Clone, Debug, PartialEq, Serialize, schemars::JsonSchema)]
pub struct RuneRow {
    pub kind: RowKind,
    pub style: Option<i64>,
    pub row: Option<u64>,
    #[serde(flatten)]
    pub ranked: Ranked<Vec<i64>>,
}

#[derive(Clone, Debug, PartialEq, Serialize, schemars::JsonSchema)]
pub struct Plan {
    pub champion: String,
    pub role: Role,
    pub patch: String,
    /// Games behind the build file, and its elo bracket and region.
    pub games: u64,
    pub elo: String,
    pub region: String,
    pub runes: Option<Choice<Page>>,
    /// D then F, in the pair's usual order; the import moves Flash to the player's key.
    pub spells: Option<Choice<(i64, i64)>>,
    pub items: Vec<SlotChoice>,
    /// The slot of the late items: the item completed there and every later one, as one
    /// decision (ADR-067). None for data from before it, where every slot is its own.
    pub late_slot: Option<u64>,
    pub alternatives: Alternatives,
}

pub fn command() -> Command {
    Command::new(
        "build.plan",
        "What an import would write, each choice labelled, and each slot's alternatives",
        run,
    )
}

fn run(ctx: &Context, params: Params) -> Result<Plan, CommandError> {
    let build = build_get::fetch(
        ctx,
        &params.champion,
        params.role,
        params.patch.as_deref(),
        params.region.as_deref(),
        params.elo.as_deref(),
    )?;
    Ok(plan(&build, params.role))
}

/// The choice for every decision of `build`, and the alternatives behind it.
pub fn plan(build: &Build, role: Role) -> Plan {
    let runes: Vec<Candidate<Page>> = build
        .runes
        .iter()
        .map(|o| Candidate {
            value: Page {
                primary_style: to_i64(o.page.primary_style),
                sub_style: to_i64(o.page.sub_style),
                perks: o.page.perks.iter().map(|p| to_i64(*p)).collect(),
            },
            id: o.page.perks.first().map_or(0, |k| to_i64(*k)),
            // The estimate is the keystone's: every game with it, not only those with exactly
            // this page (`games`), which splits a keystone across its page variants.
            played: o.n,
            wpa: o.wpa,
            ci: o.ci.as_ref().map(interval),
            too_few: too_few(&o.flags),
            low_overlap: o.flags.contains(&Flag::LowOverlap),
            unclear: o.flags.contains(&Flag::NoClearDifference),
            fragile: o.flags.contains(&Flag::Fragile),
            comparison: o.comparison.as_ref().map(compared),
        })
        .collect();
    // Spells have no WPA yet, so never a claim: always the popular pair.
    let spells: Vec<Candidate<(i64, i64)>> = build
        .spells
        .iter()
        .map(|o| {
            let [d, f] = o.spells.map(|s| to_i64(s.get()));
            Candidate {
                value: (d, f),
                id: d.min(f) * 1_000 + d.max(f),
                played: o.games.unwrap_or(o.n),
                wpa: o.wpa,
                ci: o.ci.as_ref().map(interval),
                too_few: too_few(&o.flags),
                low_overlap: o.flags.contains(&Flag::LowOverlap),
                unclear: o.flags.contains(&Flag::NoClearDifference),
                fragile: o.flags.contains(&Flag::Fragile),
                comparison: None,
            }
        })
        .collect();
    let mut slots: Vec<u64> = build.items.iter().map(|o| o.slot.get()).collect();
    slots.sort_unstable();
    slots.dedup();
    let candidates: Vec<(u64, Vec<Candidate<i64>>)> = slots
        .into_iter()
        .map(|slot| {
            let candidates = build
                .items
                .iter()
                .filter(|o| o.slot.get() == slot)
                .map(|o| Candidate {
                    value: to_i64(o.item.get()),
                    id: to_i64(o.item.get()),
                    played: o.picks.unwrap_or(o.n),
                    wpa: o.wpa,
                    ci: o.ci.as_ref().map(interval),
                    too_few: too_few(&o.flags),
                    low_overlap: o.flags.contains(&Flag::LowOverlap),
                    unclear: o.flags.contains(&Flag::NoClearDifference),
                    fragile: o.flags.contains(&Flag::Fragile),
                    comparison: o.comparison.as_ref().map(compared),
                })
                .collect();
            (slot, candidates)
        })
        .collect();
    let items: Vec<SlotChoice> = choose_items(&candidates)
        .into_iter()
        .map(|(slot, choice)| SlotChoice {
            slot,
            choice,
            then: Vec::new(),
        })
        .collect();
    // The page chosen by its keystone, which the pages' list marks (each page stands for its
    // keystone); then its rows' best bets, which the import writes and the rune rows mark.
    let keystone_choice = choose(&runes);
    let runes_choice = keystone_choice
        .clone()
        .map(|c| with_row_bets(c, &build.rune_choices));
    let spells_choice = choose(&spells);
    let rune_rows = rune_rows(&build.rune_choices, runes_choice.as_ref().map(|c| &c.value));
    let alternatives = Alternatives {
        runes: rank(&runes, keystone_choice.as_ref().map(|c| &c.value)),
        spells: rank(&spells, spells_choice.as_ref().map(|c| &c.value)),
        items: candidates
            .iter()
            .map(|(slot, options)| {
                let chosen = items.iter().find(|c| c.slot == *slot);
                SlotRanked {
                    slot: *slot,
                    ranked: rank(options, chosen.map(|c| &c.choice.value)),
                }
            })
            .collect(),
        rune_rows,
    };
    let mut plan = Plan {
        champion: build.champion.to_string(),
        role,
        patch: build.patch.to_string(),
        games: build.games,
        elo: build.elo.to_string(),
        region: build.region.to_string(),
        runes: runes_choice,
        spells: spells_choice,
        items,
        late_slot: build.late_slot.map(|s| s.get()),
        alternatives,
    };
    with_late_items(&mut plan);
    plan
}

/// The late slot's other items (ADR-067): its options most played first, without any item
/// another slot or the late choice already has, up to [`LATE_ITEMS`] with the choice. Called
/// again when the player's picks change the items.
pub fn with_late_items(plan: &mut Plan) {
    let Some(late) = plan.late_slot else { return };
    let taken: Vec<i64> = plan.items.iter().map(|s| s.choice.value).collect();
    let then: Vec<i64> = plan
        .alternatives
        .items
        .iter()
        .find(|s| s.slot == late)
        .map(|s| {
            s.ranked
                .rows
                .iter()
                .map(|r| r.value)
                .filter(|v| !taken.contains(v))
                .take(LATE_ITEMS - 1)
                .collect()
        })
        .unwrap_or_default();
    for s in &mut plan.items {
        s.then = if s.slot == late {
            then.clone()
        } else {
            Vec::new()
        };
    }
}

/// The published rune choices grouped by row, primary rows first, then pairs, then shards, each
/// ranked by the same rule as every slot; the row's choice in `page` is marked chosen.
fn rune_rows(choices: &[RuneChoice], page: Option<&Page>) -> Vec<RuneRow> {
    let mut rows: Vec<(RowKind, Option<i64>, Option<u64>)> = choices.iter().map(row_of).collect();
    rows.sort_unstable();
    rows.dedup();
    rows.into_iter()
        .map(|(kind, style, row)| {
            let candidates = row_candidates(choices, (kind, style, row));
            let chosen = page.and_then(|p| in_page(p, kind, style, row));
            RuneRow {
                kind,
                style,
                row,
                ranked: rank(&candidates, chosen.as_ref()),
            }
        })
        .collect()
}

/// One rune row's published choices as candidates.
fn row_candidates(
    choices: &[RuneChoice],
    key: (RowKind, Option<i64>, Option<u64>),
) -> Vec<Candidate<Vec<i64>>> {
    choices
        .iter()
        .filter(|c| row_of(c) == key)
        .map(|c| {
            let value: Vec<i64> = c.perks.iter().map(|p| to_i64(*p)).collect();
            Candidate {
                id: perks_id(&value),
                value,
                played: c.games.unwrap_or(c.n),
                wpa: c.wpa,
                ci: c.ci.as_ref().map(interval),
                too_few: too_few(&c.flags),
                low_overlap: c.flags.contains(&Flag::LowOverlap),
                unclear: c.flags.contains(&Flag::NoClearDifference),
                fragile: c.flags.contains(&Flag::Fragile),
                comparison: c.comparison.as_ref().map(row_compared),
            }
        })
        .collect()
}

/// Stronk's page with each of its rows chosen by the rule (ADR-065): the page is chosen whole by
/// its keystone; then, row by row (the primary tree's rows, the secondary pair, the shards), the
/// row's choice replaces the page's rune: its best bet against the row's most played rune, else
/// that most played one (a page's rune that trails it is the worse bet). A popular page that
/// changed by a best bet is labelled by its largest.
fn with_row_bets(choice: Choice<Page>, choices: &[RuneChoice]) -> Choice<Page> {
    let Choice {
        mut value,
        mut label,
    } = choice;
    let mut keys: Vec<(RowKind, Option<i64>, Option<u64>)> = choices.iter().map(row_of).collect();
    keys.sort_unstable();
    keys.dedup();
    let mut largest: Option<(f64, Label)> = None;
    for key in keys {
        let (kind, style, row) = key;
        let applies = match kind {
            RowKind::Primary => style == Some(value.primary_style),
            RowKind::Secondary => style == Some(value.sub_style),
            RowKind::Shard => true,
        };
        if !applies {
            continue;
        }
        let Some(chosen) = choose(&row_candidates(choices, key)) else {
            continue;
        };
        let gain = match chosen.label {
            Label::BestBet { wpa, .. } | Label::ClearlyBetter { wpa, .. } => Some(wpa),
            Label::Popular | Label::Picked => None,
        };
        let at = |i: Option<u64>| i.and_then(|i| usize::try_from(i).ok());
        let placed = match (kind, chosen.value.as_slice()) {
            (RowKind::Primary, [rune]) => at(row)
                .and_then(|i| value.perks.get_mut(i))
                .map(|p| *p = *rune),
            (RowKind::Shard, [shard]) => at(row.map(|r| r + 5))
                .and_then(|i| value.perks.get_mut(i))
                .map(|p| *p = *shard),
            // The same pair in another order is the page's own: it keeps its order.
            (RowKind::Secondary, [low, high]) => value.perks.get_mut(4..6).map(|p| {
                if !(p.contains(low) && p.contains(high)) {
                    p.copy_from_slice(&[*low, *high]);
                }
            }),
            _ => None,
        };
        if let (Some(_), Some(wpa)) = (placed, gain)
            && largest.as_ref().is_none_or(|(w, _)| wpa > *w)
        {
            largest = Some((wpa, chosen.label));
        }
    }
    if let (Label::Popular, Some((_, row_label))) = (label, largest) {
        label = row_label;
    }
    Choice { value, label }
}

fn row_of(c: &RuneChoice) -> (RowKind, Option<i64>, Option<u64>) {
    let kind = match c.kind {
        RuneChoiceKind::Primary => RowKind::Primary,
        RuneChoiceKind::Secondary => RowKind::Secondary,
        RuneChoiceKind::Shard => RowKind::Shard,
    };
    (kind, c.style.map(to_i64), c.row.map(|r| r.get()))
}

/// What `page` has in a row: perks are the keystone, three primary runes, two secondary runes,
/// then three shards.
fn in_page(page: &Page, kind: RowKind, style: Option<i64>, row: Option<u64>) -> Option<Vec<i64>> {
    let at = |i: u64| {
        usize::try_from(i)
            .ok()
            .and_then(|i| page.perks.get(i))
            .copied()
    };
    match kind {
        RowKind::Primary if style == Some(page.primary_style) => at(row?).map(|r| vec![r]),
        RowKind::Secondary if style == Some(page.sub_style) => {
            let mut pair = vec![at(4)?, at(5)?];
            pair.sort_unstable();
            Some(pair)
        }
        RowKind::Shard => at(row? + 5).map(|r| vec![r]),
        RowKind::Primary | RowKind::Secondary => None,
    }
}

/// A row's choice as one id for comparisons: the rune, or a pair as `low * 100000 + high`.
fn perks_id(perks: &[i64]) -> i64 {
    match perks {
        [one] => *one,
        [low, high] => low.saturating_mul(100_000).saturating_add(*high),
        _ => -1,
    }
}

fn row_compared(c: &RuneChoiceComparison) -> select::Comparison {
    let versus: Vec<i64> = c.versus.iter().map(|v| to_i64(*v)).collect();
    select::Comparison {
        versus: perks_id(&versus),
        wpa: c.wpa,
        ci: c.ci.as_ref().map(interval),
    }
}

fn too_few(flags: &[Flag]) -> bool {
    flags
        .iter()
        .any(|f| matches!(f, Flag::LowSample | Flag::LowOverlap))
}

fn interval(i: &Interval) -> (f64, f64) {
    let [low, high] = i.0;
    (low, high)
}

fn compared(c: &Comparison) -> select::Comparison {
    select::Comparison {
        versus: to_i64(c.versus),
        wpa: c.wpa,
        ci: c.ci.as_ref().map(interval),
    }
}

/// Ids are small positive integers; anything beyond i64 can't match a real id.
fn to_i64(v: u64) -> i64 {
    i64::try_from(v).unwrap_or(-1)
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    fn choices(json: serde_json::Value) -> Vec<RuneChoice> {
        serde_json::from_value(json).unwrap()
    }

    /// A build with these items (slot, item, picks), late items from slot 4.
    pub(crate) fn with_items(items: &[(u64, i64, u64)]) -> Build {
        let items: Vec<serde_json::Value> = items
            .iter()
            .map(|(slot, item, picks)| {
                serde_json::json!({"slot": slot, "item": item, "picks": picks, "n": picks,
                                   "wpa": null, "ci": null, "flags": ["low_sample"]})
            })
            .collect();
        serde_json::from_value(serde_json::json!({
            "schemaVersion": 1, "patch": "16.20", "region": "all", "elo": "master_plus",
            "champion": "LeeSin", "role": "JUNGLE", "games": 100, "runes": [], "spells": [],
            "items": items, "lateSlot": 4
        }))
        .unwrap()
    }

    #[test]
    fn the_late_slot_lists_its_choice_then_the_most_played_others() {
        let mut items = vec![(1, 6698, 90), (2, 6699, 80), (3, 6333, 70), (4, 6333, 9)];
        items.extend([(4, 3026, 60), (4, 3156, 50), (4, 3053, 40), (4, 6694, 30)]);
        items.extend([(4, 3071, 20), (4, 6610, 10), (4, 3742, 5)]);
        let mut plan = plan(&with_items(&items), Role::Jungle);
        assert_eq!(plan.late_slot, Some(4));
        let late = plan.items.iter().find(|s| s.slot == 4).unwrap();
        assert_eq!(late.choice.value, 3026);
        // Death's Dance, already item 3, is left out; six items in all.
        assert_eq!(late.then, vec![3156, 3053, 6694, 3071, 6610]);
        assert!(
            plan.items
                .iter()
                .filter(|s| s.slot != 4)
                .all(|s| s.then.is_empty())
        );
        // The player's pick in another slot leaves the late items too.
        plan.items[0].choice.value = 3156;
        with_late_items(&mut plan);
        assert_eq!(plan.items[3].then, vec![3053, 6694, 3071, 6610, 3742]);
    }

    #[test]
    fn data_from_before_the_late_slot_keeps_every_slot_its_own() {
        let mut build = with_items(&[(4, 3026, 60), (5, 3156, 50)]);
        build.late_slot = None;
        let plan = plan(&build, Role::Jungle);
        assert_eq!(plan.late_slot, None);
        assert!(plan.items.iter().all(|s| s.then.is_empty()));
    }

    #[test]
    fn a_rows_best_bet_replaces_the_pages_rune_and_the_rest_stays() {
        // Lee Sin jungle: Cut Down against Coup de Grace, +2.7 likely between 0.0 and +5.6.
        let rows = choices(serde_json::json!([
            {"kind": "primary", "style": 8000, "row": 3, "perks": [8014], "games": 2194, "n": 2194,
             "wpa": -0.024, "ci": [-0.041, -0.008], "flags": ["no_clear_difference"]},
            {"kind": "primary", "style": 8000, "row": 3, "perks": [8017], "games": 1704, "n": 1704,
             "wpa": 0.019, "ci": [0.002, 0.036], "flags": ["no_clear_difference"],
             "comparison": {"versus": [8014], "wpa": 0.027, "ci": [-0.00005, 0.05555], "q": 0.61}},
            {"kind": "shard", "row": 1, "perks": [5005], "games": 3765, "n": 3765,
             "wpa": -0.013, "ci": [-0.03, 0.004], "flags": ["no_clear_difference"]},
            {"kind": "shard", "row": 1, "perks": [5008], "games": 425, "n": 425,
             "wpa": 0.01, "ci": [-0.04, 0.06], "flags": ["no_clear_difference"],
             "comparison": {"versus": [5005], "wpa": 0.013, "ci": [-0.04, 0.066], "q": 0.9}},
            {"kind": "primary", "style": 8100, "row": 3, "perks": [8135], "games": 68, "n": 68,
             "wpa": 0.03, "ci": [0.01, 0.05], "flags": [],
             "comparison": {"versus": [8106], "wpa": 0.05, "ci": [0.04, 0.06], "q": 0.01}}
        ]));
        let page = Page {
            primary_style: 8000,
            sub_style: 8300,
            perks: vec![8010, 9111, 9104, 8014, 8347, 8304, 5005, 5008, 5001],
        };
        let chosen = with_row_bets(
            Choice {
                value: page,
                label: Label::Popular,
            },
            &rows,
        );
        // Cut Down takes row 3; the noisy shard and the other tree's row change nothing.
        assert_eq!(
            chosen.value.perks,
            vec![8010, 9111, 9104, 8017, 8347, 8304, 5005, 5008, 5001]
        );
        // A page whose shard trails its row's most played one takes the most played.
        let page = Page {
            primary_style: 8000,
            sub_style: 8300,
            perks: vec![8010, 9111, 9104, 8014, 8347, 8304, 5008, 5008, 5001],
        };
        let chosen = with_row_bets(
            Choice {
                value: page,
                label: Label::Popular,
            },
            &rows,
        );
        assert_eq!(chosen.value.perks[6], 5005);
        assert_eq!(
            chosen.label,
            Label::BestBet {
                wpa: 0.027,
                ci: Some((-0.000_05, 0.055_55)),
                games: 1704
            }
        );
    }
}
