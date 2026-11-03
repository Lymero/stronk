//! `build.import`: writes the plan (`build.plan`) for the current champion select into the
//! client: Stronk's own rune page, Stronk's own item set, and the summoner spells with Flash
//! on the player's key (ADR-043). The player's pages and item sets are never changed. The
//! player can pick other published options instead of Stronk's (ADR-050), and build any rune
//! page the client's own trees allow (ADR-059). An import can write only some parts: on
//! lock-in the app writes the item set alone unless the player asked for everything (ADR-082).
//! The skill order, which the client can't import, names the item set's first block (ADR-085).

use serde::{Deserialize, Serialize};
use stronk_contracts::build_v1::{Build, PurchaseOption, SkillOption};
use stronk_domain::Role;
use stronk_domain::item_set::purchase_items;
use stronk_domain::owned::{PREFIX, plan_rune_page};
use stronk_domain::runes::{Page, valid_page};
use stronk_domain::select::{Choice, Label};
use stronk_domain::skills;
use stronk_domain::spells::arrange_spells;

use crate::commands::build_get;
use crate::commands::build_plan::{
    BootsChoice, Plan, PurchaseChoice, SlotChoice, against_for, keys, plan, purchase_buy,
    with_alternatives,
};
use crate::item_sets::{Block, Document, ItemSet};
use crate::ports::{LeagueClient, NewRunePage};
use crate::registry::Command;
use crate::{CommandError, Context, ErrorCode};

/// The player's picks: published spells and items, and any rune page the client's trees allow;
/// Stronk's choice where none is given.
#[derive(Debug, Default, Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "ImportParams")]
pub struct Params {
    #[serde(default)]
    pub runes: Option<Page>,
    /// The pair in any order; Flash still goes on the player's key.
    #[serde(default)]
    pub spells: Option<(i64, i64)>,
    #[serde(default)]
    pub items: Vec<ItemPick>,
    /// A published start's items, in any order (ADR-071).
    #[serde(default)]
    pub start: Option<Vec<i64>>,
    /// Published first components, in any order (ADR-072).
    #[serde(default)]
    pub components: Option<Vec<i64>>,
    /// Published upgraded boots (ADR-073).
    #[serde(default)]
    pub boots: Option<i64>,
    /// Published first levels, keys "Q" to "R" (ADR-085).
    #[serde(default)]
    pub skill_levels: Option<Vec<String>>,
    /// A published max order, the same way (ADR-085).
    #[serde(default)]
    pub skill_max: Option<Vec<String>>,
    /// The elo bracket of the plan shown (ADR-078); the closest one with a build when it has
    /// none (ADR-079).
    #[serde(default)]
    pub elo: Option<String>,
    /// The parts to write, all of them when absent (ADR-082); the others are left as they are.
    #[serde(default)]
    pub parts: Option<Vec<Part>>,
}

/// A part of the import, written on its own or with the others.
#[derive(Clone, Copy, Debug, PartialEq, Deserialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Part {
    Runes,
    ItemSet,
    Spells,
}

#[derive(Debug, Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ItemPick {
    pub slot: u64,
    pub item: i64,
}

/// What happened to one part of the import.
#[derive(Clone, Debug, PartialEq, Serialize, schemars::JsonSchema)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum Outcome {
    Imported {
        name: String,
        #[serde(flatten)]
        label: Label,
    },
    Skipped {
        reason: String,
    },
    /// Not among the parts asked for: nothing was read or written.
    NotAsked,
}

#[derive(Clone, Debug, PartialEq, Serialize, schemars::JsonSchema)]
pub struct Imported {
    pub champion: String,
    pub role: Role,
    pub runes: Outcome,
    pub item_set: Outcome,
    /// Where the player's item sets were saved before Stronk wrote its own.
    pub item_set_backup: Option<String>,
    pub spells: Outcome,
}

pub fn command() -> Command {
    Command::new(
        "build.import",
        "Import the plan for the current champion select",
        run,
    )
}

fn run(ctx: &Context, params: Params) -> Result<Imported, CommandError> {
    let client = ctx.client.as_ref();
    let not_ready = |what: &str| {
        CommandError::new(ErrorCode::InvalidParams, format!("no {what} to import for"))
    };
    let session = client
        .champ_select()?
        .ok_or_else(|| not_ready("champion select"))?;
    let role = session.role.ok_or_else(|| not_ready("assigned role"))?;
    if session.champion_id <= 0 {
        return Err(not_ready("champion"));
    }
    let champion = client.champion_key(session.champion_id)?;
    let build = build_get::fetch_preferring(ctx, &champion, role, params.elo.as_deref())?;
    let against = against_for(ctx, &build, &session.enemies);
    let plan = with_picks(plan(&build, role, against), &build, &params, client)?;
    let asked = |part| {
        params
            .parts
            .as_ref()
            .is_none_or(|parts| parts.contains(&part))
    };
    let runes = if asked(Part::Runes) {
        runes(client, &plan)?
    } else {
        Outcome::NotAsked
    };
    let (item_set, item_set_backup) = if asked(Part::ItemSet) {
        item_set(ctx, &plan, session.champion_id)
    } else {
        (Outcome::NotAsked, None)
    };
    let spells = if asked(Part::Spells) {
        spells(client, &plan, session.spells.unwrap_or((0, 0)))?
    } else {
        Outcome::NotAsked
    };
    Ok(Imported {
        runes,
        item_set,
        item_set_backup,
        spells,
        champion,
        role,
    })
}

/// The plan with the player's picks in place of Stronk's choices. A pick that isn't published,
/// or a rune page the client's trees don't allow, is refused before anything is written; a pick
/// equal to Stronk's choice keeps its label.
fn with_picks(
    mut plan: Plan,
    build: &Build,
    params: &Params,
    client: &dyn LeagueClient,
) -> Result<Plan, CommandError> {
    if let Some(page) = &params.runes {
        pick_runes(&mut plan, build, page, client)?;
    }
    if let Some(pair) = params.spells {
        pick_spells(&mut plan, build, pair)?;
    }
    pick_items(&mut plan, build, &params.items)?;
    if let Some(items) = &params.start {
        pick_purchase(&mut plan.start, &build.starts, items, "start")?;
    }
    if let Some(items) = &params.components {
        pick_purchase(
            &mut plan.components,
            &build.first_components,
            items,
            "components",
        )?;
    }
    if let Some(boots) = params.boots {
        pick_boots(&mut plan, build, boots)?;
    }
    if let Some(order) = &params.skill_levels {
        pick_skills(
            &mut plan.skill_levels,
            &build.skill_levels,
            order,
            "first levels",
        )?;
    }
    if let Some(order) = &params.skill_max {
        pick_skills(&mut plan.skill_max, &build.skill_max, order, "max order")?;
    }
    with_alternatives(&mut plan);
    Ok(plan)
}

fn invalid(what: String) -> CommandError {
    CommandError::new(ErrorCode::InvalidParams, what)
}

/// Ids are small positive integers; anything beyond i64 can't match a real id.
fn id(v: u64) -> i64 {
    i64::try_from(v).unwrap_or(-1)
}

/// A published page, or one the player built rune by rune that the client's trees allow.
fn pick_runes(
    plan: &mut Plan,
    build: &Build,
    page: &Page,
    client: &dyn LeagueClient,
) -> Result<(), CommandError> {
    let published = build.runes.iter().any(|o| {
        id(o.page.primary_style) == page.primary_style
            && id(o.page.sub_style) == page.sub_style
            && o.page
                .perks
                .iter()
                .map(|p| id(*p))
                .eq(page.perks.iter().copied())
    });
    if !published {
        // A page the player built rune by rune: checked against the client's own layout.
        let names = client.game_names()?;
        valid_page(
            page.primary_style,
            page.sub_style,
            &page.perks,
            &names.rune_trees,
            &names.shard_rows,
        )
        .map_err(|why| invalid(format!("runes: {why}")))?;
    }
    if plan.runes.as_ref().map(|c| &c.value) != Some(page) {
        plan.runes = Some(picked(page.clone()));
    }
    Ok(())
}

/// A published spell pair, in either order.
fn pick_spells(plan: &mut Plan, build: &Build, (a, b): (i64, i64)) -> Result<(), CommandError> {
    let same = |(c, d): (i64, i64)| (c, d) == (a, b) || (d, c) == (a, b);
    let published = build.spells.iter().any(|o| {
        let [d, f] = o.spells.map(|s| id(s.get()));
        same((d, f))
    });
    if !published {
        return Err(invalid(format!(
            "spells: {a} and {b} are not a published pair"
        )));
    }
    if !plan.spells.as_ref().is_some_and(|c| same(c.value)) {
        plan.spells = Some(picked((a, b)));
    }
    Ok(())
}

/// Published items, one per slot.
fn pick_items(plan: &mut Plan, build: &Build, picks: &[ItemPick]) -> Result<(), CommandError> {
    for (i, pick) in picks.iter().enumerate() {
        let (slot, item) = (pick.slot, pick.item);
        if picks.iter().take(i).any(|p| p.slot == slot) {
            return Err(invalid(format!("items: slot {slot} picked twice")));
        }
        if !build
            .items
            .iter()
            .any(|o| o.slot.get() == slot && id(o.item.get()) == item)
        {
            return Err(invalid(format!(
                "items: {item} is not published for slot {slot}"
            )));
        }
        match plan.items.iter_mut().find(|s| s.slot == slot) {
            Some(s) if s.choice.value == item => {}
            Some(s) => s.choice = picked(item),
            None => plan.items.push(SlotChoice {
                slot,
                choice: picked(item),
                then: Vec::new(),
                order: Vec::new(),
                block: 0,
            }),
        }
    }
    plan.items.sort_by_key(|s| s.slot);
    Ok(())
}

/// A published start or first components (ADR-071, ADR-072), its items in any order, with what
/// is most often bought with them.
fn pick_purchase(
    choice: &mut Option<PurchaseChoice>,
    options: &[PurchaseOption],
    items: &[i64],
    what: &str,
) -> Result<(), CommandError> {
    let mut items = items.to_vec();
    items.sort_unstable();
    items.dedup();
    if !options.iter().any(|o| purchase_items(&o.items) == items) {
        return Err(invalid(format!("{what}: {items:?} are not published")));
    }
    if choice.as_ref().map(|c| &c.choice.value) != Some(&items) {
        let buy = purchase_buy(options, &items);
        *choice = Some(PurchaseChoice {
            choice: picked(items),
            buy,
        });
    }
    Ok(())
}

/// Published boots (ADR-073), whichever enemy damage they were estimated against.
fn pick_boots(plan: &mut Plan, build: &Build, boots: i64) -> Result<(), CommandError> {
    if !build.boots.iter().any(|o| id(o.item.get()) == boots) {
        return Err(invalid(format!("boots: {boots} are not published")));
    }
    if plan.boots.as_ref().map(|b| b.choice.value) != Some(boots) {
        let against = plan.boots.as_ref().and_then(|b| b.against);
        plan.boots = Some(BootsChoice {
            choice: picked(boots),
            then: Vec::new(),
            against,
        });
    }
    Ok(())
}

/// A published first levels or max order (ADR-085), its keys in order.
fn pick_skills(
    choice: &mut Option<Choice<Vec<String>>>,
    options: &[SkillOption],
    order: &[String],
    what: &str,
) -> Result<(), CommandError> {
    if !options.iter().any(|o| keys(&o.skills) == order) {
        return Err(invalid(format!("{what}: {order:?} is not published")));
    }
    if choice.as_ref().map(|c| c.value.as_slice()) != Some(order) {
        *choice = Some(picked(order.to_vec()));
    }
    Ok(())
}

fn picked<T>(value: T) -> Choice<T> {
    Choice {
        value,
        label: Label::Picked,
    }
}

fn title(plan: &Plan) -> String {
    format!("{PREFIX}{} {}", plan.champion, plan.role.as_str())
}

fn runes(client: &dyn LeagueClient, plan: &Plan) -> Result<Outcome, CommandError> {
    let Some(Choice { value: page, label }) = &plan.runes else {
        return Ok(Outcome::Skipped {
            reason: "no rune page published".into(),
        });
    };
    let Some(room) = plan_rune_page(&client.rune_pages()?, client.rune_page_capacity()?) else {
        let reason =
            "all your rune pages are in use: delete one in the client, then import again".into();
        return Ok(Outcome::Skipped { reason });
    };
    for id in room.delete {
        client.delete_rune_page(id)?;
    }
    let name = title(plan);
    client.create_rune_page(&NewRunePage {
        name: name.clone(),
        primary_style: page.primary_style,
        sub_style: page.sub_style,
        perks: page.perks.clone(),
    })?;
    Ok(Outcome::Imported {
        name,
        label: *label,
    })
}

/// Stronk's item set, written only after the player's current sets were read and backed up;
/// any failure skips the item set and writes nothing (ADR-043).
fn item_set(ctx: &Context, plan: &Plan, champion_id: i64) -> (Outcome, Option<String>) {
    if plan.items.is_empty() {
        return (skipped("no items published"), None);
    }
    let labels = || plan.items.iter().map(|s| s.choice.label);
    let label = labels()
        .find(|l| matches!(l, Label::Picked))
        .or_else(|| labels().find(|l| matches!(l, Label::ClearlyBetter { .. })))
        .unwrap_or(Label::Popular);
    let name = item_set_title(ctx, plan, champion_id);
    let current = match ctx.client.item_sets() {
        Ok(current) => current,
        Err(e) => {
            return (
                skipped(&format!(
                    "could not read your item sets ({e}); nothing written"
                )),
                None,
            );
        }
    };
    let document = match Document::parse(&current, "the client's item sets") {
        Ok(parsed) => parsed.with_ours(&item_set_of(plan, name.clone(), champion_id).to_json()),
        Err(e) => return (skipped(&format!("{}; nothing written", e.message)), None),
    };
    let backup = match ctx.backups.save("item-sets", current.as_bytes()) {
        Ok(backup) => backup,
        Err(e) => {
            return (
                skipped(&format!(
                    "could not back up your item sets ({e}); nothing written"
                )),
                None,
            );
        }
    };
    match ctx.client.save_item_sets(&document) {
        Ok(()) => (Outcome::Imported { name, label }, Some(backup)),
        Err(e) => (
            skipped(&format!("writing the item set failed ({e})")),
            Some(backup),
        ),
    }
}

fn skipped(reason: &str) -> Outcome {
    Outcome::Skipped {
        reason: reason.to_owned(),
    }
}

/// Why a block's first item was chosen, as its name says it.
fn why(label: Label) -> String {
    match label {
        Label::Popular => "Popular".to_owned(),
        Label::Picked => "Your pick".to_owned(),
        Label::ClearlyBetter { wpa, .. } => format!("Clearly better, {:+.1}% win", wpa * 100.0),
        Label::BestBet { wpa, .. } => format!("Best bet, {:+.1}% win", wpa * 100.0),
    }
}

/// The item set's title as players read it: "Stronk: Lee Sin Jungle", the champion as the
/// client names it (its data key when the client's names can't be read).
fn item_set_title(ctx: &Context, plan: &Plan, champion_id: i64) -> String {
    let champion = ctx
        .client
        .game_names()
        .ok()
        .and_then(|n| n.champions.get(&champion_id).cloned())
        .unwrap_or_else(|| plan.champion.clone());
    format!("{PREFIX}{champion} {}", plan.role.label())
}

/// Stronk's set (the client lists it first): the start and the first components as bought,
/// supplies included (ADR-071, ADR-072), then one block per slot (boots after the first item,
/// when they're usually bought, ADR-073), named with the slot and why the item was chosen, its
/// choice first and then the slot's other items (ADR-069); the late slot's block is "Items 4+"
/// (ADR-067). The first block's name ends with the skill order (ADR-085): "Start: Popular ·
/// Q W E Q · max Q > E > W".
fn item_set_of(plan: &Plan, title: String, champion_id: i64) -> ItemSet {
    let named = |name: &str, label: Label, items: Vec<i64>| Block {
        name: format!("{name}: {}", why(label)),
        items,
    };
    let purchase = |name: &str, choice: &Option<PurchaseChoice>| {
        choice
            .as_ref()
            .map(|p| named(name, p.choice.label, p.buy.clone()))
    };
    let start = purchase("Start", &plan.start);
    let components = purchase("First components", &plan.components);
    let mut slots: Vec<Block> = plan
        .items
        .iter()
        .map(|s| {
            let name = if plan.late_slot == Some(s.slot) {
                format!("Items {}+", s.slot)
            } else {
                format!("Item {}", s.slot)
            };
            let items = std::iter::once(s.choice.value).chain(s.then.iter().copied());
            named(&name, s.choice.label, items.collect())
        })
        .collect();
    if let Some(b) = &plan.boots {
        let items = std::iter::once(b.choice.value).chain(b.then.iter().copied());
        slots.insert(
            slots.len().min(1),
            named("Boots", b.choice.label, items.collect()),
        );
    }
    let mut blocks: Vec<Block> = start.into_iter().chain(components).chain(slots).collect();
    let levels = plan.skill_levels.as_ref().map(|c| c.value.as_slice());
    let max = plan.skill_max.as_ref().map(|c| c.value.as_slice());
    if let (Some(first), Some(note)) = (blocks.first_mut(), skills::note(levels, max)) {
        first.name = format!("{} · {note}", first.name);
    }
    ItemSet {
        title,
        uid: format!(
            "stronk-{}-{}",
            plan.champion.to_lowercase(),
            plan.role.as_str().to_lowercase()
        ),
        champion_id,
        blocks,
    }
}

fn spells(
    client: &dyn LeagueClient,
    plan: &Plan,
    current: (i64, i64),
) -> Result<Outcome, CommandError> {
    let Some(Choice { value: pair, label }) = &plan.spells else {
        return Ok(Outcome::Skipped {
            reason: "no spells published".into(),
        });
    };
    let (d, f) = arrange_spells(*pair, current);
    client.set_spells((d, f))?;
    Ok(Outcome::Imported {
        name: format!("{d} {f}"),
        label: *label,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::commands::build_plan::tests::{with_items, with_skills};

    #[test]
    fn the_late_slots_block_names_it_and_lists_its_items() {
        let build = with_items(&[(1, 6698, 90), (4, 3026, 60), (4, 3156, 50)]);
        let set = item_set_of(
            &plan(&build, Role::Jungle, None),
            "Stronk: Lee Sin Jungle".into(),
            64,
        );
        assert_eq!(set.uid, "stronk-leesin-jungle");
        assert_eq!(set.blocks[0].name, "Item 1: Popular");
        assert_eq!(set.blocks[1].name, "Items 4+: Popular");
        assert_eq!(set.blocks[1].items, [3026, 3156]);
    }

    #[test]
    fn the_first_block_names_the_skill_order() {
        // The client can't import a skill order: the shop shows it this way (ADR-085).
        let mut build = with_items(&[(1, 6698, 90)]);
        let skills = with_skills(&[("Q W E Q", 90)], &[("Q E W", 80, None, false)]);
        build.skill_levels = skills.skill_levels;
        build.skill_max = skills.skill_max;
        let set = item_set_of(&plan(&build, Role::Jungle, None), "Stronk".into(), 64);
        assert_eq!(
            set.blocks[0].name,
            "Item 1: Popular · Q W E Q · max Q > E > W"
        );
        assert_eq!(set.blocks[0].items, [6698]);
    }

    #[test]
    fn only_a_published_skill_order_can_be_picked() {
        let build = with_skills(
            &[("Q W E Q", 90)],
            &[("Q E W", 80, None, false), ("Q W E", 20, None, false)],
        );
        let mut plan = plan(&build, Role::Jungle, None);
        let keys = |s: &str| s.split(' ').map(str::to_owned).collect::<Vec<_>>();
        pick_skills(
            &mut plan.skill_max,
            &build.skill_max,
            &keys("Q W E"),
            "max order",
        )
        .unwrap();
        let max = plan.skill_max.clone().unwrap();
        assert_eq!((max.value, max.label), (keys("Q W E"), Label::Picked));
        let refused = pick_skills(
            &mut plan.skill_max,
            &build.skill_max,
            &keys("W Q E"),
            "max order",
        );
        assert!(refused.is_err());
        // Picking Stronk's choice again keeps its label.
        let mut again = plan_for(&build);
        pick_skills(
            &mut again.skill_levels,
            &build.skill_levels,
            &keys("Q W E Q"),
            "first levels",
        )
        .unwrap();
        assert_eq!(again.skill_levels.unwrap().label, Label::Popular);
    }

    fn plan_for(build: &Build) -> Plan {
        plan(build, Role::Jungle, None)
    }
}
