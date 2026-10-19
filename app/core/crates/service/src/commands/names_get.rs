//! `names.get`: display names for champions, runes, spells and items, from the League client's
//! own game data, so the UI shows names instead of ids, in the player's language.

use serde::Deserialize;

use crate::ports::GameNames;
use crate::registry::Command;
use crate::{CommandError, Context};

#[derive(Debug, Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
#[schemars(inline, extend("tsType" = "Record<string, never>"))]
pub struct Params {}

pub fn command() -> Command {
    Command::new(
        "names.get",
        "Names for champions, runes, spells and items, from the League client",
        run,
    )
}

fn run(ctx: &Context, _: Params) -> Result<GameNames, CommandError> {
    Ok(ctx.client.game_names()?)
}
