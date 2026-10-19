//! `item_sets.backups`: the local backups of the player's item sets, newest first.

use serde::{Deserialize, Serialize};

use crate::ports::Backup;
use crate::registry::Command;
use crate::{CommandError, Context};

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Params {}

#[derive(Debug, Serialize, PartialEq, Eq)]
pub struct Listed {
    pub backups: Vec<Backup>,
}

pub fn command() -> Command {
    Command::new(
        "item_sets.backups",
        "The local backups of the player's item sets, newest first",
        run,
    )
}

fn run(ctx: &Context, _: Params) -> Result<Listed, CommandError> {
    Ok(Listed {
        backups: ctx.backups.list("item-sets")?,
    })
}
