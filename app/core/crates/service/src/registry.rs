use std::collections::BTreeMap;

use schemars::generate::{Contract, SchemaSettings};
use schemars::{JsonSchema, Schema, SchemaGenerator};
use serde::Serialize;
use serde::de::DeserializeOwned;
use serde_json::{Map, Value, json};

use crate::{CommandError, Context, ErrorCode};

type Handler = Box<dyn Fn(&Context, Value) -> Result<Value, CommandError> + Send + Sync>;
/// The params' schema (as read) and the result's (as written), named types in each generator.
type Describe = fn(&mut SchemaGenerator, &mut SchemaGenerator) -> (Schema, Schema);

/// One use case: an id, a summary, typed params and result, typed errors.
pub struct Command {
    pub id: &'static str,
    pub summary: &'static str,
    handler: Handler,
    describe: Describe,
}

impl Command {
    /// Params are validated from JSON before `run` sees them; unknown fields are rejected by
    /// the params type (`#[serde(deny_unknown_fields)]`).
    pub fn new<P, R, F>(id: &'static str, summary: &'static str, run: F) -> Self
    where
        P: DeserializeOwned + JsonSchema,
        R: Serialize + JsonSchema,
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
            describe: |params, result| (params.subschema_for::<P>(), result.subschema_for::<R>()),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, schemars::JsonSchema)]
pub struct CommandInfo {
    pub id: &'static str,
    pub summary: &'static str,
}

/// A flattened enum gives an object both `properties` and `oneOf` (an import outcome's status
/// and name next to the label's variants); json2ts drops the properties then, so they move
/// into an `allOf` with the variants. Same meaning, all the way down.
fn split_shared_properties(schema: &mut Value) {
    match schema {
        Value::Object(o) => {
            for value in o.values_mut() {
                split_shared_properties(value);
            }
            if o.contains_key("properties") && o.contains_key("oneOf") {
                let mut shared = Map::new();
                for key in ["type", "properties", "required"] {
                    if let Some(v) = o.remove(key) {
                        shared.insert(key.to_owned(), v);
                    }
                }
                let variants = o.remove("oneOf").unwrap_or(Value::Null);
                o.insert("allOf".to_owned(), json!([shared, {"oneOf": variants}]));
            }
        }
        Value::Array(a) => a.iter_mut().for_each(split_shared_properties),
        _ => {}
    }
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

    /// Every command's params and result as one JSON Schema (draft 7, for json2ts): an object with a
    /// `{params, result}` property per command id, the named types in `definitions`. The UI's types
    /// are generated from it (ADR-053). A type named the same in params and results must have
    /// the same schema in both.
    pub fn schema(&self) -> Result<Value, CommandError> {
        let generator = |contract| {
            SchemaSettings::draft07()
                .with(|s| s.contract = contract)
                .into_generator()
        };
        let (mut read, mut written) = (
            generator(Contract::Deserialize),
            generator(Contract::Serialize),
        );
        let mut commands = Map::new();
        for c in self.commands.values() {
            let (params, result) = (c.describe)(&mut read, &mut written);
            let signature = json!({
                "type": "object",
                "description": c.summary,
                "properties": {"params": params, "result": result},
                "required": ["params", "result"],
                "additionalProperties": false,
            });
            commands.insert(c.id.to_owned(), signature);
        }
        // How every command fails, for the UI's `Result`.
        written.subschema_for::<CommandError>();
        let mut defs = read.take_definitions(true);
        for (name, schema) in written.take_definitions(true) {
            match defs.get(&name) {
                Some(other) if *other != schema => {
                    let message = format!("{name} reads and writes differently: rename one");
                    return Err(CommandError::new(ErrorCode::Internal, message));
                }
                _ => {
                    defs.insert(name, schema);
                }
            }
        }
        for schema in defs.values_mut() {
            split_shared_properties(schema);
        }
        let required: Vec<&String> = commands.keys().collect();
        Ok(json!({
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "Commands",
            "description": "Every app command's params and result, by id.",
            "type": "object",
            "properties": commands,
            "required": required,
            "additionalProperties": false,
            "definitions": defs,
        }))
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
