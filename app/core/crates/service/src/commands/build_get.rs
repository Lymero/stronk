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
    let patch = params.patch.map(|p| p.to_string());
    fetch(
        ctx,
        &params.champion,
        params.role,
        patch.as_deref(),
        Some(&params.region),
        Some(&params.elo),
    )
}

/// The verified build file; `None` means the newest patch, `all` regions, `master_plus`.
pub fn fetch(
    ctx: &Context,
    champion: &str,
    role: Role,
    patch: Option<&str>,
    region: Option<&str>,
    elo: Option<&str>,
) -> Result<Build, CommandError> {
    let invalid =
        |e: &dyn std::fmt::Display| CommandError::new(ErrorCode::InvalidParams, e.to_string());
    let key = BuildKey::new(
        region.unwrap_or("all"),
        elo.unwrap_or("master_plus"),
        champion,
        role,
    )
    .map_err(|e| invalid(&e))?;
    let patch: Patch = match patch {
        Some(text) => text.parse().map_err(|e| invalid(&e))?,
        None => ctx.builds.status()?.patch,
    };
    Ok(ctx.builds.build(patch, &key)?)
}
