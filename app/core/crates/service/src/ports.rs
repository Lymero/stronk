//! What the use cases need from the outside world. Adapters live in other crates
//! (`stronk-data`, `stronk-lcu`); tests use in-memory fakes.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use stronk_contracts::build_v1::Build;
use stronk_domain::select::PageInfo;
use stronk_domain::{BuildKey, Patch, Role};

use crate::{CommandError, ErrorCode};

/// Why a port call failed.
#[derive(Clone, Debug, PartialEq, Eq, thiserror::Error)]
pub enum PortError {
    #[error("not found: {0}")]
    NotFound(String),
    /// Present but rejected: bad signature, hash mismatch, invalid JSON.
    #[error("invalid: {0}")]
    Invalid(String),
    #[error("unavailable: {0}")]
    Unavailable(String),
}

impl From<PortError> for CommandError {
    fn from(e: PortError) -> Self {
        let code = match &e {
            PortError::NotFound(_) => ErrorCode::NotFound,
            PortError::Invalid(_) => ErrorCode::InvalidData,
            PortError::Unavailable(_) => ErrorCode::Unavailable,
        };
        Self::new(code, e.to_string())
    }
}

/// A patch's verified manifest: the signature checked against the app's key.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, schemars::JsonSchema)]
pub struct DataStatus {
    pub patch: Patch,
    pub run_id: String,
    pub key_id: String,
    pub files: usize,
}

/// Published build files (docs/architecture.md, section 5, "Data source"). Every
/// implementation verifies the signed manifest and each file's hash before returning it.
pub trait BuildSource: Send + Sync {
    /// The newest patch the source has, verified.
    fn status(&self) -> Result<DataStatus, PortError>;
    fn build(&self, patch: Patch, key: &BuildKey) -> Result<Build, PortError>;
}

/// The local player's champion select, as far as the app needs it.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize, schemars::JsonSchema)]
pub struct ChampSelect {
    /// Champion id, 0 while none is picked or hovered.
    pub champion_id: i64,
    /// Locked in, not just hovered.
    pub locked: bool,
    pub role: Option<Role>,
    pub phase: String,
    /// The player's summoner spells now, D then F.
    pub spells: Option<(i64, i64)>,
}

/// A rune page to create.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct NewRunePage {
    pub name: String,
    pub primary_style: i64,
    pub sub_style: i64,
    /// Nine: four primary, two secondary, three shards.
    pub perks: Vec<i64>,
}

/// Display names by id, from the client's own game data, so in the player's language
/// (`names.get`).
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub struct GameNames {
    pub champions: BTreeMap<i64, String>,
    /// Rune trees (Precision, Domination…).
    pub rune_styles: BTreeMap<i64, String>,
    /// Runes and stat shards.
    pub runes: BTreeMap<i64, String>,
    pub spells: BTreeMap<i64, String>,
    pub items: BTreeMap<i64, String>,
    /// Each tree's rows as the client shows them: keystones, then the three rows after them.
    pub rune_trees: BTreeMap<i64, Vec<Vec<i64>>>,
    /// The stat shard rows: offense, flex, defense.
    pub shard_rows: Vec<Vec<i64>>,
}

/// What an icon is of (`icons.get`).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum IconKind {
    Champion,
    RuneStyle,
    Rune,
    Spell,
    Item,
}

/// An image from the client's game data, checked to be one: PNG, JPEG or WebP, and small.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Icon {
    pub mime: &'static str,
    pub bytes: Vec<u8>,
}

/// The running League client (`stronk-lcu`, or `tools/lcu-mock` in tests).
pub trait LeagueClient: Send + Sync {
    /// `None` outside champion select.
    fn champ_select(&self) -> Result<Option<ChampSelect>, PortError>;
    /// Champion id to its key in published data (`LeeSin`), from the client's own data.
    fn champion_key(&self, champion_id: i64) -> Result<String, PortError>;
    /// Names for champions, runes, spells and items, from the client's game data.
    fn game_names(&self) -> Result<GameNames, PortError>;
    /// The icon the client's game data gives for `id`; `None` when it gives none.
    fn icon(&self, kind: IconKind, id: i64) -> Result<Option<Icon>, PortError>;
    fn rune_pages(&self) -> Result<Vec<PageInfo>, PortError>;
    /// How many editable rune pages the account may have.
    fn rune_page_capacity(&self) -> Result<usize, PortError>;
    fn delete_rune_page(&self, id: i64) -> Result<(), PortError>;
    /// Creates the page and makes it the current one.
    fn create_rune_page(&self, page: &NewRunePage) -> Result<(), PortError>;
    /// The client's item set document, as the raw JSON text it sent: the player's sets go back
    /// byte for byte, never decoded and re-encoded (ADR-043).
    fn item_sets(&self) -> Result<String, PortError>;
    fn save_item_sets(&self, document: &str) -> Result<(), PortError>;
    /// Summoner spells for the current champion select, D then F.
    fn set_spells(&self, spells: (i64, i64)) -> Result<(), PortError>;
}

/// One local backup.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub struct Backup {
    /// What [`Backups::load`] takes.
    pub location: String,
    /// When it was saved, in milliseconds since the Unix epoch, when known.
    pub saved_at_ms: Option<u64>,
}

/// Local copies of what an import replaces, written before each write (ADR-043).
pub trait Backups: Send + Sync {
    /// Saves `data` as the newest backup of `kind` (for example `item-sets`); returns where.
    fn save(&self, kind: &str, data: &[u8]) -> Result<String, PortError>;
    /// The backups of `kind`, newest first.
    fn list(&self, kind: &str) -> Result<Vec<Backup>, PortError>;
    /// A backup's bytes, exactly as saved; `location` is one [`Backups::save`] or
    /// [`Backups::list`] returned, or a backup file the user points to.
    fn load(&self, location: &str) -> Result<Vec<u8>, PortError>;
}
