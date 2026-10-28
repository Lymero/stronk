//! `build.import`: writes the plan (`build.plan`) for the current champion select into the
//! client: Stronk's own rune page, Stronk's own item set, and the summoner spells with Flash
//! on the player's key (ADR-043). The player's pages and item sets are never changed. The
//! player can pick other published options instead of Stronk's (ADR-050), and build any rune
//! page the client's own trees allow (ADR-059).

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use stronk_contracts::build_v1::Build;
use stronk_domain::Role;
use stronk_domain::select::{Choice, Label, PREFIX, arrange_spells, plan_rune_page, valid_page};

use crate::commands::build_get;
use crate::commands::build_plan::{Page, Plan, SlotChoice, plan};
use crate::item_sets::Document;
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
    let build = build_get::fetch(ctx, &champion, role, None, None, None)?;
    let plan = with_picks(plan(&build, role), &build, &params, client)?;
    let runes = runes(client, &plan)?;
    let (item_set, item_set_backup) = item_set(ctx, &plan, session.champion_id);
    Ok(Imported {
        runes,
        item_set,
        item_set_backup,
        spells: spells(client, &plan, session.spells.unwrap_or((0, 0)))?,
        champion,
        role,
    })
}

/// The plan with the player's picks in place of Stronk's choices. A spell pair or item that isn't
/// published, or a rune page the client's trees don't allow, is refused before anything is
/// written; a pick equal to Stronk's choice keeps its label.
fn with_picks(
    mut plan: Plan,
    build: &Build,
    params: &Params,
    client: &dyn LeagueClient,
) -> Result<Plan, CommandError> {
    let invalid = |what: String| CommandError::new(ErrorCode::InvalidParams, what);
    let id = |v: u64| i64::try_from(v).unwrap_or(-1);
    if let Some(page) = &params.runes {
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
    }
    if let Some((a, b)) = params.spells {
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
    }
    for (i, pick) in params.items.iter().enumerate() {
        if params.items.iter().take(i).any(|p| p.slot == pick.slot) {
            return Err(invalid(format!("items: slot {} picked twice", pick.slot)));
        }
        if !build
            .items
            .iter()
            .any(|o| o.slot.get() == pick.slot && id(o.item.get()) == pick.item)
        {
            let (slot, item) = (pick.slot, pick.item);
            return Err(invalid(format!(
                "items: {item} is not published for slot {slot}"
            )));
        }
        match plan.items.iter_mut().find(|s| s.slot == pick.slot) {
            Some(s) if s.choice.value == pick.item => {}
            Some(s) => s.choice = picked(pick.item),
            None => plan.items.push(SlotChoice {
                slot: pick.slot,
                choice: picked(pick.item),
            }),
        }
    }
    plan.items.sort_by_key(|s| s.slot);
    Ok(plan)
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
    let name = title(plan);
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
        Ok(parsed) => parsed.with_ours(&item_set_json(plan, &name, champion_id)),
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

/// Stronk's set: one block per slot, named with the slot and why the item was chosen.
fn item_set_json(plan: &Plan, title: &str, champion_id: i64) -> Value {
    let blocks: Vec<Value> = plan
        .items
        .iter()
        .map(|s| {
            let why = match s.choice.label {
                Label::Popular => "Popular".to_owned(),
                Label::Picked => "Your pick".to_owned(),
                Label::ClearlyBetter { wpa, .. } => format!("Clearly better, {:+.1}% win", wpa * 100.0),
            };
            json!({"type": format!("Item {}: {why}", s.slot), "items": [{"id": s.choice.value.to_string(), "count": 1}]})
        })
        .collect();
    json!({
        "title": title,
        "type": "custom",
        "map": "any",
        "mode": "any",
        "priority": false,
        "sortrank": 0,
        "associatedChampions": [champion_id],
        "associatedMaps": [],
        "blocks": blocks,
        "uid": format!("stronk-{}-{}", plan.champion.to_lowercase(), plan.role.as_str().to_lowercase()),
    })
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
