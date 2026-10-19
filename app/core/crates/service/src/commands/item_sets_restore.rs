//! `item_sets.restore`: puts a backup of the player's item sets back into the client, exactly
//! as it was saved. The current sets are backed up first, so a restore can be undone too; a
//! backup from another account, or one that isn't an item set document, is never written.

use serde::{Deserialize, Serialize};

use crate::item_sets::Document;
use crate::registry::Command;
use crate::{CommandError, Context, ErrorCode};

#[derive(Debug, Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "RestoreParams")]
pub struct Params {
    /// A backup file, as `item_sets.backups` lists them or as `build.import` reported.
    pub backup: String,
}

#[derive(Debug, Serialize, PartialEq, Eq, schemars::JsonSchema)]
pub struct Restored {
    pub restored: String,
    /// Item sets in the restored document.
    pub sets: usize,
    /// Where the sets that were replaced were saved first.
    pub previous_backup: String,
}

pub fn command() -> Command {
    Command::new(
        "item_sets.restore",
        "Put a backup of the player's item sets back into the client",
        run,
    )
}

fn run(ctx: &Context, params: Params) -> Result<Restored, CommandError> {
    let bytes = ctx.backups.load(&params.backup)?;
    let text = String::from_utf8(bytes)
        .map_err(|_| CommandError::new(ErrorCode::InvalidData, "the backup is not UTF-8 text"))?;
    let backup = Document::parse(&text, "the backup")?;
    let current_text = ctx.client.item_sets()?; // nothing written if the client can't be read
    let current = Document::parse(&current_text, "the client's item sets")?;
    if backup.account() != current.account() {
        return Err(CommandError::new(
            ErrorCode::InvalidParams,
            "the backup belongs to another account than the one logged in; nothing written",
        ));
    }
    let previous_backup = ctx.backups.save("item-sets", current_text.as_bytes())?;
    ctx.client.save_item_sets(&text)?;
    Ok(Restored {
        restored: params.backup,
        sets: backup.len(),
        previous_backup,
    })
}
