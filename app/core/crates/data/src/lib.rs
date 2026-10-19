//! Published build data (docs/architecture.md, section 5, "Data source").
//!
//! Every source verifies before it returns anything: the patch's `manifest.json` against its
//! minisign signature and the app's public key, the trusted comment against the manifest's
//! patch and run, then each file's size and sha256 against the manifest. Data that fails is
//! an error, never used.

mod backups;
mod directory;
mod http;
mod verify;

use std::path::Path;
use std::sync::Arc;

use stronk_service::ports::{BuildSource, PortError};

pub use backups::{FileBackups, default_backup_dir};
pub use directory::DirectorySource;
pub use http::{HttpSource, REFRESH, default_cache_dir};
pub use verify::{TrustedKey, VerifiedManifest};

/// The source a `data.source` setting names: `http(s)://…` is fetched into `cache`
/// ([`HttpSource`]); `dir:<path>`, or any other value, is a local directory.
pub fn open_source(
    setting: &str,
    key: TrustedKey,
    cache: &Path,
) -> Result<Arc<dyn BuildSource>, PortError> {
    if setting.starts_with("http://") || setting.starts_with("https://") {
        return Ok(Arc::new(HttpSource::new(setting, key, cache)?));
    }
    let dir = setting.strip_prefix("dir:").unwrap_or(setting);
    Ok(Arc::new(DirectorySource::new(dir, key)))
}
