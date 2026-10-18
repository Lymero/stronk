use std::collections::BTreeMap;

use serde::Serialize;
use serde::de::DeserializeOwned;
use serde_json::Value;

use crate::{CommandError, Context, ErrorCode};

type Handler = Box<dyn Fn(&Context, Value) -> Result<Value, CommandError> + Send + Sync>;

/// One use case: an id, a summary, typed params and result, typed errors.
pub struct Command {
    pub id: &'static str,
    pub summary: &'static str,
    handler: Handler,
}

impl Command {
    /// Params are validated from JSON before `run` sees them; unknown fields are rejected by
    /// the params type (`#[serde(deny_unknown_fields)]`).
    pub fn new<P, R, F>(id: &'static str, summary: &'static str, run: F) -> Self
    where
        P: DeserializeOwned,
        R: Serialize,
        F: Fn(&Context, P) -> Result<R, CommandError> + Send + Sync + 'static,
    {
        let handler = move |ctx: &Context, params: Value| {
            let params: P = serde_json::from_value(params)
                .map_err(|e| CommandError::new(ErrorCode::InvalidParams, e.to_string()))?;
            let result = run(ctx, params)?;
            serde_json::to_value(result)
                .map_err(|e| CommandError::new(ErrorCode::Internal, e.to_string()))
        };
        Self {
            id,
            summary,
            handler: Box::new(handler),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct CommandInfo {
    pub id: &'static str,
    pub summary: &'static str,
}

/// Every command, by id. Entry points only call [`Registry::run`].
pub struct Registry {
    commands: BTreeMap<&'static str, Command>,
}

impl Registry {
    pub fn new(commands: Vec<Command>) -> Self {
        Self {
            commands: commands.into_iter().map(|c| (c.id, c)).collect(),
        }
    }

    pub fn list(&self) -> Vec<CommandInfo> {
        self.commands
            .values()
            .map(|c| CommandInfo {
                id: c.id,
                summary: c.summary,
            })
            .collect()
    }

    pub fn run(&self, ctx: &Context, id: &str, params: Value) -> Result<Value, CommandError> {
        let command = self.commands.get(id).ok_or_else(|| {
            let known: Vec<_> = self.commands.keys().copied().collect();
            let message = format!("unknown command {id:?}; known: {}", known.join(", "));
            CommandError::new(ErrorCode::UnknownCommand, message)
        })?;
        (command.handler)(ctx, params)
    }
}
