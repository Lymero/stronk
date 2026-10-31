use std::fs;
use std::io::ErrorKind;
use std::path::{Path, PathBuf};

use stronk_contracts::build_v1::Build;
use stronk_contracts::champions_v1::Champions;
use stronk_domain::{BuildKey, Patch};
use stronk_service::ports::{BuildSource, CHAMPIONS, DataStatus, PortError};

use crate::verify::{TrustedKey, VerifiedManifest};

/// Published data in a local directory with the CDN's layout (`dist/data`, `fixtures/data`):
/// `{patch}/manifest.json`, `{patch}/manifest.json.minisig`, `{patch}/{region}/...`.
pub struct DirectorySource {
    root: PathBuf,
    key: TrustedKey,
}

impl DirectorySource {
    pub fn new(root: impl Into<PathBuf>, key: TrustedKey) -> Self {
        Self {
            root: root.into(),
            key,
        }
    }

    fn newest_patch(&self) -> Result<Patch, PortError> {
        let entries = fs::read_dir(&self.root).map_err(|e| unavailable(&self.root, &e))?;
        entries
            .filter_map(Result::ok)
            .filter(|e| e.path().join("manifest.json").is_file())
            .filter_map(|e| e.file_name().to_str()?.parse::<Patch>().ok())
            .max()
            .ok_or_else(|| PortError::NotFound(format!("no patch in {}", self.root.display())))
    }

    fn manifest(&self, patch: Patch) -> Result<VerifiedManifest, PortError> {
        let dir = self.root.join(patch.to_string());
        let manifest = read(&dir.join("manifest.json"))?;
        let signature = read(&dir.join("manifest.json.minisig"))?;
        VerifiedManifest::verify(&self.key, patch, &manifest, &signature)
    }
}

impl BuildSource for DirectorySource {
    fn status(&self) -> Result<DataStatus, PortError> {
        let verified = self.manifest(self.newest_patch()?)?;
        Ok(DataStatus {
            patch: verified.patch,
            run_id: verified.manifest.run_id.to_string(),
            key_id: verified.manifest.key_id.to_string(),
            files: verified.manifest.files.len(),
        })
    }

    fn build(&self, patch: Patch, key: &BuildKey) -> Result<Build, PortError> {
        let verified = self.manifest(patch)?;
        let path = key.path();
        if verified.entry(&path).is_none() {
            return Err(PortError::NotFound(format!("{patch} {path}")));
        }
        let data = read(&self.root.join(patch.to_string()).join(&path))?;
        verified.parse_build(key, &data)
    }

    fn champions(&self, patch: Patch) -> Result<Champions, PortError> {
        let verified = self.manifest(patch)?;
        if verified.entry(CHAMPIONS).is_none() {
            return Err(PortError::NotFound(format!("{patch} {CHAMPIONS}")));
        }
        let data = read(&self.root.join(patch.to_string()).join(CHAMPIONS))?;
        verified.parse_champions(&data)
    }
}

fn read(path: &Path) -> Result<Vec<u8>, PortError> {
    fs::read(path).map_err(|e| match e.kind() {
        ErrorKind::NotFound => PortError::NotFound(path.display().to_string()),
        _ => unavailable(path, &e),
    })
}

fn unavailable(path: &Path, e: &std::io::Error) -> PortError {
    PortError::Unavailable(format!("{}: {e}", path.display()))
}
