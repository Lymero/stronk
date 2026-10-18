//! `build.get`: the verified build file for a champion and role.

use serde::Deserialize;
use stronk_contracts::build_v1::Build;
use stronk_domain::{BuildKey, Patch, Role};

use crate::registry::Command;
use crate::{CommandError, Context, ErrorCode};

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Params {
    pub champion: String,
    pub role: Role,
    /// Defaults to the newest patch the data source has.
    pub patch: Option<Patch>,
    #[serde(default = "all")]
    pub region: String,
    #[serde(default = "master_plus")]
    pub elo: String,
}

fn all() -> String {
    "all".to_owned()
}

fn master_plus() -> String {
    "master_plus".to_owned()
}

pub fn command() -> Command {
    Command::new(
        "build.get",
        "The verified build file for a champion and role",
        run,
    )
}

fn run(ctx: &Context, params: Params) -> Result<Build, CommandError> {
    let key = BuildKey::new(&params.region, &params.elo, &params.champion, params.role)
        .map_err(|e| CommandError::new(ErrorCode::InvalidParams, e.to_string()))?;
    let patch = match params.patch {
        Some(patch) => patch,
        None => ctx.builds.status()?.patch,
    };
    Ok(ctx.builds.build(patch, &key)?)
}
