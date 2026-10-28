//! The parts of the client's JSON the app reads, decoded leniently: unknown fields are ignored
//! and missing ones take defaults, because the client adds fields every patch.

use std::collections::BTreeMap;

use serde::Deserialize;
use stronk_domain::Role;
use stronk_service::ports::ChampSelect;

/// `GET /lol-champ-select/v1/session`.
#[derive(Debug, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct Session {
    pub local_player_cell_id: i64,
    pub my_team: Vec<TeamMember>,
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

/// One entry of `GET /lol-game-data/assets/v1/champion-summary.json`; `alias` is the key
/// published data uses (`LeeSin`).
#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ChampionSummary {
    pub id: i64,
    pub alias: String,
    /// The display name, in the client's language.
    #[serde(default)]
    pub name: String,
    /// The champion's square icon, under `/lol-game-data/assets/`.
    #[serde(default)]
    pub square_portrait_path: String,
}

/// An entry of the client's game data lists (`perks.json`, `summoner-spells.json`,
/// `items.json`): only the id, display name and icon.
#[derive(Debug, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct Named {
    pub id: i64,
    pub name: String,
    /// Where the client serves its icon, under `/lol-game-data/assets/`.
    pub icon_path: String,
}

/// `GET /lol-game-data/assets/v1/perkstyles.json`.
#[derive(Debug, Deserialize, Default)]
#[serde(default)]
pub struct PerkStyles {
    pub styles: Vec<PerkStyle>,
}

/// A rune tree: its name and icon, and its rows as the client lays them out.
#[derive(Debug, Deserialize, Default)]
#[serde(default)]
pub struct PerkStyle {
    #[serde(flatten)]
    pub named: Named,
    pub slots: Vec<PerkSlot>,
}

/// One row of a tree: `kKeyStone`, `kMixedRegularSplashable` (the three rows after it) or
/// `kStatMod` (the shard rows, the same in every tree).
#[derive(Debug, Deserialize, Default)]
#[serde(default)]
pub struct PerkSlot {
    #[serde(rename = "type")]
    pub kind: String,
    pub perks: Vec<i64>,
}

impl PerkStyles {
    /// Each tree's rows, keystones first, then the three rows after them; trees whose layout
    /// isn't four rows are left out.
    pub fn trees(&self) -> BTreeMap<i64, Vec<Vec<i64>>> {
        self.styles
            .iter()
            .filter_map(|s| {
                let rows: Vec<Vec<i64>> = s
                    .slots
                    .iter()
                    .filter(|slot| slot.kind != "kStatMod" && !slot.perks.is_empty())
                    .map(|slot| slot.perks.clone())
                    .collect();
                (rows.len() == 4).then_some((s.named.id, rows))
            })
            .collect()
    }

    /// The stat shard rows (offense, flex, defense), from the first tree that has three.
    pub fn shard_rows(&self) -> Vec<Vec<i64>> {
        self.styles
            .iter()
            .map(|s| {
                s.slots
                    .iter()
                    .filter(|slot| slot.kind == "kStatMod")
                    .map(|slot| slot.perks.clone())
                    .collect::<Vec<_>>()
            })
            .find(|rows| rows.len() == 3)
            .unwrap_or_default()
    }

    pub fn named(&self) -> impl Iterator<Item = &Named> {
        self.styles.iter().map(|s| &s.named)
    }
}

/// Id to name, leaving out entries without a name.
pub fn by_id<'a>(entries: impl IntoIterator<Item = &'a Named>) -> BTreeMap<i64, String> {
    entries
        .into_iter()
        .filter(|e| !e.name.is_empty())
        .map(|e| (e.id, e.name.clone()))
        .collect()
}

/// Where the client serves its game data images; an icon path must stay under it.
pub const ASSETS: &str = "/lol-game-data/assets/";

/// Id to icon path, leaving out entries without one and paths that could leave the client's
/// game data: anything outside [`ASSETS`], with `..`, a query or a fragment, or not plain ASCII.
pub fn icons_by_id<'a>(entries: impl IntoIterator<Item = (i64, &'a str)>) -> BTreeMap<i64, String> {
    entries
        .into_iter()
        .filter(|(_, path)| safe_asset_path(path))
        .map(|(id, path)| (id, path.to_owned()))
        .collect()
}

fn safe_asset_path(path: &str) -> bool {
    path.starts_with(ASSETS)
        && !path.split('/').any(|part| part == "..")
        && path
            .bytes()
            .all(|b| b.is_ascii_graphic() && !matches!(b, b'?' | b'#' | b'%' | b'\\'))
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
    fn names_keep_id_and_name_only_and_skip_unnamed_entries() {
        let items: Vec<Named> = serde_json::from_str(
            r#"[{"id": 6692, "name": "Eclipse", "priceTotal": 2900, "from": [3134]},
                {"id": 1, "description": "no name"}]"#,
        )
        .unwrap();
        assert_eq!(
            by_id(&items),
            BTreeMap::from([(6692, "Eclipse".to_owned())])
        );
        let styles: PerkStyles = serde_json::from_str(
            r#"{"schemaVersion": 2, "styles": [{"id": 8000, "name": "Precision"}]}"#,
        )
        .unwrap();
        assert_eq!(by_id(styles.named())[&8000], "Precision");
        assert!(styles.trees().is_empty()); // no layout: no tree
    }

    #[test]
    fn icon_paths_stay_in_the_clients_game_data() {
        let paths = [
            (
                1,
                "/lol-game-data/assets/ASSETS/Items/Icons2D/6692_Marksman_T3_Eclipse.png",
            ),
            (2, "/lol-game-data/assets/v1/champion-icons/64.png"),
            (3, ""),
            (4, "/lol-perks/v1/pages"),
            (5, "/lol-game-data/assets/../../lol-perks/v1/pages"),
            (6, "/lol-game-data/assets/x.png?y=1"),
            (7, "/lol-game-data/assets/%2e%2e/x.png"),
            (8, "https://example.com/lol-game-data/assets/x.png"),
            (9, "/lol-game-data/assets/a b.png"),
        ];
        let kept: Vec<_> = icons_by_id(paths).into_keys().collect();
        assert_eq!(kept, [1, 2]);
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

    #[test]
    fn perk_styles_give_each_trees_rows_and_the_shard_rows() {
        let styles: PerkStyles = serde_json::from_str(
            r#"{"styles": [{"id": 8000, "name": "Precision", "slots": [
                {"type": "kKeyStone", "slotLabel": "", "perks": [8005, 8008, 8021, 8010]},
                {"type": "kMixedRegularSplashable", "perks": [9101, 9111, 8009]},
                {"type": "kMixedRegularSplashable", "perks": [9104, 9105, 9103]},
                {"type": "kMixedRegularSplashable", "perks": [8014, 8017, 8299]},
                {"type": "kStatMod", "slotLabel": "Offense", "perks": [5008, 5005, 5007]},
                {"type": "kStatMod", "slotLabel": "Flex", "perks": [5008, 5010, 5001]},
                {"type": "kStatMod", "slotLabel": "Defense", "perks": [5011, 5013, 5001]}
            ]}, {"id": 9000, "name": "Odd", "slots": [{"type": "kKeyStone", "perks": [1]}]}]}"#,
        )
        .unwrap();
        let trees = styles.trees();
        assert_eq!(trees.len(), 1); // a tree without four rows is left out
        assert_eq!(trees[&8000][0], vec![8005, 8008, 8021, 8010]);
        assert_eq!(trees[&8000][3], vec![8014, 8017, 8299]);
        assert_eq!(
            styles.shard_rows(),
            vec![
                vec![5008, 5005, 5007],
                vec![5008, 5010, 5001],
                vec![5011, 5013, 5001]
            ]
        );
    }
}
