//! `build.import`: writes the plan (`build.plan`) for the current champion select into the
//! client: Stronk's own rune page, Stronk's own item set, and the summoner spells with Flash
//! on the player's key (ADR-043). The player's pages and item sets are never changed.

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use stronk_domain::Role;
use stronk_domain::select::{Choice, Label, PREFIX, arrange_spells, plan_rune_page};

use crate::commands::build_get;
use crate::commands::build_plan::{Plan, plan};
use crate::item_sets::Document;
use crate::ports::{LeagueClient, NewRunePage};
use crate::registry::Command;
use crate::{CommandError, Context, ErrorCode};

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Params {}

/// What happened to one part of the import.
#[derive(Clone, Debug, PartialEq, Serialize)]
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

#[derive(Clone, Debug, PartialEq, Serialize)]
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

fn run(ctx: &Context, _: Params) -> Result<Imported, CommandError> {
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
    let plan = plan(&build, role);
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
    let label = plan
        .items
        .iter()
        .map(|s| s.choice.label)
        .find(|l| matches!(l, Label::ClearlyBetter { .. }))
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
                Label::ClearlyBetter { wpa, .. } => format!("Clearly better, {:+.1}% win", wpa * 100.0),
            };
            json!({"type": format!("Item {} · {why}", s.slot), "items": [{"id": s.choice.value.to_string(), "count": 1}]})
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
