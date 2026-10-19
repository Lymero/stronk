//! `build.plan`: what an import would write for a champion and role, each choice labelled
//! "popular" or "clearly better" (ADR-043). Writes nothing.

use serde::{Deserialize, Serialize};
use stronk_contracts::build_v1::{Build, Comparison, Flag};
use stronk_domain::Role;
use stronk_domain::select::{self, Candidate, Choice, choose, choose_items};

use crate::commands::build_get;
use crate::registry::Command;
use crate::{CommandError, Context};

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Params {
    pub champion: String,
    pub role: Role,
    pub patch: Option<String>,
    pub region: Option<String>,
    pub elo: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Page {
    pub primary_style: i64,
    pub sub_style: i64,
    pub perks: Vec<i64>,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct SlotChoice {
    pub slot: u64,
    #[serde(flatten)]
    pub choice: Choice<i64>,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Plan {
    pub champion: String,
    pub role: Role,
    pub patch: String,
    pub runes: Option<Choice<Page>>,
    /// D then F, in the pair's usual order; the import moves Flash to the player's key.
    pub spells: Option<Choice<(i64, i64)>>,
    pub items: Vec<SlotChoice>,
}

pub fn command() -> Command {
    Command::new(
        "build.plan",
        "What an import would write, each choice labelled",
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

/// The choice for every decision of `build`.
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
            played: o.games.unwrap_or(o.n),
            claimable: claimable(o.wpa, &o.flags),
            unclear: o.flags.contains(&Flag::NoClearDifference),
            comparison: o.comparison.as_ref().map(compared),
        })
        .collect();
    let spells: Vec<Candidate<(i64, i64)>> = build
        .spells
        .iter()
        .map(|o| {
            let [d, f] = o.spells.map(|s| to_i64(s.get()));
            Candidate {
                value: (d, f),
                id: d.min(f) * 1_000 + d.max(f),
                played: o.games.unwrap_or(o.n),
                claimable: false, // spells have no WPA yet: always the popular pair
                unclear: true,
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
                    claimable: claimable(o.wpa, &o.flags),
                    unclear: o.flags.contains(&Flag::NoClearDifference),
                    comparison: o.comparison.as_ref().map(compared),
                })
                .collect();
            (slot, candidates)
        })
        .collect();
    let items = choose_items(&candidates)
        .into_iter()
        .map(|(slot, choice)| SlotChoice { slot, choice })
        .collect();
    Plan {
        champion: build.champion.to_string(),
        role,
        patch: build.patch.to_string(),
        runes: choose(&runes),
        spells: choose(&spells),
        items,
    }
}

fn claimable(wpa: Option<f64>, flags: &[Flag]) -> bool {
    wpa.is_some()
        && !flags
            .iter()
            .any(|f| matches!(f, Flag::LowSample | Flag::LowOverlap))
}

fn compared(c: &Comparison) -> select::Comparison {
    select::Comparison {
        versus: to_i64(c.versus),
        wpa: c.wpa,
        ci: c.ci.as_ref().map(|i| {
            let [low, high] = i.0;
            (low, high)
        }),
    }
}

/// Ids are small positive integers; anything beyond i64 can't match a real id.
fn to_i64(v: u64) -> i64 {
    i64::try_from(v).unwrap_or(-1)
}
