//! `build.import`: writes the plan (`build.plan`) for the current champion select into the
//! client: Stronk's own rune page, Stronk's own item set, and the summoner spells with Flash
//! on the player's key (ADR-043). The player's pages and item sets are never changed.

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use stronk_domain::Role;
use stronk_domain::select::{Choice, Label, PREFIX, arrange_spells, is_ours, plan_rune_page};

use crate::commands::build_get;
use crate::commands::build_plan::{Plan, plan};
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
    Ok(Imported {
        runes: runes(client, &plan)?,
        item_set: item_set(client, &plan, session.champion_id)?,
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
        let reason = "every rune page is yours: free one to let Stronk add its own".into();
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

fn item_set(
    client: &dyn LeagueClient,
    plan: &Plan,
    champion_id: i64,
) -> Result<Outcome, CommandError> {
    let Some(best) = plan
        .items
        .iter()
        .map(|s| &s.choice.label)
        .find(|l| matches!(l, Label::ClearlyBetter { .. }))
    else {
        return write_set(client, plan, champion_id, Label::Popular);
    };
    write_set(client, plan, champion_id, *best)
}

fn write_set(
    client: &dyn LeagueClient,
    plan: &Plan,
    champion_id: i64,
    label: Label,
) -> Result<Outcome, CommandError> {
    if plan.items.is_empty() {
        return Ok(Outcome::Skipped {
            reason: "no items published".into(),
        });
    }
    let name = title(plan);
    let document = merged_item_sets(client.item_sets()?, item_set_json(plan, &name, champion_id))?;
    client.save_item_sets(&document)?;
    Ok(Outcome::Imported { name, label })
}

/// Stronk's set: one block per slot, named with the slot and why the item was chosen.
fn item_set_json(plan: &Plan, title: &str, champion_id: i64) -> Value {
    let blocks: Vec<Value> = plan
        .items
        .iter()
        .map(|s| {
            let why = match s.choice.label {
                Label::Popular => "Popular".to_owned(),
                Label::ClearlyBetter { wpa } => format!("Clearly better, {:+.1}% win", wpa * 100.0),
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

/// The client's document with Stronk's sets replaced by `ours`; every other set, and every
/// other field, exactly as read.
fn merged_item_sets(mut document: Value, ours: Value) -> Result<Value, CommandError> {
    let invalid = || {
        CommandError::new(
            ErrorCode::InvalidData,
            "the client's item sets have no `itemSets` list",
        )
    };
    let sets = document
        .get_mut("itemSets")
        .and_then(Value::as_array_mut)
        .ok_or_else(invalid)?;
    sets.retain(|set| {
        !set.get("title")
            .and_then(Value::as_str)
            .is_some_and(is_ours)
    });
    sets.push(ours);
    Ok(document)
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

    #[test]
    fn merging_keeps_every_other_set_and_field() {
        let theirs = json!({"title": "My Jinx", "blocks": [1]});
        let old_ours = json!({"title": "Stronk: Jinx BOTTOM"});
        let document =
            json!({"accountId": 1, "timestamp": 5, "itemSets": [theirs.clone(), old_ours]});
        let merged = merged_item_sets(document, json!({"title": "Stronk: Ahri MIDDLE"})).unwrap();
        assert_eq!(merged["accountId"], 1);
        assert_eq!(
            merged["itemSets"],
            json!([theirs, {"title": "Stronk: Ahri MIDDLE"}])
        );
        assert!(merged_item_sets(json!({}), json!({})).is_err());
    }
}
