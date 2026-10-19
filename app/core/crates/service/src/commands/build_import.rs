//! `build.import`: writes the plan (`build.plan`) for the current champion select into the
//! client: Stronk's own rune page, Stronk's own item set, and the summoner spells with Flash
//! on the player's key (ADR-043). The player's pages and item sets are never changed.

use serde::{Deserialize, Serialize};
use serde_json::value::RawValue;
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
    let document = match merged_item_sets(&current, &item_set_json(plan, &name, champion_id)) {
        Ok(document) => document,
        Err(e) => return (skipped(&format!("{e}; nothing written")), None),
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

/// A JSON object's members in their order, each value as its raw text.
struct Members(Vec<(String, Box<RawValue>)>);

impl<'de> Deserialize<'de> for Members {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct Visit;
        impl<'de> serde::de::Visitor<'de> for Visit {
            type Value = Members;
            fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                f.write_str("a JSON object")
            }
            fn visit_map<A: serde::de::MapAccess<'de>>(
                self,
                mut map: A,
            ) -> Result<Members, A::Error> {
                let mut members = Vec::new();
                while let Some(member) = map.next_entry::<String, Box<RawValue>>()? {
                    members.push(member);
                }
                Ok(Members(members))
            }
        }
        deserializer.deserialize_map(Visit)
    }
}

/// Only what tells Stronk's sets from the player's; every other field stays raw.
#[derive(Deserialize)]
struct Titled {
    title: Option<String>,
}

/// The client's document with Stronk's sets replaced by `ours`. Only the outline is parsed:
/// every set that isn't Stronk's is copied byte for byte, and the other top-level members keep
/// their order and their values' raw text (only the whitespace between members is rewritten).
fn merged_item_sets(current: &str, ours: &Value) -> Result<String, CommandError> {
    let invalid = |what: &str| {
        CommandError::new(
            ErrorCode::InvalidData,
            format!("the client's item sets {what}"),
        )
    };
    let Members(members) = serde_json::from_str(current)
        .map_err(|e| invalid(&format!("are not a JSON object ({e})")))?;
    if !members.iter().any(|(key, _)| key == "itemSets") {
        return Err(invalid("have no `itemSets` list"));
    }
    let mut out = String::from("{");
    for (i, (key, value)) in members.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        out.push_str(&serde_json::to_string(key).map_err(|e| invalid(&e.to_string()))?);
        out.push(':');
        if key != "itemSets" {
            out.push_str(value.get());
            continue;
        }
        let sets: Vec<Box<RawValue>> = serde_json::from_str(value.get())
            .map_err(|e| invalid(&format!("`itemSets` is not a list ({e})")))?;
        let mut kept = Vec::with_capacity(sets.len() + 1);
        for set in &sets {
            let titled: Titled = serde_json::from_str(set.get())
                .map_err(|e| invalid(&format!("hold a set that is not an object ({e})")))?;
            if !titled.title.as_deref().is_some_and(is_ours) {
                kept.push(set.get());
            }
        }
        let ours = ours.to_string();
        kept.push(&ours);
        out.push('[');
        out.push_str(&kept.join(","));
        out.push(']');
    }
    out.push('}');
    Ok(out)
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
    fn merging_copies_the_players_sets_and_fields_byte_for_byte() {
        let theirs = r#"{"title": "My Jinx", "blocks":[ ],"x-future": {"n": 2.50, "s": "\u00e9"}}"#;
        let current = format!(
            r#"{{"timestamp":5,"itemSets":[{theirs}, {{"title":"Stronk: Jinx BOTTOM"}}],"accountId": 1}}"#
        );
        let merged = merged_item_sets(&current, &json!({"title": "Stronk: Ahri MIDDLE"})).unwrap();
        assert_eq!(
            merged,
            format!(
                r#"{{"timestamp":5,"itemSets":[{theirs},{{"title":"Stronk: Ahri MIDDLE"}}],"accountId":1}}"#
            )
        );
    }

    #[test]
    fn a_document_without_a_set_list_is_refused() {
        for bad in ["", "[]", "{}", r#"{"itemSets": 3}"#, r#"{"itemSets": [1]}"#] {
            assert!(merged_item_sets(bad, &json!({})).is_err(), "{bad}");
        }
    }
}
