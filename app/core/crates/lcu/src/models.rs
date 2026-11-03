//! The parts of the client's JSON the app reads, decoded leniently: unknown fields are ignored
//! and missing ones take defaults, because the client adds fields every patch.

use serde::Deserialize;
use stronk_domain::Role;
use stronk_service::ports::ChampSelect;

/// `GET /lol-champ-select/v1/session`.
#[derive(Debug, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct Session {
    pub local_player_cell_id: i64,
    pub my_team: Vec<TeamMember>,
    pub their_team: Vec<TeamMember>,
    pub actions: Vec<Vec<Action>>,
    pub timer: Timer,
}

#[derive(Debug, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct TeamMember {
    pub cell_id: i64,
    pub champion_id: i64,
    pub champion_pick_intent: i64,
    pub assigned_position: String,
    pub spell1_id: i64,
    pub spell2_id: i64,
}

#[derive(Debug, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct Action {
    pub actor_cell_id: i64,
    pub champion_id: i64,
    pub completed: bool,
    pub is_in_progress: bool,
    #[serde(rename = "type")]
    pub kind: String,
}

#[derive(Debug, Deserialize, Default)]
#[serde(default)]
pub struct Timer {
    pub phase: String,
}

impl Session {
    /// The local player's view: the locked champion, else the one being hovered in the pick
    /// turn, else the pick intent declared while planning.
    pub fn local(&self) -> ChampSelect {
        let me = self
            .my_team
            .iter()
            .find(|m| m.cell_id == self.local_player_cell_id);
        let picks = || {
            self.actions
                .iter()
                .flatten()
                .filter(|a| a.actor_cell_id == self.local_player_cell_id && a.kind == "pick")
        };
        let locked = picks().find(|a| a.completed && a.champion_id > 0);
        let hovering = picks().find(|a| a.is_in_progress && a.champion_id > 0);
        let champion_id = locked
            .or(hovering)
            .map(|a| a.champion_id)
            .or_else(|| me.map(|m| m.champion_id).filter(|&id| id > 0))
            .or_else(|| me.map(|m| m.champion_pick_intent).filter(|&id| id > 0))
            .unwrap_or(0);
        ChampSelect {
            champion_id,
            locked: locked.is_some(),
            role: me.and_then(|m| Role::from_lcu(&m.assigned_position)),
            phase: self.timer.phase.clone(),
            spells: me
                .map(|m| (m.spell1_id, m.spell2_id))
                .filter(|&(d, f)| d > 0 && f > 0),
            enemies: self
                .their_team
                .iter()
                .map(|m| m.champion_id)
                .filter(|&id| id > 0)
                .collect(),
        }
    }
}

/// One entry of `GET /lol-perks/v1/pages`.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PerkPage {
    pub id: i64,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub is_editable: bool,
}

/// `GET /lol-perks/v1/inventory`.
#[derive(Debug, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct PerkInventory {
    pub owned_page_count: usize,
}

/// `GET /lol-summoner/v1/current-summoner`: only the id the item set path needs.
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CurrentSummoner {
    pub summoner_id: i64,
}

/// The image type of `bytes` from its first bytes, whatever the response claimed.
pub fn image_type(bytes: &[u8]) -> Option<&'static str> {
    if bytes.starts_with(b"\x89PNG\r\n\x1a\n") {
        Some("image/png")
    } else if bytes.starts_with(&[0xFF, 0xD8, 0xFF]) {
        Some("image/jpeg")
    } else if bytes.len() > 12 && bytes.starts_with(b"RIFF") && bytes.get(8..12) == Some(b"WEBP") {
        Some("image/webp")
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn session(json: &str) -> Session {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn hover_then_lock() {
        let planning = session(
            r#"{"localPlayerCellId": 1, "timer": {"phase": "PLANNING"},
            "myTeam": [{"cellId": 1, "championPickIntent": 64, "assignedPosition": "jungle"}]}"#,
        );
        assert_eq!(planning.local().champion_id, 64);
        assert!(!planning.local().locked);
        assert_eq!(planning.local().role, Some(Role::Jungle));

        let locked = session(
            r#"{"localPlayerCellId": 1, "timer": {"phase": "FINALIZATION"},
            "myTeam": [{"cellId": 1, "championId": 121, "assignedPosition": "jungle"}],
            "actions": [[{"actorCellId": 1, "championId": 121, "completed": true, "type": "pick"}],
                        [{"actorCellId": 1, "championId": 7, "completed": true, "type": "ban"}]]}"#,
        );
        assert_eq!(locked.local().champion_id, 121);
        assert!(locked.local().locked);
    }

    #[test]
    fn the_enemies_are_the_champions_they_picked_so_far() {
        let s = session(
            r#"{"localPlayerCellId": 1, "myTeam": [{"cellId": 1, "championId": 64}],
            "theirTeam": [{"cellId": 5, "championId": 86}, {"cellId": 6, "championId": 0},
                          {"cellId": 7, "championId": 103}]}"#,
        );
        assert_eq!(s.local().enemies, vec![86, 103]);
        assert!(session("{}").local().enemies.is_empty());
    }

    #[test]
    fn images_are_recognised_by_their_bytes() {
        assert_eq!(image_type(b"\x89PNG\r\n\x1a\n...."), Some("image/png"));
        assert_eq!(image_type(&[0xFF, 0xD8, 0xFF, 0xE0]), Some("image/jpeg"));
        assert_eq!(image_type(b"RIFF\0\0\0\0WEBPVP8 "), Some("image/webp"));
        assert_eq!(image_type(b"<svg onload=alert(1)>"), None);
        assert_eq!(image_type(b"{\"message\": \"x\"}"), None);
    }

    #[test]
    fn tolerates_unknown_and_missing_fields() {
        let s = session(r#"{"somethingNew": [1, 2], "myTeam": [{"cellId": 0, "extra": true}]}"#);
        let local = s.local();
        assert_eq!(local.champion_id, 0);
        assert_eq!(local.role, None);
    }
}
