//! Published build data (docs/architecture.md, section 5, "Data source").
//!
//! Every source verifies before it returns anything: the patch's `manifest.json` against its
//! minisign signature and the app's public key, the trusted comment against the manifest's
//! patch and run, then each file's size and sha256 against the manifest. Data that fails is
//! an error, never used.

mod backups;
mod directory;
mod verify;

pub use backups::{FileBackups, default_backup_dir};
pub use directory::DirectorySource;
pub use verify::{TrustedKey, VerifiedManifest};
