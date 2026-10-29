//! `build.plan`: what an import would write for a champion and role, each choice labelled
//! "popular" or "clearly better" (ADR-043), and each slot's alternatives ranked by the same
//! rule (ADR-049). Writes nothing.

use serde::{Deserialize, Serialize};
use stronk_contracts::build_v1::{
    Build, Comparison, Flag, Interval, RuneChoice, RuneChoiceComparison, RuneChoiceKind,
};
use stronk_domain::Role;
use stronk_domain::select::{self, Candidate, Choice, Ranked, choose, choose_items, rank};

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
}

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
        .map(|(slot, choice)| SlotChoice { slot, choice })
        .collect();
    let runes_choice = choose(&runes);
    let spells_choice = choose(&spells);
    let rune_rows = rune_rows(&build.rune_choices, runes_choice.as_ref().map(|c| &c.value));
    let alternatives = Alternatives {
        runes: rank(&runes, runes_choice.as_ref().map(|c| &c.value)),
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
    Plan {
        champion: build.champion.to_string(),
        role,
        patch: build.patch.to_string(),
        games: build.games,
        elo: build.elo.to_string(),
        region: build.region.to_string(),
        runes: runes_choice,
        spells: spells_choice,
        items,
        alternatives,
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
            let candidates: Vec<Candidate<Vec<i64>>> = choices
                .iter()
                .filter(|c| row_of(c) == (kind, style, row))
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
                .collect();
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
