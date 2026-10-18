//! The League client adapter (docs/architecture.md, section 5).
//!
//! The client writes a lockfile with its port and a per-session password, and serves HTTPS on
//! 127.0.0.1 with a certificate from its own root. [`LcuClient`] trusts exactly one root
//! certificate, given by the caller: `tools/lcu-mock` writes its own next to its lockfile.

mod client;
mod lockfile;
pub mod models;

pub use client::LcuClient;
pub use lockfile::{Lockfile, LockfileError, discover};
