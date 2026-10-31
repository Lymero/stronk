//! `build.plan`: what an import would write for a champion and role, each choice labelled
//! "popular" or "clearly better" (ADR-043), and each slot's alternatives ranked by the same
//! rule (ADR-049). Writes nothing.

use serde::{Deserialize, Serialize};
use stronk_contracts::build_v1::{
    BootsOption, Build, Comparison, Flag, Interval, PurchaseComparison, PurchaseOption, RuneChoice,
    RuneChoiceComparison, RuneChoiceKind,
};
use stronk_domain::Role;
use stronk_domain::damage::{self, Against};
use stronk_domain::select::{
    self, Candidate, Choice, Label, Ranked, Row, by_judgement, choose, choose_items, rank,
};

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
    /// The enemy champions picked so far: boots are chosen against their damage (ADR-074).
    #[serde(default)]
    pub enemies: Vec<i64>,
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
    /// The slot's other items the import lists after the choice in its block, most played
    /// first (ADR-067, ADR-069).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub then: Vec<i64>,
}

/// Items in a slot's block of the item set: its choice, then the most played others.
pub const SLOT_ITEMS: usize = 4;
/// Items in the late slot's block, which stands for three or four items.
pub const LATE_ITEMS: usize = 6;
/// An alternative needs this share of its slot's games to be listed in the block.
pub const BLOCK_MIN_SHARE: f64 = 0.02;

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
    /// The starts (ADR-071): each the items bought before leaving base, without supplies.
    pub start: Ranked<Vec<i64>>,
    /// The first components (ADR-072): each the items bought on the first trip back, without
    /// supplies, boots or completed items.
    pub components: Ranked<Vec<i64>>,
    /// The upgraded boots (ADR-073).
    pub boots: Ranked<i64>,
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
    /// The start (ADR-071): its items without supplies, smallest id first; the import writes
    /// what is most often bought with it.
    pub start: Option<Choice<Vec<i64>>>,
    /// What the import writes for that start: what is most often bought with it, supplies
    /// included, repeated as bought.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub start_buy: Vec<i64>,
    /// The first components (ADR-072), as the start.
    pub components: Option<Choice<Vec<i64>>>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub components_buy: Vec<i64>,
    /// The upgraded boots (ADR-073), and the other boots their block lists after them.
    pub boots: Option<Choice<i64>>,
    /// The enemy damage the boots were chosen against (ADR-074); None: over every game, as
    /// fewer than three enemies are known or the data has no boots for that kind of team.
    pub boots_against: Option<Against>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub boots_then: Vec<i64>,
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
    let against = against_for(ctx, &build, &params.enemies);
    Ok(plan(&build, params.role, against))
}

/// The enemy team's damage from the picks so far and the patch's champion ratings (ADR-074).
/// Without the ratings (older data), nothing: boots are then chosen over every game.
pub fn against_for(ctx: &Context, build: &Build, enemies: &[i64]) -> Option<Against> {
    let patch = build.patch.parse().ok()?;
    let champions = ctx.builds.champions(patch).ok()?;
    let rating = |id: i64| {
        champions
            .champions
            .iter()
            .find(|c| i64::try_from(c.id.get()).ok() == Some(id))
            .map(|c| {
                (
                    u64::try_from(c.attack).unwrap_or(0),
                    u64::try_from(c.magic).unwrap_or(0),
                )
            })
    };
    damage::against(
        enemies,
        rating,
        champions.physical_below,
        champions.magic_from,
    )
}

/// The choice for every decision of `build`, and the alternatives behind it; boots against
/// the enemy team's damage when it is known and the data has boots for it (ADR-074).
pub fn plan(build: &Build, role: Role, against: Option<Against>) -> Plan {
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
    let starts = purchase_candidates(&build.starts);
    let start_choice = choose(&starts);
    let components = purchase_candidates(&build.first_components);
    let components_choice = choose(&components);
    // Boots against this kind of team if the data has them, else over every game.
    let profile = |o: &BootsOption| o.against.map(|a| a.to_string());
    let boots_against = against.filter(|a| {
        build
            .boots
            .iter()
            .any(|o| profile(o).as_deref() == Some(a.as_str()))
    });
    let boots: Vec<Candidate<i64>> = build
        .boots
        .iter()
        .filter(|o| profile(o).as_deref() == boots_against.map(Against::as_str))
        .map(|o| Candidate {
            value: to_i64(o.item.get()),
            id: to_i64(o.item.get()),
            played: o.games,
            wpa: o.wpa,
            ci: o.ci.as_ref().map(interval),
            too_few: too_few(&o.flags),
            low_overlap: o.flags.contains(&Flag::LowOverlap),
            unclear: o.flags.contains(&Flag::NoClearDifference),
            fragile: o.flags.contains(&Flag::Fragile),
            comparison: o.comparison.as_ref().map(compared),
        })
        .collect();
    let boots_choice = choose(&boots);
    let rune_rows = rune_rows(&build.rune_choices, runes_choice.as_ref().map(|c| &c.value));
    let alternatives = Alternatives {
        runes: rank(&runes, keystone_choice.as_ref().map(|c| &c.value)),
        spells: rank(&spells, spells_choice.as_ref().map(|c| &c.value)),
        start: rank(&starts, start_choice.as_ref().map(|c| &c.value)),
        components: rank(&components, components_choice.as_ref().map(|c| &c.value)),
        boots: rank(&boots, boots_choice.as_ref().map(|c| &c.value)),
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
        start_buy: start_choice
            .as_ref()
            .map(|c| purchase_buy(&build.starts, &c.value))
            .unwrap_or_default(),
        start: start_choice,
        components_buy: components_choice
            .as_ref()
            .map(|c| purchase_buy(&build.first_components, &c.value))
            .unwrap_or_default(),
        components: components_choice,
        boots: boots_choice,
        boots_then: Vec::new(),
        boots_against,
        items,
        late_slot: build.late_slot.map(|s| s.get()),
        alternatives,
    };
    with_alternatives(&mut plan);
    plan
}

/// Each slot's other items for its block (ADR-069): its options with at least
/// [`BLOCK_MIN_SHARE`] of its games in Stronk's order (its choice, then its judgement,
/// ADR-070), without any item a slot already takes, up to [`SLOT_ITEMS`] with the slot's item
/// ([`LATE_ITEMS`] for the late slot, ADR-067). The block starts with the slot's item, the
/// player's pick when they made one: a pick overrules Stronk, which then comes next. Called
/// again when the player's picks change the items.
pub fn with_alternatives(plan: &mut Plan) {
    let taken: Vec<i64> = plan.items.iter().map(|s| s.choice.value).collect();
    for s in &mut plan.items {
        let size = if plan.late_slot == Some(s.slot) {
            LATE_ITEMS
        } else {
            SLOT_ITEMS
        };
        s.then = plan
            .alternatives
            .items
            .iter()
            .find(|a| a.slot == s.slot)
            .map(|a| block_others(&a.ranked, &taken, size))
            .unwrap_or_default();
    }
    // Boots are their own block (ADR-073): the other boots, in the same order.
    let boots: Vec<i64> = plan.boots.iter().map(|c| c.value).collect();
    plan.boots_then = if plan.boots.is_some() {
        block_others(&plan.alternatives.boots, &boots, SLOT_ITEMS)
    } else {
        Vec::new()
    };
}

/// A block's items after its first: the options with [`BLOCK_MIN_SHARE`] of the games, not
/// `taken`, in Stronk's order, `size - 1` of them.
fn block_others(ranked: &Ranked<i64>, taken: &[i64], size: usize) -> Vec<i64> {
    let mut rows: Vec<&Row<i64>> = ranked
        .rows
        .iter()
        .filter(|r| r.share >= BLOCK_MIN_SHARE && !taken.contains(&r.value))
        .collect();
    by_judgement(&mut rows);
    rows.iter().map(|r| r.value).take(size - 1).collect()
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

/// Published purchases (starts, first components) as candidates (ADR-071, ADR-072).
fn purchase_candidates(options: &[PurchaseOption]) -> Vec<Candidate<Vec<i64>>> {
    options
        .iter()
        .map(|o| {
            let value = purchase_items(&o.items);
            Candidate {
                id: purchase_id(&value),
                value,
                played: o.games,
                wpa: o.wpa,
                ci: o.ci.as_ref().map(interval),
                too_few: too_few(&o.flags),
                low_overlap: o.flags.contains(&Flag::LowOverlap),
                unclear: o.flags.contains(&Flag::NoClearDifference),
                fragile: o.flags.contains(&Flag::Fragile),
                comparison: o.comparison.as_ref().map(purchase_compared),
            }
        })
        .collect()
}

/// What is most often bought with the purchase of `items` among `options` (its items alone if
/// it isn't published).
pub fn purchase_buy(options: &[PurchaseOption], items: &[i64]) -> Vec<i64> {
    options
        .iter()
        .find(|o| purchase_items(&o.items) == items)
        .map_or_else(
            || items.to_vec(),
            |o| o.buy.iter().map(|i| to_i64(i.get())).collect(),
        )
}

/// A purchase's items, smallest id first, each once, whatever order they come in.
pub fn purchase_items(items: &[std::num::NonZeroU64]) -> Vec<i64> {
    let mut value: Vec<i64> = items.iter().map(|i| to_i64(i.get())).collect();
    value.sort_unstable();
    value.dedup();
    value
}

/// One id for a set of items, to match a purchase with the one it is compared with.
fn purchase_id(items: &[i64]) -> i64 {
    items
        .iter()
        .fold(0_i64, |id, i| id.wrapping_mul(1_000_003).wrapping_add(*i))
}

fn purchase_compared(c: &PurchaseComparison) -> select::Comparison {
    select::Comparison {
        versus: purchase_id(&purchase_items(&c.versus)),
        wpa: c.wpa,
        ci: c.ci.as_ref().map(interval),
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
        let mut plan = plan(&with_items(&items), Role::Jungle, None);
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
        with_alternatives(&mut plan);
        assert_eq!(plan.items[3].then, vec![3053, 6694, 3071, 6610, 3742]);
    }

    #[test]
    fn a_block_follows_stronks_judgement_after_the_slots_item() {
        // Eclipse most played; Profane Hydra ahead, not yet clear (Stronk's best bet); Bastionbreaker
        // clearly worse; Black Cleaver and Sundered Sky not measured against Eclipse.
        let compared = |wpa: f64, low: f64, high: f64| serde_json::json!({"versus": 6692, "wpa": wpa, "ci": [low, high], "q": 0.5});
        let option =
            |item: i64, picks: u64, flags: &[&str], comparison: Option<serde_json::Value>| {
                let mut o = serde_json::json!({"slot": 1, "item": item, "picks": picks, "n": picks,
                                           "wpa": 0.0, "ci": [-0.01, 0.01], "flags": flags});
                if let Some(k) = comparison {
                    o["comparison"] = k;
                }
                o
            };
        let build: Build = serde_json::from_value(serde_json::json!({
            "schemaVersion": 1, "patch": "16.20", "region": "all", "elo": "master_plus",
            "champion": "LeeSin", "role": "JUNGLE", "games": 3000, "runes": [], "spells": [],
            "items": [
                option(6692, 1500, &[], None),
                option(6698, 600, &["no_clear_difference"], Some(compared(0.03, 0.0, 0.06))),
                option(3071, 400, &["low_sample"], None),
                option(2520, 300, &[], Some(compared(-0.04, -0.06, -0.02))),
                option(6610, 200, &["low_sample"], None),
            ]
        }))
        .unwrap();
        let mut plan = plan(&build, Role::Jungle, None);
        assert_eq!(plan.items[0].choice.value, 6698);
        // The baseline leads what Stronk knows nothing against; the clearly worse one is last.
        assert_eq!(plan.items[0].then, vec![6692, 3071, 6610]);
        // The player's pick overrules Stronk, whose choice comes next.
        plan.items[0].choice.value = 3071;
        with_alternatives(&mut plan);
        assert_eq!(plan.items[0].then, vec![6698, 6692, 6610]);
    }

    #[test]
    fn data_from_before_the_late_slot_keeps_every_slot_its_own() {
        let mut build = with_items(&[(4, 3026, 60), (5, 3156, 50)]);
        build.late_slot = None;
        let plan = plan(&build, Role::Jungle, None);
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
