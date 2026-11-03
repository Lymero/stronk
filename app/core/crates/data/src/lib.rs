//! Published build data (docs/architecture.md, section 5, "Data source").
//!
//! Every source verifies before it returns anything: the patch's `manifest.json` against its
//! minisign signature and the app's public key, the trusted comment against the manifest's
//! patch and run, then each file's size and sha256 against the manifest. Data that fails is
//! an error, never used.

#[cfg(feature = "sources")]
mod backups;
#[cfg(feature = "sources")]
mod directory;
#[cfg(feature = "sources")]
mod http;
mod verify;

#[cfg(feature = "sources")]
use std::path::Path;
#[cfg(feature = "sources")]
use std::sync::Arc;

#[cfg(feature = "sources")]
use stronk_service::ports::{BuildSource, PortError};

#[cfg(feature = "sources")]
pub use backups::{FileBackups, default_backup_dir};
#[cfg(feature = "sources")]
pub use directory::DirectorySource;
#[cfg(feature = "sources")]
pub use http::{HttpSource, REFRESH, default_cache_dir};
pub use verify::{TrustedKey, VerifiedManifest};

#[cfg(feature = "sources")]
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
