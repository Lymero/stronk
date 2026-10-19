//! `build.get`: the verified build file for a champion and role.

use std::borrow::Cow;

use schemars::{JsonSchema, Schema, SchemaGenerator, json_schema};
use serde::{Deserialize, Serialize};
use stronk_contracts::build_v1::Build;
use stronk_domain::{BuildKey, Patch, Role};

use crate::registry::Command;
use crate::{CommandError, Context, ErrorCode};

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
#[schemars(rename = "BuildGetParams")]
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

/// The build file as the contract defines it (`build.v1`): its types come from
/// `contracts/schemas/`, so the command's schema points at them instead of repeating them.
#[derive(Serialize)]
#[serde(transparent)]
pub struct BuildFile(pub Build);

impl JsonSchema for BuildFile {
    fn schema_name() -> Cow<'static, str> {
        "BuildFile".into()
    }

    fn inline_schema() -> bool {
        true
    }

    fn json_schema(_: &mut SchemaGenerator) -> Schema {
        json_schema!({"tsType": "BuildV1.Build"})
    }
}

fn run(ctx: &Context, params: Params) -> Result<BuildFile, CommandError> {
    let patch = params.patch.map(|p| p.to_string());
    fetch(
        ctx,
        &params.champion,
        params.role,
        patch.as_deref(),
        Some(&params.region),
        Some(&params.elo),
    )
    .map(BuildFile)
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
