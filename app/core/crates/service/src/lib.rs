//! Use cases as commands (docs/architecture.md, section 2), over the ports in [`ports`].
//!
//! Entry points (the `stronk-core` CLI, the Tauri shell) only build a [`Context`] from adapters
//! and dispatch commands by id through the [`Registry`].

pub mod commands;
pub mod error;
pub mod ports;
pub mod registry;

use std::sync::Arc;

pub use error::{CommandError, ErrorCode};
pub use registry::{CommandInfo, Registry};

/// The adapters a command can use.
#[derive(Clone)]
pub struct Context {
    pub builds: Arc<dyn ports::BuildSource>,
    pub client: Arc<dyn ports::LeagueClient>,
    pub backups: Arc<dyn ports::Backups>,
}

/// Every command the app has.
pub fn registry() -> Registry {
    Registry::new(vec![
        commands::build_get::command(),
        commands::build_import::command(),
        commands::build_plan::command(),
        commands::champselect_state::command(),
        commands::data_status::command(),
    ])
}
