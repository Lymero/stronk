//! What the use cases need from the outside world. Adapters live in other crates
//! (`stronk-data`, `stronk-lcu`); tests use in-memory fakes.

use serde::{Deserialize, Serialize};
use serde_json::Value;
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
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
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
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
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

/// The running League client (`stronk-lcu`, or `tools/lcu-mock` in tests).
pub trait LeagueClient: Send + Sync {
    /// `None` outside champion select.
    fn champ_select(&self) -> Result<Option<ChampSelect>, PortError>;
    /// Champion id to its key in published data (`LeeSin`), from the client's own data.
    fn champion_key(&self, champion_id: i64) -> Result<String, PortError>;
    fn rune_pages(&self) -> Result<Vec<PageInfo>, PortError>;
    /// How many editable rune pages the account may have.
    fn rune_page_capacity(&self) -> Result<usize, PortError>;
    fn delete_rune_page(&self, id: i64) -> Result<(), PortError>;
    /// Creates the page and makes it the current one.
    fn create_rune_page(&self, page: &NewRunePage) -> Result<(), PortError>;
    /// The client's item set document, kept whole so everything but Stronk's set goes back
    /// unchanged.
    fn item_sets(&self) -> Result<Value, PortError>;
    fn save_item_sets(&self, document: &Value) -> Result<(), PortError>;
    /// Summoner spells for the current champion select, D then F.
    fn set_spells(&self, spells: (i64, i64)) -> Result<(), PortError>;
}
