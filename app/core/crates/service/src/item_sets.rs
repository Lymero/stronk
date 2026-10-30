//! The client's item set document, handled as raw JSON (ADR-043): only its outline is parsed,
//! so everything that isn't Stronk's is written back byte for byte. Shared by `build.import`
//! and `item_sets.restore`.

use serde::Deserialize;
use serde_json::Value;
use serde_json::value::RawValue;
use stronk_domain::select::is_ours;

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
    fn a_document_without_a_set_list_is_refused() {
        for bad in ["", "[]", "{}", r#"{"itemSets": 3}"#, r#"{"itemSets": [1]}"#] {
            assert!(Document::parse(bad, "x").is_err(), "{bad}");
        }
    }
}
