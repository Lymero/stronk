//! The League client adapter (docs/architecture.md, section 5).
//!
//! The client writes a lockfile with its port and a per-session password, and serves HTTPS on
//! 127.0.0.1 with a certificate from Riot's CA. [`LcuClient`] accepts that certificate per a
//! [`Trust`]: Riot's root by default (`tls.rs` explains the checks), another root for
//! `tools/lcu-mock`, or a pinned certificate as the fallback.

mod client;
mod connect;
mod lockfile;
pub mod models;
pub mod scrub;
pub mod tls;
pub mod watch;

pub use client::{CHAMPION_SUMMARY, LcuClient, SESSION};
pub use connect::{ConnectOptions, connect, connect_or_absent};
pub use lockfile::{Lockfile, LockfileError, discover};
pub use tls::Trust;
pub use watch::{Notice, watch};
