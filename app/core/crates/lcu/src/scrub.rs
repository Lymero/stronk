//! Recordings of the client keep only what the app and lcu-mock read (an allowlist), so
//! account ids, PUUIDs, names, chat and anything Riot adds later never reach a file.
//! [`identifiers`] then looks for anything that still looks like one; the recorder refuses to
//! save when it finds any, and tools/lcu_mock's tests run the same rules on committed sessions.

use serde_json::{Map, Value};

/// The allowlisted parts of a `/lol-champ-select/v1/session` response. Timer counters are
/// dropped too, so two polls of the same state are equal.
pub fn session(raw: &Value) -> Value {
    let mut out = Map::new();
    copy(
        raw,
        &mut out,
        &["localPlayerCellId", "isCustomGame", "benchEnabled"],
    );
    if let Some(phase) = raw.pointer("/timer/phase") {
        out.insert("timer".into(), serde_json::json!({ "phase": phase }));
    }
    for team in ["myTeam", "theirTeam"] {
        if let Some(Value::Array(members)) = raw.get(team) {
            out.insert(
                team.into(),
                Value::Array(members.iter().map(member).collect()),
            );
        }
    }
    if let Some(Value::Array(turns)) = raw.get("actions") {
        let turns = turns
            .iter()
            .map(|turn| match turn {
                Value::Array(actions) => Value::Array(actions.iter().map(action).collect()),
                _ => Value::Array(vec![]),
            })
            .collect();
        out.insert("actions".into(), Value::Array(turns));
    }
    if let Some(bans) = raw.get("bans") {
        let mut kept = Map::new();
        for side in ["myTeamBans", "theirTeamBans"] {
            if let Some(Value::Array(ids)) = bans.get(side) {
                kept.insert(
                    side.into(),
                    Value::Array(ids.iter().filter(|v| v.is_i64()).cloned().collect()),
                );
            }
        }
        out.insert("bans".into(), Value::Object(kept));
    }
    Value::Object(out)
}

fn member(raw: &Value) -> Value {
    let mut out = Map::new();
    copy(
        raw,
        &mut out,
        &[
            "cellId",
            "championId",
            "championPickIntent",
            "assignedPosition",
            "team",
            "spell1Id",
            "spell2Id",
        ],
    );
    Value::Object(out)
}

fn action(raw: &Value) -> Value {
    let mut out = Map::new();
    copy(
        raw,
        &mut out,
        &[
            "id",
            "actorCellId",
            "championId",
            "completed",
            "isInProgress",
            "isAllyAction",
            "type",
            "pickTurn",
        ],
    );
    Value::Object(out)
}

/// Copies `keys` whose values are numbers, booleans, or short plain words (positions, action
/// types, phases): never an object, array or free text.
fn copy(raw: &Value, out: &mut Map<String, Value>, keys: &[&str]) {
    for key in keys {
        match raw.get(*key) {
            Some(v @ (Value::Number(_) | Value::Bool(_))) => {
                out.insert((*key).into(), v.clone());
            }
            Some(Value::String(s)) if is_word(s) => {
                out.insert((*key).into(), Value::String(s.clone()));
            }
            _ => {}
        }
    }
}

fn is_word(s: &str) -> bool {
    s.len() <= 24 && s.bytes().all(|b| b.is_ascii_alphabetic() || b == b'_')
}

/// Key names that hold personal data in the client's API.
const PERSONAL_KEYS: [&str; 14] = [
    "puuid",
    "summonerid",
    "accountid",
    "playerid",
    "gamename",
    "tagline",
    "displayname",
    "summonername",
    "internalname",
    "obfuscated",
    "chat",
    "muc",
    "jwt",
    "password",
];

/// JSON paths of anything in `value` that looks like a personal identifier: a personal key
/// name, a UUID, a long opaque token, or a Riot ID (`name#tag`). Empty means clean.
pub fn identifiers(value: &Value) -> Vec<String> {
    let mut found = Vec::new();
    walk(value, "", &mut found);
    found
}

fn walk(value: &Value, path: &str, found: &mut Vec<String>) {
    match value {
        Value::Object(map) => {
            for (key, child) in map {
                let lower = key.to_ascii_lowercase();
                let child_path = format!("{path}/{key}");
                if PERSONAL_KEYS.iter().any(|k| lower.contains(k)) {
                    found.push(child_path.clone());
                }
                walk(child, &child_path, found);
            }
        }
        Value::Array(items) => {
            for (i, item) in items.iter().enumerate() {
                walk(item, &format!("{path}/{i}"), found);
            }
        }
        Value::String(s) if looks_like_identifier(s) => found.push(path.to_owned()),
        _ => {}
    }
}

fn looks_like_identifier(s: &str) -> bool {
    let uuid = s.len() == 36
        && s.char_indices().all(|(i, c)| {
            if matches!(i, 8 | 13 | 18 | 23) {
                c == '-'
            } else {
                c.is_ascii_hexdigit()
            }
        });
    let token = s.len() >= 32
        && !s.contains(' ')
        && s.bytes().all(|b| {
            b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b'=' | b'.' | b'/' | b'+')
        });
    let riot_id = s.split_once('#').is_some_and(|(name, tag)| {
        !name.is_empty()
            && (2..=5).contains(&tag.len())
            && tag.bytes().all(|b| b.is_ascii_alphanumeric())
    });
    uuid || token || riot_id
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    /// A session as the client sends it, with every kind of personal data it carries.
    fn raw() -> Value {
        json!({
            "localPlayerCellId": 1, "gameId": 7_212_345_678_i64, "isCustomGame": true,
            "timer": {"phase": "BAN_PICK", "adjustedTimeLeftInPhase": 21_337, "internalNowInEpochMs": 1},
            "chatDetails": {"mucJwtDto": {"jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2ln"},
                            "multiUserChatId": "c1~0123456789abcdef", "multiUserChatPassword": "pw"},
            "myTeam": [{"cellId": 1, "championId": 64, "championPickIntent": 0, "assignedPosition": "jungle",
                        "team": 1, "spell1Id": 4, "spell2Id": 11,
                        "summonerId": 123_456_789, "puuid": "2f1c0f1e-8c4b-4f3a-9a3c-1b2c3d4e5f60",
                        "gameName": "Somebody", "tagLine": "EUW", "nameVisibilityType": "VISIBLE",
                        "obfuscatedPuuid": "x", "playerType": "PLAYER"}],
            "theirTeam": [{"cellId": 5, "championId": 0, "summonerId": 987, "puuid": "abc"}],
            "actions": [[{"id": 1, "actorCellId": 1, "championId": 64, "completed": false,
                          "isInProgress": true, "type": "pick", "isAllyAction": true}]],
            "bans": {"myTeamBans": [7], "theirTeamBans": [], "numBans": 0}
        })
    }

    #[test]
    fn the_raw_session_is_full_of_identifiers() {
        let found = identifiers(&raw());
        for path in [
            "/chatDetails",
            "/myTeam/0/summonerId",
            "/myTeam/0/puuid",
            "/myTeam/0/gameName",
            "/myTeam/0/tagLine",
            "/theirTeam/0/puuid",
        ] {
            assert!(
                found.iter().any(|p| p == path),
                "{path} not flagged in {found:?}"
            );
        }
    }

    #[test]
    fn scrubbing_leaves_none_and_keeps_what_the_app_reads() {
        let clean = session(&raw());
        assert_eq!(identifiers(&clean), Vec::<String>::new());
        assert_eq!(clean.pointer("/myTeam/0/championId"), Some(&json!(64)));
        assert_eq!(
            clean.pointer("/myTeam/0/assignedPosition"),
            Some(&json!("jungle"))
        );
        assert_eq!(
            clean.pointer("/actions/0/0/isInProgress"),
            Some(&json!(true))
        );
        assert_eq!(clean.pointer("/timer"), Some(&json!({"phase": "BAN_PICK"})));
        assert_eq!(clean.get("gameId"), None);
        let local = serde_json::from_value::<crate::models::Session>(clean)
            .unwrap()
            .local();
        assert_eq!((local.champion_id, local.locked), (64, false));
    }

    #[test]
    fn flags_identifier_shaped_values_under_any_key() {
        assert!(!identifiers(&json!({"note": "Faker#KR1"})).is_empty());
        assert!(!identifiers(&json!({"x": "2f1c0f1e-8c4b-4f3a-9a3c-1b2c3d4e5f60"})).is_empty());
        assert!(!identifiers(&json!({"x": "aGVsbG8taGVsbG8taGVsbG8taGVsbG8taGVsbG8"})).is_empty());
        assert!(
            identifiers(&json!({"phase": "FINALIZATION", "assignedPosition": "utility"}))
                .is_empty()
        );
    }
}
