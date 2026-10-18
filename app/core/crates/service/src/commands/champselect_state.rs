//! `champselect.state`: the local player's champion select, and the build key it needs.

use serde::{Deserialize, Serialize};
use stronk_domain::Role;

use crate::ports::ChampSelect;
use crate::registry::Command;
use crate::{CommandError, Context};

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Params {}

#[derive(Debug, Serialize, PartialEq, Eq)]
pub struct State {
    /// `None` outside champion select.
    pub session: Option<ChampSelect>,
    /// The champion's key in published data, once one is picked or hovered.
    pub champion: Option<String>,
    pub role: Option<Role>,
}

pub fn command() -> Command {
    Command::new(
        "champselect.state",
        "The local player's champion select",
        run,
    )
}

fn run(ctx: &Context, _: Params) -> Result<State, CommandError> {
    let Some(session) = ctx.client.champ_select()? else {
        return Ok(State {
            session: None,
            champion: None,
            role: None,
        });
    };
    let champion = match session.champion_id {
        0 => None,
        id => Some(ctx.client.champion_key(id)?),
    };
    let role = session.role;
    Ok(State {
        session: Some(session),
        champion,
        role,
    })
}
