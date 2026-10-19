use serde::{Deserialize, Serialize};

/// Stable error codes: the UI maps them to messages, scripts can match on them.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ErrorCode {
    UnknownCommand,
    InvalidParams,
    NotFound,
    /// Data failed verification (signature, hash, schema) and was not used.
    InvalidData,
    /// A dependency is down or absent: the League client isn't running, the data is offline.
    Unavailable,
    Unsupported,
    Internal,
}

/// What a command returns instead of crashing.
#[derive(
    Clone, Debug, PartialEq, Eq, Serialize, Deserialize, thiserror::Error, schemars::JsonSchema,
)]
#[error("{code:?}: {message}")]
pub struct CommandError {
    pub code: ErrorCode,
    pub message: String,
}

impl CommandError {
    pub fn new(code: ErrorCode, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}
