//! Pure app logic (docs/architecture.md, section 5): no I/O, no clocks, no panics.

pub mod build_key;
pub mod patch;
pub mod role;

pub use build_key::{BuildKey, InvalidKey};
pub use patch::{InvalidPatch, Patch};
pub use role::Role;
