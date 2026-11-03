//! The client's game data documents (`/lol-game-data/assets/v1/`): champion, rune, spell and
//! item names, the rune trees' layout and icon paths. The League client serves them to the app;
//! CommunityDragon mirrors the same files for the web viewer (ADR-086). Decoded leniently:
//! unknown fields are ignored and missing ones take defaults, because they change every patch.

use std::collections::BTreeMap;

use serde::Deserialize;

use crate::ports::{GameNames, IconKind};

/// Names and icon paths from the game data documents.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct GameData {
    pub names: GameNames,
    /// Icon paths by kind, then id, each checked to stay under [`ASSETS`].
    pub icons: BTreeMap<IconKind, BTreeMap<i64, String>>,
}

impl GameData {
    /// From `champion-summary.json`, `perkstyles.json`, `perks.json`, `summoner-spells.json`
    /// and `items.json`, decoded.
    pub fn from_documents(
        champions: &[ChampionSummary],
        perk_styles: &PerkStyles,
        runes: &[Named],
        spells: &[Named],
        items: &[Named],
    ) -> Self {
        let styles: Vec<&Named> = perk_styles.named().collect();
        let paths =
            |entries: &[Named]| icons_by_id(entries.iter().map(|e| (e.id, e.icon_path.as_str())));
        GameData {
            names: GameNames {
                champions: champions
                    .iter()
                    .filter(|c| !c.name.is_empty())
                    .map(|c| (c.id, c.name.clone()))
                    .collect(),
                rune_styles: by_id(styles.iter().copied()),
                rune_trees: perk_styles.trees(),
                shard_rows: perk_styles.shard_rows(),
                runes: by_id(runes),
                spells: by_id(spells),
                items: by_id(items),
            },
            icons: BTreeMap::from([
                (
                    IconKind::Champion,
                    icons_by_id(
                        champions
                            .iter()
                            .map(|c| (c.id, c.square_portrait_path.as_str())),
                    ),
                ),
                (
                    IconKind::RuneStyle,
                    icons_by_id(styles.iter().map(|e| (e.id, e.icon_path.as_str()))),
                ),
                (IconKind::Rune, paths(runes)),
                (IconKind::Spell, paths(spells)),
                (IconKind::Item, paths(items)),
            ]),
        }
    }
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

/// `GET /lol-game-data/assets/v1/champions/{id}.json`, one champion's own document: here only
/// its abilities.
#[derive(Debug, Deserialize, Default)]
#[serde(default)]
pub struct ChampionDetail {
    pub spells: Vec<Ability>,
}

/// One of a champion's Q, W, E and R.
#[derive(Debug, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct Ability {
    /// `q`, `w`, `e` or `r`.
    pub spell_key: String,
    /// Where the client serves its icon, under `/lol-game-data/assets/`.
    pub ability_icon_path: String,
}

impl ChampionDetail {
    /// Where the client serves the document of `champion` (its numeric id).
    pub fn path(champion: i64) -> String {
        format!("{ASSETS}v1/champions/{champion}.json")
    }

    /// Icon paths by slot, Q 1 to R 4 (as `skills::id` numbers keys), checked as every icon is.
    pub fn ability_icons(&self) -> BTreeMap<i64, String> {
        icons_by_id(self.spells.iter().filter_map(|a| {
            let slot = match a.spell_key.as_str() {
                "q" => 1,
                "w" => 2,
                "e" => 3,
                "r" => 4,
                _ => return None,
            };
            Some((slot, a.ability_icon_path.as_str()))
        }))
    }
}

/// An ability's id in `icons.get` (ADR-085): its champion's id times ten plus its slot, Q 1 to
/// R 4, so Lee Sin's (64) Q is 641. None for a slot outside 1 to 4 or an id too large.
pub fn ability_id(champion: i64, slot: i64) -> Option<i64> {
    let valid = champion > 0 && (1..=4).contains(&slot);
    valid
        .then(|| champion.checked_mul(10)?.checked_add(slot))
        .flatten()
}

/// The champion and slot an ability id stands for ([`ability_id`] reversed).
pub fn ability_of(id: i64) -> Option<(i64, i64)> {
    let (champion, slot) = (id.div_euclid(10), id.rem_euclid(10));
    (champion > 0 && (1..=4).contains(&slot)).then_some((champion, slot))
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

#[cfg(test)]
mod tests {
    use super::*;

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
    fn a_champions_abilities_give_their_icons_by_slot() {
        let lee: ChampionDetail = serde_json::from_str(
            r#"{"id": 64, "passive": {"abilityIconPath": "/lol-game-data/assets/P.png"},
                "spells": [
                  {"spellKey": "r", "abilityIconPath": "/lol-game-data/assets/ASSETS/LeeSinR.png"},
                  {"spellKey": "q", "abilityIconPath": "/lol-game-data/assets/ASSETS/LeeSinQ1.png"},
                  {"spellKey": "w", "abilityIconPath": "https://elsewhere.test/w.png"},
                  {"spellKey": "x", "abilityIconPath": "/lol-game-data/assets/X.png"},
                  {"name": "no key"}]}"#,
        )
        .unwrap();
        assert_eq!(
            lee.ability_icons(),
            BTreeMap::from([
                (1, "/lol-game-data/assets/ASSETS/LeeSinQ1.png".to_owned()),
                (4, "/lol-game-data/assets/ASSETS/LeeSinR.png".to_owned()),
            ])
        );
        assert_eq!(
            ChampionDetail::path(64),
            "/lol-game-data/assets/v1/champions/64.json"
        );
    }

    #[test]
    fn an_ability_id_is_its_champion_and_slot() {
        assert_eq!(ability_id(64, 1), Some(641));
        assert_eq!(ability_of(641), Some((64, 1)));
        assert_eq!(ability_of(ability_id(901, 4).unwrap()), Some((901, 4)));
        for (champion, slot) in [(64, 0), (64, 5), (0, 1), (-3, 1), (i64::MAX, 1)] {
            assert_eq!(ability_id(champion, slot), None, "{champion} {slot}");
        }
        for id in [640, 645, 4, -641, 0] {
            assert_eq!(ability_of(id), None, "{id}");
        }
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
