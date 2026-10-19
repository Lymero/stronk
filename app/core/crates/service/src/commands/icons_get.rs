//! `icons.get`: icons for champions, runes, spells and items, from the League client's own game
//! data, as `data:` URLs the UI can show without reaching the client itself (ADR-051).

use std::collections::BTreeMap;

use base64::Engine as _;
use serde::{Deserialize, Serialize};

use crate::ports::{IconKind, PortError};
use crate::registry::Command;
use crate::{CommandError, Context, ErrorCode};

/// The most ids one call takes: a champion select view needs a few dozen.
pub const MAX_IDS: usize = 200;

/// The ids wanted, by kind.
#[derive(Debug, Default, Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields, default)]
#[schemars(rename = "IconsParams")]
pub struct Params {
    pub champions: Vec<i64>,
    pub rune_styles: Vec<i64>,
    pub runes: Vec<i64>,
    pub spells: Vec<i64>,
    pub items: Vec<i64>,
}

/// `data:` URLs by id, by kind; ids the client has no icon for are left out.
#[derive(Debug, Default, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub struct Icons {
    pub champions: BTreeMap<i64, String>,
    pub rune_styles: BTreeMap<i64, String>,
    pub runes: BTreeMap<i64, String>,
    pub spells: BTreeMap<i64, String>,
    pub items: BTreeMap<i64, String>,
}

pub fn command() -> Command {
    Command::new(
        "icons.get",
        "Icons for champions, runes, spells and items, from the League client",
        run,
    )
}

fn run(ctx: &Context, params: Params) -> Result<Icons, CommandError> {
    let total = params.champions.len()
        + params.rune_styles.len()
        + params.runes.len()
        + params.spells.len()
        + params.items.len();
    if total > MAX_IDS {
        return Err(CommandError::new(
            ErrorCode::InvalidParams,
            format!("{total} icons asked for, at most {MAX_IDS} per call"),
        ));
    }
    let mut icons = Icons::default();
    for (kind, ids, out) in [
        (IconKind::Champion, &params.champions, &mut icons.champions),
        (
            IconKind::RuneStyle,
            &params.rune_styles,
            &mut icons.rune_styles,
        ),
        (IconKind::Rune, &params.runes, &mut icons.runes),
        (IconKind::Spell, &params.spells, &mut icons.spells),
        (IconKind::Item, &params.items, &mut icons.items),
    ] {
        for &id in ids {
            if out.contains_key(&id) {
                continue;
            }
            match ctx.client.icon(kind, id) {
                Ok(Some(icon)) => {
                    let data = base64::engine::general_purpose::STANDARD.encode(&icon.bytes);
                    out.insert(id, format!("data:{};base64,{data}", icon.mime));
                }
                // Cosmetic: an icon missing or not an image is left out, the UI shows a stand-in.
                Ok(None) | Err(PortError::NotFound(_) | PortError::Invalid(_)) => {}
                // The client is gone: asking for the rest would only wait on each.
                Err(e @ PortError::Unavailable(_)) => return Err(e.into()),
            }
        }
    }
    Ok(icons)
}
