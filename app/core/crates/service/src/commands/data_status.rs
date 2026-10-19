//! `data.status`: which patch and run the data source serves, after verifying its signature.

use serde::Deserialize;

use crate::ports::DataStatus;
use crate::registry::Command;
use crate::{CommandError, Context};

#[derive(Debug, Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
#[schemars(inline, extend("tsType" = "Record<string, never>"))]
pub struct Params {}

pub fn command() -> Command {
    Command::new(
        "data.status",
        "The newest verified patch the data source serves",
        run,
    )
}

fn run(ctx: &Context, _: Params) -> Result<DataStatus, CommandError> {
    Ok(ctx.builds.status()?)
}
