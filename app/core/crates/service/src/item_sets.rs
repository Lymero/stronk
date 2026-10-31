//! The client's item sets: the document, handled as raw JSON (ADR-043), where only its outline
//! is parsed so everything that isn't Stronk's is written back byte for byte (shared by
//! `build.import` and `item_sets.restore`); and Stronk's own set in the client's format.

use serde::Deserialize;
use serde_json::value::RawValue;
use serde_json::{Value, json};
use stronk_domain::owned::is_ours;

use crate::{CommandError, ErrorCode};

/// A checked item set document: a JSON object whose `itemSets` is a list of objects.
pub struct Document {
    members: Vec<(String, Box<RawValue>)>,
    sets: Vec<Box<RawValue>>,
}

impl Document {
    /// `what` names the document in errors ("the client's item sets", "the backup").
    pub fn parse(text: &str, what: &str) -> Result<Self, CommandError> {
        let invalid = |problem: String| {
            CommandError::new(ErrorCode::InvalidData, format!("{what} {problem}"))
        };
        let Members(members) = serde_json::from_str(text)
            .map_err(|e| invalid(format!("is not a JSON object ({e})")))?;
        let list = members
            .iter()
            .find(|(key, _)| key == "itemSets")
            .ok_or_else(|| invalid("has no `itemSets` list".into()))?;
        let sets: Vec<Box<RawValue>> = serde_json::from_str(list.1.get())
            .map_err(|e| invalid(format!("has an `itemSets` that is not a list ({e})")))?;
        for set in &sets {
            serde_json::from_str::<Titled>(set.get())
                .map_err(|e| invalid(format!("holds a set that is not an object ({e})")))?;
        }
        Ok(Self { members, sets })
    }

    /// The `accountId` member, as its raw text (compared, never interpreted).
    pub fn account(&self) -> Option<&str> {
        self.members
            .iter()
            .find(|(key, _)| key == "accountId")
            .map(|(_, v)| v.get())
    }

    pub fn len(&self) -> usize {
        self.sets.len()
    }

    pub fn is_empty(&self) -> bool {
        self.sets.is_empty()
    }

    /// The document with Stronk's sets replaced by `ours`, first in the list so the shop shows
    /// it on top: every set that isn't Stronk's is copied byte for byte, in its order, and the
    /// other top-level members keep their order and their values' raw text (only the
    /// whitespace between members is rewritten).
    pub fn with_ours(&self, ours: &Value) -> String {
        let ours = ours.to_string();
        let kept: Vec<&str> = self
            .sets
            .iter()
            .filter(|set| {
                let title = serde_json::from_str::<Titled>(set.get())
                    .ok()
                    .and_then(|t| t.title);
                !title.as_deref().is_some_and(is_ours)
            })
            .map(|set| set.get())
            .collect();
        let list = format!("[{}]", [vec![ours.as_str()], kept].concat().join(","));
        let members = self.members.iter().map(|(key, value)| {
            let value = if key == "itemSets" {
                list.as_str()
            } else {
                value.get()
            };
            // A key read from JSON always serialises back.
            format!("{}:{value}", serde_json::to_string(key).unwrap_or_default())
        });
        format!("{{{}}}", members.collect::<Vec<_>>().join(","))
    }
}

/// One of Stronk's item sets: what to write, without the client's format.
pub struct ItemSet {
    pub title: String,
    /// Stable per champion and role, so a new import replaces the set in place.
    pub uid: String,
    pub champion_id: i64,
    pub blocks: Vec<Block>,
}

/// One block of an item set: its name, and its items in order, repeated as bought.
pub struct Block {
    pub name: String,
    pub items: Vec<i64>,
}

impl ItemSet {
    /// The set as the client stores it: on every map and mode, listed first in the shop
    /// (`priority`); a block's repeated item is one entry with its count (two Health Potions
    /// read "2").
    pub fn to_json(&self) -> Value {
        let blocks: Vec<Value> = self
            .blocks
            .iter()
            .map(|b| {
                let mut counted: Vec<(i64, u32)> = Vec::new();
                for id in &b.items {
                    match counted.iter_mut().find(|(i, _)| i == id) {
                        Some((_, n)) => *n += 1,
                        None => counted.push((*id, 1)),
                    }
                }
                let items: Vec<Value> = counted
                    .into_iter()
                    .map(|(id, count)| json!({"id": id.to_string(), "count": count}))
                    .collect();
                json!({"type": b.name, "items": items})
            })
            .collect();
        json!({
            "title": self.title,
            "type": "custom",
            "map": "any",
            "mode": "any",
            "priority": true,
            "sortrank": 0,
            "associatedChampions": [self.champion_id],
            "associatedMaps": [],
            "blocks": blocks,
            "uid": self.uid,
        })
    }
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

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn merging_copies_the_players_sets_and_fields_byte_for_byte() {
        let theirs = r#"{"title": "My Jinx", "blocks":[ ],"x-future": {"n": 2.50, "s": "é"}}"#;
        let current = format!(
            r#"{{"timestamp":5,"itemSets":[{theirs}, {{"title":"Stronk: Jinx BOTTOM"}}],"accountId": 1}}"#
        );
        let document = Document::parse(&current, "the client's item sets").unwrap();
        assert_eq!(document.account(), Some("1"));
        assert_eq!(
            document.with_ours(&json!({"title": "Stronk: Ahri MIDDLE"})),
            format!(
                r#"{{"timestamp":5,"itemSets":[{{"title":"Stronk: Ahri MIDDLE"}},{theirs}],"accountId":1}}"#
            )
        );
    }

    #[test]
    fn a_set_counts_repeats_and_comes_first_in_the_shop() {
        let set = ItemSet {
            title: "Stronk: Lee Sin Jungle".into(),
            uid: "stronk-leesin-jungle".into(),
            champion_id: 64,
            blocks: vec![Block {
                name: "Start: Popular".into(),
                items: vec![1103, 2003, 2003],
            }],
        }
        .to_json();
        assert_eq!(set["priority"], true);
        assert_eq!(set["associatedChampions"], json!([64]));
        assert_eq!(
            set["blocks"],
            json!([{"type": "Start: Popular", "items": [
                {"id": "1103", "count": 1}, {"id": "2003", "count": 2}]}])
        );
    }

    #[test]
    fn a_document_without_a_set_list_is_refused() {
        for bad in ["", "[]", "{}", r#"{"itemSets": 3}"#, r#"{"itemSets": [1]}"#] {
            assert!(Document::parse(bad, "x").is_err(), "{bad}");
        }
    }
}
