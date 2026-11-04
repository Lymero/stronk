//! The web build viewer's core (ADR-086), built to WebAssembly: the browser has no `stronk-core`,
//! so the same rules run here. A patch's manifest is checked against its signature and the
//! viewer's public key, each build file against the manifest, and the plan is `build.plan`'s
//! own (`plan`), so the viewer shows what the app would import. Names and icon paths come from
//! the client's game data documents, which CommunityDragon mirrors, read as the app reads them.
//!
//! Everything is plain Rust returning `Result<_, String>`, tested natively; the
//! `#[wasm_bindgen]` items only turn errors into JavaScript ones.

use std::collections::BTreeMap;

use serde::Serialize;
use stronk_data::{TrustedKey, VerifiedManifest};
use stronk_domain::{BuildKey, Patch, Role, Window, elo};
use stronk_service::commands::build_plan::{Plan, plan};
use stronk_service::game_data::{
    ChampionDetail, ChampionSummary, GameData, Named, PerkStyles, ability_id,
};
use stronk_service::ports::{GameNames, IconKind};
use wasm_bindgen::prelude::*;

/// The region builds are published for.
const REGION: &str = "all";

/// A patch's published data, its manifest verified.
#[wasm_bindgen]
pub struct Data {
    manifest: VerifiedManifest,
}

/// Where the app reads a champion and role's build: its bracket and window.
#[derive(Debug, PartialEq, Eq, Serialize)]
pub struct Found {
    pub elo: String,
    pub window: Window,
}

/// A champion and role with a build in at least one bracket.
#[derive(Debug, PartialEq, Eq, PartialOrd, Ord, Serialize)]
pub struct Listed {
    pub champion: String,
    pub role: Role,
}

impl Data {
    /// The manifest of `patch`, if `signature` is the viewer's key's over it.
    pub fn verified(
        public_key: &str,
        patch: &str,
        manifest: &[u8],
        signature: &[u8],
    ) -> Result<Self, String> {
        let key = TrustedKey::decode(public_key).map_err(|e| e.to_string())?;
        let patch: Patch = patch
            .parse()
            .map_err(|_| format!("{patch} is not a patch"))?;
        let manifest = VerifiedManifest::verify(&key, patch, manifest, signature)
            .map_err(|e| e.to_string())?;
        Ok(Self { manifest })
    }

    /// Every champion and role the manifest has a build for, by champion then role.
    pub fn listed(&self) -> Vec<Listed> {
        let mut out: Vec<Listed> = self
            .manifest
            .manifest
            .files
            .iter()
            .filter_map(|f| {
                let parts: Vec<&str> = f.path.as_str().split('/').collect();
                let (champion, file) = match parts.as_slice() {
                    [_, _, champion, file] | [_, _, "pooled", champion, file] => (champion, file),
                    _ => return None,
                };
                let role = role(file.strip_suffix(".json")?)?;
                Some(Listed {
                    champion: (*champion).to_owned(),
                    role,
                })
            })
            .collect();
        out.sort();
        out.dedup();
        out
    }

    /// The bracket and window whose build of `champion` and `role` the app would read for
    /// `wanted` and `window`, in `build_get::fetch_preferring`'s order: the bracket in that
    /// window, then in the other, then the closest bracket with a build, wider first
    /// (`elo::fallbacks`, ADR-079, ADR-088).
    pub fn found_for(
        &self,
        champion: &str,
        role: &str,
        wanted: &str,
        window: Window,
    ) -> Option<Found> {
        let role = self::role(role)?;
        elo::fallbacks(wanted).into_iter().find_map(|bracket| {
            window.fallbacks().into_iter().find_map(|window| {
                let key = BuildKey::new(REGION, bracket, champion, role)
                    .ok()?
                    .in_window(window);
                self.manifest.entry(&key.path()).map(|_| Found {
                    elo: bracket.to_owned(),
                    window,
                })
            })
        })
    }

    /// The plan for the build `data` holds, if it is the manifest's file for `champion`, `role`,
    /// `bracket` and `window`: `build.plan`'s, with no enemies known (boots over every game).
    pub fn plan_of(
        &self,
        champion: &str,
        role: &str,
        bracket: &str,
        window: Window,
        data: &[u8],
    ) -> Result<Plan, String> {
        let role = self::role(role).ok_or_else(|| format!("{role} is not a role"))?;
        let key = BuildKey::new(REGION, bracket, champion, role)
            .map_err(|e| e.to_string())?
            .in_window(window);
        let build = self
            .manifest
            .parse_build(&key, data)
            .map_err(|e| e.to_string())?;
        Ok(plan(&build, role, None))
    }

    /// Where the build of `champion`, `role`, `bracket` and `window` is, inside the patch
    /// directory.
    pub fn path(
        champion: &str,
        role: &str,
        bracket: &str,
        window: Window,
    ) -> Result<String, String> {
        let role = self::role(role).ok_or_else(|| format!("{role} is not a role"))?;
        let key = BuildKey::new(REGION, bracket, champion, role).map_err(|e| e.to_string())?;
        Ok(key.in_window(window).path())
    }
}

#[wasm_bindgen]
impl Data {
    /// Verifies `manifest` (the patch's `manifest.json`) against `signature` (its `.minisig`)
    /// and `public_key` (a minisign public key file).
    #[wasm_bindgen(constructor)]
    pub fn new(
        public_key: &str,
        patch: &str,
        manifest: &[u8],
        signature: &[u8],
    ) -> Result<Data, JsError> {
        Self::verified(public_key, patch, manifest, signature).map_err(|e| JsError::new(&e))
    }

    /// The elo brackets with builds, highest first.
    pub fn elos(&self) -> Vec<String> {
        self.manifest.elos()
    }

    /// The windows with builds, pooled first (ADR-088): `"pooled"`, `"patch"`.
    pub fn windows(&self) -> Vec<String> {
        self.manifest
            .windows()
            .into_iter()
            .map(|w| w.as_str().to_owned())
            .collect()
    }

    /// [`Data::listed`] as JSON: `[{"champion": "LeeSin", "role": "JUNGLE"}, …]`.
    pub fn builds(&self) -> Result<String, JsError> {
        serde_json::to_string(&self.listed()).map_err(|e| JsError::new(&e.to_string()))
    }

    /// [`Data::found_for`] as JSON, `{"elo": "diamond_plus", "window": "pooled"}`, if any.
    pub fn found(
        &self,
        champion: &str,
        role: &str,
        wanted: &str,
        window: &str,
    ) -> Result<Option<String>, JsError> {
        let found = self.found_for(champion, role, wanted, self::window(window)?);
        found
            .map(|f| serde_json::to_string(&f).map_err(|e| JsError::new(&e.to_string())))
            .transpose()
    }

    /// [`Data::path`].
    pub fn file(
        champion: &str,
        role: &str,
        bracket: &str,
        window: &str,
    ) -> Result<String, JsError> {
        Self::path(champion, role, bracket, self::window(window)?).map_err(|e| JsError::new(&e))
    }

    /// [`Data::plan_of`] as JSON, the shape `build.plan` returns.
    pub fn plan(
        &self,
        champion: &str,
        role: &str,
        bracket: &str,
        window: &str,
        data: &[u8],
    ) -> Result<String, JsError> {
        let plan = self
            .plan_of(champion, role, bracket, self::window(window)?, data)
            .map_err(|e| JsError::new(&e))?;
        serde_json::to_string(&plan).map_err(|e| JsError::new(&e.to_string()))
    }
}

/// Names and icon paths, as `names.get` and the app's icons read them from the client.
#[derive(Debug, Serialize)]
pub struct Names {
    pub names: GameNames,
    /// Icon paths by kind (`champions`, `rune_styles`, `runes`, `spells`, `items`), then id,
    /// under `/lol-game-data/assets/`.
    pub icons: BTreeMap<&'static str, BTreeMap<i64, String>>,
}

/// From the five game data documents' text (`champion-summary.json`, `perkstyles.json`,
/// `perks.json`, `summoner-spells.json`, `items.json`).
pub fn names_of(
    champions: &str,
    perk_styles: &str,
    perks: &str,
    spells: &str,
    items: &str,
) -> Result<Names, String> {
    fn read<T: serde::de::DeserializeOwned>(what: &str, text: &str) -> Result<T, String> {
        serde_json::from_str(text).map_err(|e| format!("{what}: {e}"))
    }
    let champions: Vec<ChampionSummary> = read("champion-summary.json", champions)?;
    let perk_styles: PerkStyles = read("perkstyles.json", perk_styles)?;
    let runes: Vec<Named> = read("perks.json", perks)?;
    let spells: Vec<Named> = read("summoner-spells.json", spells)?;
    let items: Vec<Named> = read("items.json", items)?;
    let data = GameData::from_documents(&champions, &perk_styles, &runes, &spells, &items);
    let icons = data
        .icons
        .into_iter()
        .map(|(kind, paths)| (kind_name(kind), paths))
        .collect();
    Ok(Names {
        names: data.names,
        icons,
    })
}

/// [`names_of`] as JSON.
#[wasm_bindgen]
pub fn game_names(
    champions: &str,
    perk_styles: &str,
    perks: &str,
    spells: &str,
    items: &str,
) -> Result<String, JsError> {
    let names =
        names_of(champions, perk_styles, perks, spells, items).map_err(|e| JsError::new(&e))?;
    serde_json::to_string(&names).map_err(|e| JsError::new(&e.to_string()))
}

/// A champion's ability icon paths by ability id ([`ability_id`]), from its own game data
/// document (`champions/{id}.json`).
pub fn abilities_of(champion: i64, document: &str) -> Result<BTreeMap<i64, String>, String> {
    let detail: ChampionDetail =
        serde_json::from_str(document).map_err(|e| format!("champions/{champion}.json: {e}"))?;
    Ok(detail
        .ability_icons()
        .into_iter()
        .filter_map(|(slot, path)| Some((ability_id(champion, slot)?, path)))
        .collect())
}

/// [`abilities_of`] as JSON.
#[wasm_bindgen]
pub fn ability_icons(champion: i64, document: &str) -> Result<String, JsError> {
    let paths = abilities_of(champion, document).map_err(|e| JsError::new(&e))?;
    serde_json::to_string(&paths).map_err(|e| JsError::new(&e.to_string()))
}

/// What the UI calls each kind (`GameIcons`'s keys).
fn kind_name(kind: IconKind) -> &'static str {
    match kind {
        IconKind::Champion => "champions",
        IconKind::RuneStyle => "rune_styles",
        IconKind::Rune => "runes",
        IconKind::Spell => "spells",
        IconKind::Item => "items",
        IconKind::Ability => "abilities",
    }
}

fn role(name: &str) -> Option<Role> {
    Role::ALL.into_iter().find(|r| r.as_str() == name)
}

/// A window by its name in JSON, `"pooled"` or `"patch"` (ADR-088).
fn window(name: &str) -> Result<Window, JsError> {
    Window::ALL
        .into_iter()
        .find(|w| w.as_str() == name)
        .ok_or_else(|| JsError::new(&format!("{name} is not a window")))
}
