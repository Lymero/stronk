//! `build.plan`: what an import would write for a champion and role, each choice labelled
//! "popular" or "clearly better" (ADR-043), and each slot's alternatives ranked by the same
//! rule (ADR-049). Writes nothing.

use serde::{Deserialize, Serialize};
use stronk_contracts::build_v1::{
    BootsOption, BootsOptionAgainst, Build, Comparison, Flag, Interval, Patch as ContractPatch,
    PurchaseComparison, PurchaseOption, RuneChoice, RuneChoiceComparison, RuneChoiceKind, Skill,
    SkillComparison, SkillOption, SpellComparison,
};
use stronk_domain::damage::{self, Against};
use stronk_domain::item_set::{block_order, block_others, block_size, purchase_id, purchase_items};
use stronk_domain::runes::{Page, RowKey, RowKind, in_page, perks_id, with_row_bets};
use stronk_domain::select::{self, Candidate, Choice, Ranked, choose, choose_items, rank};
use stronk_domain::{Role, Window};
use stronk_domain::{skills, spells};

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
    /// The player's elo bracket; a champion and role it has no build for get the closest
    /// bracket's, wider first, and the plan's `elo` says which (ADR-078, ADR-079). Ignored with
    /// a `patch` or `region`, which ask for that exact file.
    pub elo: Option<String>,
    /// The player's window (ADR-088): earlier patches' games pooled (the default) or the
    /// patch's own; data without it gets the other, and the plan's `window` says which.
    /// Without a `patch` or `region`, as `elo`; with one, the exact file in this window.
    pub window: Option<Window>,
    /// The enemy champions picked so far: boots are chosen against their damage (ADR-074).
    #[serde(default)]
    pub enemies: Vec<i64>,
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
    /// What the block's list draws from: the slot's options with at least 2% of its games, in
    /// Stronk's order (ADR-070).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub order: Vec<i64>,
    /// Items in the slot's block, its own first: four, six for the late slot (ADR-067).
    pub block: usize,
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
    /// The first four level-ups (ADR-085).
    pub skill_levels: Ranked<Vec<String>>,
    /// The max order (ADR-085).
    pub skill_max: Ranked<Vec<String>>,
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

/// A start's or first components' choice (ADR-071, ADR-072), and what the import writes for it:
/// what is most often bought with those items, supplies included, repeated as bought.
#[derive(Clone, Debug, PartialEq, Serialize, schemars::JsonSchema)]
pub struct PurchaseChoice {
    #[serde(flatten)]
    pub choice: Choice<Vec<i64>>,
    pub buy: Vec<i64>,
}

/// The boots' choice (ADR-073), the other boots their block lists after it, and the enemy damage
/// they were chosen against (ADR-074): None, over every game, as fewer than three enemies are
/// known or the data has no boots for that kind of team.
#[derive(Clone, Debug, PartialEq, Serialize, schemars::JsonSchema)]
pub struct BootsChoice {
    #[serde(flatten)]
    pub choice: Choice<i64>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub then: Vec<i64>,
    pub against: Option<Against>,
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
    /// The games' window (ADR-088), and the patches they come from, oldest first.
    pub window: Window,
    pub patches: Vec<String>,
    pub runes: Option<Choice<Page>>,
    /// D then F, in the pair's usual order; the import moves Flash to the player's key.
    pub spells: Option<Choice<(i64, i64)>>,
    /// The start (ADR-071): its items without supplies, smallest id first.
    pub start: Option<PurchaseChoice>,
    /// The first components (ADR-072), as the start.
    pub components: Option<PurchaseChoice>,
    /// The upgraded boots (ADR-073).
    pub boots: Option<BootsChoice>,
    pub items: Vec<SlotChoice>,
    /// The first four level-ups, keys "Q" to "R" (ADR-085). The client can't import them: the
    /// item set's first block names them.
    pub skill_levels: Option<Choice<Vec<String>>>,
    /// The max order, the basic abilities from maxed first to last (ADR-085), named the same way.
    pub skill_max: Option<Choice<Vec<String>>>,
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
    let build = if params.patch.is_none() && params.region.is_none() {
        build_get::fetch_preferring(
            ctx,
            &params.champion,
            params.role,
            params.elo.as_deref(),
            params.window,
        )?
    } else {
        build_get::fetch(
            ctx,
            &params.champion,
            params.role,
            params.patch.as_deref(),
            params.region.as_deref(),
            params.elo.as_deref(),
            params.window.unwrap_or(Window::Patch),
        )?
    };
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
    let runes = page_candidates(build);
    let spells = spell_candidates(build);
    let candidates = item_candidates(build);
    let starts = purchase_candidates(&build.starts);
    let components = purchase_candidates(&build.first_components);
    let (boots, boots_against) = boots_candidates(build, against);
    let skill_levels = skill_candidates(&build.skill_levels);
    let skill_max = skill_candidates(&build.skill_max);
    let items: Vec<SlotChoice> = choose_items(&candidates)
        .into_iter()
        .map(|(slot, choice)| SlotChoice {
            slot,
            choice,
            then: Vec::new(),
            order: Vec::new(),
            block: 0,
        })
        .collect();
    // The page chosen by its keystone, which the pages' list marks (each page stands for its
    // keystone); then its rows' best bets, which the import writes and the rune rows mark.
    let rows = rune_row_candidates(&build.rune_choices);
    let keystone_choice = choose(&runes);
    let runes_choice = keystone_choice.clone().map(|c| with_row_bets(c, &rows));
    let spells_choice = choose(&spells);
    let start_choice = choose(&starts);
    let components_choice = choose(&components);
    let boots_choice = choose(&boots);
    let skill_levels_choice = choose(&skill_levels);
    let skill_max_choice = choose(&skill_max);
    let alternatives = Alternatives {
        runes: rank(&runes, chosen(&keystone_choice)),
        spells: rank(&spells, chosen(&spells_choice)),
        start: rank(&starts, chosen(&start_choice)),
        components: rank(&components, chosen(&components_choice)),
        boots: rank(&boots, chosen(&boots_choice)),
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
        rune_rows: rune_rows(rows, chosen(&runes_choice)),
        skill_levels: rank(&skill_levels, chosen(&skill_levels_choice)),
        skill_max: rank(&skill_max, chosen(&skill_max_choice)),
    };
    let purchase = |options: &[PurchaseOption], choice: Option<Choice<Vec<i64>>>| {
        choice.map(|c| PurchaseChoice {
            buy: purchase_buy(options, &c.value),
            choice: c,
        })
    };
    let mut plan = Plan {
        champion: build.champion.to_string(),
        role,
        patch: build.patch.to_string(),
        games: build.games,
        elo: build.elo.to_string(),
        region: build.region.to_string(),
        window: if build.patches.is_some() {
            Window::Pooled
        } else {
            Window::Patch
        },
        patches: build.patches.as_ref().map_or_else(
            || vec![build.patch.to_string()],
            |p| p.iter().map(|p| p.as_str().to_owned()).collect(),
        ),
        runes: runes_choice,
        spells: spells_choice,
        start: purchase(&build.starts, start_choice),
        components: purchase(&build.first_components, components_choice),
        boots: boots_choice.map(|choice| BootsChoice {
            choice,
            then: Vec::new(),
            against: boots_against,
        }),
        items,
        skill_levels: skill_levels_choice,
        skill_max: skill_max_choice,
        late_slot: build.late_slot.map(|s| s.get()),
        alternatives,
    };
    with_alternatives(&mut plan);
    plan
}

/// The value a choice takes, if any.
fn chosen<T>(choice: &Option<Choice<T>>) -> Option<&T> {
    choice.as_ref().map(|c| &c.value)
}

/// A published option as the rule reads it (ADR-043): its estimate, interval and flags.
fn candidate<T>(
    value: T,
    id: i64,
    played: u64,
    wpa: Option<f64>,
    ci: Option<&Interval>,
    flags: &[Flag],
    comparison: Option<select::Comparison>,
) -> Candidate<T> {
    Candidate {
        value,
        id,
        played,
        wpa,
        ci: ci.map(interval),
        too_few: too_few(flags),
        low_overlap: flags.contains(&Flag::LowOverlap),
        unclear: flags.contains(&Flag::NoClearDifference),
        fragile: flags.contains(&Flag::Fragile),
        comparison,
        changed_in: None,
    }
}

/// `candidate` for an item or purchase changed in `patch` (ADR-088).
fn changed<T>(candidate: Candidate<T>, patch: Option<&ContractPatch>) -> Candidate<T> {
    Candidate {
        changed_in: patch.map(|p| p.as_str().to_owned()),
        ..candidate
    }
}

/// The published pages, each standing for its keystone.
fn page_candidates(build: &Build) -> Vec<Candidate<Page>> {
    build
        .runes
        .iter()
        .map(|o| {
            let page = Page {
                primary_style: to_i64(o.page.primary_style),
                sub_style: to_i64(o.page.sub_style),
                perks: o.page.perks.iter().map(|p| to_i64(*p)).collect(),
            };
            let keystone = o.page.perks.first().map_or(0, |k| to_i64(*k));
            // The estimate is the keystone's: every game with it, not only those with exactly
            // this page (`games`), which splits a keystone across its page variants.
            let comparison = o.comparison.as_ref().map(compared);
            candidate(
                page,
                keystone,
                o.n,
                o.wpa,
                o.ci.as_ref(),
                &o.flags,
                comparison,
            )
        })
        .collect()
}

/// A skill order's keys as players read them.
pub fn keys(skills: &[Skill]) -> Vec<String> {
    skills.iter().map(ToString::to_string).collect()
}

/// The published first levels or max orders (ADR-085), each compared with the most played.
fn skill_candidates(options: &[SkillOption]) -> Vec<Candidate<Vec<String>>> {
    options
        .iter()
        .map(|o| {
            let value = keys(&o.skills);
            let id = skills::id(&value);
            let comparison = o.comparison.as_ref().map(skill_compared);
            candidate(
                value,
                id,
                o.games,
                o.wpa,
                o.ci.as_ref(),
                &o.flags,
                comparison,
            )
        })
        .collect()
}

fn skill_compared(c: &SkillComparison) -> select::Comparison {
    select::Comparison {
        versus: skills::id(&keys(&c.versus)),
        wpa: c.wpa,
        ci: c.ci.as_ref().map(interval),
    }
}

/// The published spell pairs, each compared with the most played pair when the data has their
/// estimates (ADR-083); without, the popular pair.
fn spell_candidates(build: &Build) -> Vec<Candidate<(i64, i64)>> {
    build
        .spells
        .iter()
        .map(|o| {
            let [d, f] = o.spells.map(|s| to_i64(s.get()));
            let id = spells::pair_id(d, f);
            let played = o.games.unwrap_or(o.n);
            let comparison = o.comparison.as_ref().map(spell_compared);
            candidate(
                (d, f),
                id,
                played,
                o.wpa,
                o.ci.as_ref(),
                &o.flags,
                comparison,
            )
        })
        .collect()
}

/// Each item slot's published items, by slot.
fn item_candidates(build: &Build) -> Vec<(u64, Vec<Candidate<i64>>)> {
    let mut slots: Vec<u64> = build.items.iter().map(|o| o.slot.get()).collect();
    slots.sort_unstable();
    slots.dedup();
    slots
        .into_iter()
        .map(|slot| {
            let candidates = build
                .items
                .iter()
                .filter(|o| o.slot.get() == slot)
                .map(|o| {
                    let item = to_i64(o.item.get());
                    let played = o.picks.unwrap_or(o.n);
                    let comparison = o.comparison.as_ref().map(compared);
                    let found = candidate(
                        item,
                        item,
                        played,
                        o.wpa,
                        o.ci.as_ref(),
                        &o.flags,
                        comparison,
                    );
                    changed(found, o.changed_in.as_ref())
                })
                .collect();
            (slot, candidates)
        })
        .collect()
}

/// The boots against `against` if the data has them, else over every game (ADR-074), and the
/// enemy damage they were estimated against.
fn boots_candidates(
    build: &Build,
    against: Option<Against>,
) -> (Vec<Candidate<i64>>, Option<Against>) {
    let profile = |o: &BootsOption| o.against.map(against_of);
    let used = against.filter(|a| build.boots.iter().any(|o| profile(o) == Some(*a)));
    let boots = build
        .boots
        .iter()
        .filter(|o| profile(o) == used)
        .map(|o| {
            let item = to_i64(o.item.get());
            let comparison = o.comparison.as_ref().map(compared);
            let found = candidate(
                item,
                item,
                o.games,
                o.wpa,
                o.ci.as_ref(),
                &o.flags,
                comparison,
            );
            changed(found, o.changed_in.as_ref())
        })
        .collect();
    (boots, used)
}

/// The data's enemy profile as the domain's.
fn against_of(against: BootsOptionAgainst) -> Against {
    match against {
        BootsOptionAgainst::Physical => Against::Physical,
        BootsOptionAgainst::Mixed => Against::Mixed,
        BootsOptionAgainst::Magic => Against::Magic,
    }
}

/// Each slot's block (ADR-069): its order, the options with at least
/// [`stronk_domain::item_set::BLOCK_MIN_SHARE`] of its games in Stronk's order (its choice, then
/// its judgement, ADR-070), and its size ([`block_size`], ADR-067); `then`, the first of that
/// order no slot takes. The block starts with the slot's item, the player's pick when they made
/// one: a pick overrules Stronk, which then comes next. Called again when the player's picks
/// change the items; the app fills the late block's list from `order` and `block` the same way.
pub fn with_alternatives(plan: &mut Plan) {
    let taken: Vec<i64> = plan.items.iter().map(|s| s.choice.value).collect();
    for s in &mut plan.items {
        s.block = block_size(plan.late_slot == Some(s.slot));
        s.order = plan
            .alternatives
            .items
            .iter()
            .find(|a| a.slot == s.slot)
            .map(|a| block_order(&a.ranked))
            .unwrap_or_default();
        s.then = block_others(&s.order, &taken, s.block);
    }
    // Boots are their own block (ADR-073): the other boots, in the same order.
    let order = block_order(&plan.alternatives.boots);
    if let Some(boots) = plan.boots.as_mut() {
        boots.then = block_others(&order, &[boots.choice.value], block_size(false));
    }
}

/// The published rune choices as candidates, by row in row order (primary rows, then pairs,
/// then shards).
fn rune_row_candidates(choices: &[RuneChoice]) -> Vec<(RowKey, Vec<Candidate<Vec<i64>>>)> {
    let mut keys: Vec<RowKey> = choices.iter().map(row_of).collect();
    keys.sort_unstable();
    keys.dedup();
    keys.into_iter()
        .map(|key| {
            let candidates = choices
                .iter()
                .filter(|c| row_of(c) == key)
                .map(|c| {
                    let value: Vec<i64> = c.perks.iter().map(|p| to_i64(*p)).collect();
                    let (id, played) = (perks_id(&value), c.games.unwrap_or(c.n));
                    let comparison = c.comparison.as_ref().map(row_compared);
                    candidate(
                        value,
                        id,
                        played,
                        c.wpa,
                        c.ci.as_ref(),
                        &c.flags,
                        comparison,
                    )
                })
                .collect();
            (key, candidates)
        })
        .collect()
}

/// Each rune row ranked by the same rule as every slot; the row's choice in `page` is marked
/// chosen.
fn rune_rows(rows: Vec<(RowKey, Vec<Candidate<Vec<i64>>>)>, page: Option<&Page>) -> Vec<RuneRow> {
    rows.into_iter()
        .map(|(key, candidates)| {
            let chosen = page.and_then(|p| in_page(p, key));
            RuneRow {
                kind: key.kind,
                style: key.style,
                row: key.row,
                ranked: rank(&candidates, chosen.as_ref()),
            }
        })
        .collect()
}

fn row_of(c: &RuneChoice) -> RowKey {
    let kind = match c.kind {
        RuneChoiceKind::Primary => RowKind::Primary,
        RuneChoiceKind::Secondary => RowKind::Secondary,
        RuneChoiceKind::Shard => RowKind::Shard,
    };
    RowKey {
        kind,
        style: c.style.map(to_i64),
        row: c.row.map(|r| r.get()),
    }
}

/// Published purchases (starts, first components) as candidates (ADR-071, ADR-072).
fn purchase_candidates(options: &[PurchaseOption]) -> Vec<Candidate<Vec<i64>>> {
    options
        .iter()
        .map(|o| {
            let value = purchase_items(&o.items);
            let id = purchase_id(&value);
            let comparison = o.comparison.as_ref().map(purchase_compared);
            let found = candidate(
                value,
                id,
                o.games,
                o.wpa,
                o.ci.as_ref(),
                &o.flags,
                comparison,
            );
            changed(found, o.changed_in.as_ref())
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

fn purchase_compared(c: &PurchaseComparison) -> select::Comparison {
    select::Comparison {
        versus: purchase_id(&purchase_items(&c.versus)),
        wpa: c.wpa,
        ci: c.ci.as_ref().map(interval),
    }
}

fn spell_compared(c: &SpellComparison) -> select::Comparison {
    let [a, b] = c.versus.map(|s| to_i64(s.get()));
    select::Comparison {
        versus: spells::pair_id(a, b),
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
    use stronk_domain::select::Label;

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

    /// A max order in a test build: keys, games, comparison with the most played as (wpa, low,
    /// high), clear.
    pub(crate) type MaxOrder<'a> = (&'a str, u64, Option<(f64, f64, f64)>, bool);

    /// A build with these first levels (keys, games) and max orders.
    pub(crate) fn with_skills(levels: &[(&str, u64)], max: &[MaxOrder]) -> Build {
        fn order(keys: &str) -> Vec<&str> {
            keys.split(' ').collect()
        }
        let levels: Vec<serde_json::Value> = levels
            .iter()
            .map(|(keys, games)| {
                serde_json::json!({"skills": order(keys), "games": games,
                "n": games, "wpa": 0.0, "ci": [-0.01, 0.01], "flags": []})
            })
            .collect();
        let popular = max.first().map(|m| order(m.0)).unwrap_or_default();
        let max: Vec<serde_json::Value> = max
            .iter()
            .map(|(keys, games, vs, clear)| {
                let flags: &[&str] = if *clear {
                    &[]
                } else {
                    &["no_clear_difference"]
                };
                let mut o = serde_json::json!({"skills": order(keys), "games": games, "n": games,
                    "wpa": 0.0, "ci": [-0.01, 0.01], "flags": flags});
                if let Some((wpa, low, high)) = vs {
                    o["comparison"] = serde_json::json!({"versus": popular, "wpa": wpa,
                        "ci": [low, high], "q": 0.01});
                }
                o
            })
            .collect();
        serde_json::from_value(serde_json::json!({
            "schemaVersion": 1, "patch": "16.21", "region": "all", "elo": "master_plus",
            "champion": "LeeSin", "role": "JUNGLE", "games": 3000, "runes": [], "items": [],
            "spells": [], "skillLevels": levels, "skillMax": max
        }))
        .unwrap()
    }

    #[test]
    fn the_skill_order_is_the_most_played_unless_another_is_ahead_of_it() {
        // Q W E Q first; Q > E > W maxed most, Q > W > E a best bet against it (ADR-085).
        let keys = |s: &str| s.split(' ').map(str::to_owned).collect::<Vec<_>>();
        let build = with_skills(
            &[("Q W E Q", 2000), ("W Q E Q", 600)],
            &[
                ("Q E W", 1800, None, false),
                ("Q W E", 900, Some((0.02, 0.012, 0.028)), false),
                ("E Q W", 100, Some((-0.03, -0.06, 0.0)), false),
            ],
        );
        let plan = plan(&build, Role::Jungle, None);
        let levels = plan.skill_levels.unwrap();
        assert_eq!(
            (levels.value, levels.label),
            (keys("Q W E Q"), Label::Popular)
        );
        let max = plan.skill_max.unwrap();
        assert_eq!(max.value, keys("Q W E"));
        assert!(matches!(max.label, Label::BestBet { .. }));
        assert_eq!(plan.alternatives.skill_max.rows.len(), 3);
        let none = plan_of_nothing();
        assert!(none.skill_levels.is_none() && none.skill_max.is_none());
    }

    fn plan_of_nothing() -> Plan {
        plan(&with_items(&[]), Role::Jungle, None)
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
    fn a_spell_pair_clearly_better_than_the_most_played_replaces_it() {
        // Smite and Flash most played; Ghost clearly better against it (ADR-083); Ignite
        // clearly worse; Exhaust not measured against it.
        let pair = |spells: [i64; 2], games: u64, flags: &[&str], vs: Option<(f64, f64, f64)>| {
            let mut o = serde_json::json!({"spells": spells, "games": games, "n": games,
                                           "wpa": 0.0, "ci": [-0.01, 0.01], "flags": flags});
            if let Some((wpa, low, high)) = vs {
                o["comparison"] = serde_json::json!({"versus": [4, 11], "wpa": wpa, "ci": [low, high], "q": 0.01});
            }
            o
        };
        let build = |spells: Vec<serde_json::Value>| -> Build {
            serde_json::from_value(serde_json::json!({
                "schemaVersion": 1, "patch": "16.21", "region": "all", "elo": "master_plus",
                "champion": "LeeSin", "role": "JUNGLE", "games": 3000, "runes": [], "items": [],
                "spells": spells
            }))
            .unwrap()
        };
        let smite_flash = pair([11, 4], 2400, &[], None);
        let ghost = pair([6, 11], 400, &[], Some((0.03, 0.01, 0.05)));
        let ignite = pair([11, 14], 150, &[], Some((-0.04, -0.06, -0.02)));
        let exhaust = pair([3, 11], 50, &["low_sample"], None);
        let chosen = |b: &Build| plan(b, Role::Jungle, None).spells.map(|c| c.value);
        let all = build(vec![
            smite_flash.clone(),
            ghost,
            ignite.clone(),
            exhaust.clone(),
        ]);
        assert_eq!(chosen(&all), Some((6, 11)));
        let without = build(vec![smite_flash, ignite, exhaust]);
        assert_eq!(chosen(&without), Some((11, 4)));
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
        // Lee Sin jungle: Cut Down against Coup de Grace, +2.7 likely between 0.0 and +5.6, as
        // published; the rule itself is the domain's (`runes::with_row_bets`).
        let rows = rune_row_candidates(&choices(serde_json::json!([
            {"kind": "shard", "row": 1, "perks": [5005], "games": 3765, "n": 3765,
             "wpa": -0.013, "ci": [-0.03, 0.004], "flags": ["no_clear_difference"]},
            {"kind": "primary", "style": 8000, "row": 3, "perks": [8014], "games": 2194, "n": 2194,
             "wpa": -0.024, "ci": [-0.041, -0.008], "flags": ["no_clear_difference"]},
            {"kind": "primary", "style": 8000, "row": 3, "perks": [8017], "games": 1704, "n": 1704,
             "wpa": 0.019, "ci": [0.002, 0.036], "flags": ["no_clear_difference"],
             "comparison": {"versus": [8014], "wpa": 0.027, "ci": [-0.00005, 0.05555], "q": 0.61}}
        ])));
        // Primary rows come before shards, each row's options with their comparison.
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].0.kind, RowKind::Primary);
        let cut_down = &rows[0].1[1];
        assert_eq!(
            cut_down.comparison.map(|k| (k.versus, k.wpa)),
            Some((8014, 0.027))
        );
        let page = Page {
            primary_style: 8000,
            sub_style: 8300,
            perks: vec![8010, 9111, 9104, 8014, 8347, 8304, 5005, 5008, 5001],
        };
        let chosen = with_row_bets(
            Choice {
                value: page.clone(),
                label: select::Label::Popular,
            },
            &rows,
        );
        assert_eq!(chosen.value.perks[3], 8017);
        // The rune rows mark the page's own runes.
        let ranked = rune_rows(rows, Some(&chosen.value));
        assert!(
            ranked[0]
                .ranked
                .rows
                .iter()
                .any(|r| r.chosen && r.value == [8017])
        );
    }
}
