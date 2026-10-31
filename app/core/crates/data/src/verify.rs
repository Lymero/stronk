use minisign_verify::{PublicKey, Signature};
use sha2::{Digest, Sha256};
use stronk_contracts::build_v1::Build;
use stronk_contracts::champions_v1::Champions;
use stronk_contracts::manifest_v1::{FileEntry, Manifest};
use stronk_domain::{BuildKey, Patch};
use stronk_service::ports::{CHAMPIONS, PortError};

/// The public key the app trusts for published data.
pub struct TrustedKey(PublicKey);

impl TrustedKey {
    /// A minisign public key file (`untrusted comment: ...` then the key) or its key line.
    pub fn decode(text: &str) -> Result<Self, PortError> {
        let line = text
            .lines()
            .rfind(|l| !l.trim().is_empty())
            .unwrap_or_default();
        PublicKey::from_base64(line.trim())
            .map(Self)
            .map_err(|e| PortError::Invalid(format!("public key: {e}")))
    }
}

/// A manifest whose signature, trusted comment and patch all checked out.
#[derive(Debug, Clone)]
pub struct VerifiedManifest {
    pub patch: Patch,
    pub manifest: Manifest,
}

impl VerifiedManifest {
    pub fn verify(
        key: &TrustedKey,
        patch: Patch,
        manifest: &[u8],
        signature: &[u8],
    ) -> Result<Self, PortError> {
        let invalid = |what: &str| PortError::Invalid(format!("{patch} manifest: {what}"));
        let signature = std::str::from_utf8(signature)
            .ok()
            .and_then(|s| Signature::decode(s).ok())
            .ok_or_else(|| invalid("unreadable signature"))?;
        key.0
            .verify(manifest, &signature, false)
            .map_err(|e| invalid(&format!("signature rejected ({e})")))?;
        let parsed: Manifest = serde_json::from_slice(manifest)
            .map_err(|e| invalid(&format!("not a manifest.v1 ({e})")))?;
        if parsed.patch.as_str() != patch.to_string() {
            return Err(invalid(&format!("lists patch {}", parsed.patch.as_str())));
        }
        // The comment is signed too: it ties the signature to this patch and run, so a valid
        // manifest can't be replayed under another patch's directory.
        let expected = format!(
            "stronk manifest v1 patch={patch} runId={}",
            parsed.run_id.as_str()
        );
        if signature.trusted_comment() != expected {
            return Err(invalid("trusted comment doesn't match the manifest"));
        }
        Ok(Self {
            patch,
            manifest: parsed,
        })
    }

    pub fn entry(&self, path: &str) -> Option<&FileEntry> {
        self.manifest.files.iter().find(|f| f.path.as_str() == path)
    }

    /// `data` if it is the file the manifest lists at `path`, byte for byte.
    pub fn check_file<'a>(&self, path: &str, data: &'a [u8]) -> Result<&'a [u8], PortError> {
        let entry = self
            .entry(path)
            .ok_or_else(|| PortError::NotFound(format!("{} {path}", self.patch)))?;
        let digest = hex(&Sha256::digest(data));
        if data.len() as u64 != entry.bytes || digest != entry.sha256.as_str() {
            return Err(PortError::Invalid(format!(
                "{} {path}: hash mismatch",
                self.patch
            )));
        }
        Ok(data)
    }

    /// The build `data` holds, if it is the file the manifest lists for `key` and describes
    /// that champion on this patch.
    pub fn parse_build(&self, key: &BuildKey, data: &[u8]) -> Result<Build, PortError> {
        let (patch, path) = (self.patch, key.path());
        let build: Build = serde_json::from_slice(self.check_file(&path, data)?)
            .map_err(|e| PortError::Invalid(format!("{patch} {path}: not a build.v1 ({e})")))?;
        if build.champion.as_str() != key.champion || build.patch.as_str() != patch.to_string() {
            return Err(PortError::Invalid(format!(
                "{patch} {path}: describes another build"
            )));
        }
        Ok(build)
    }
}

impl VerifiedManifest {
    /// The champion ratings `data` holds, if it is the file the manifest lists at
    /// [`CHAMPIONS`] and describes this patch (ADR-074).
    pub fn parse_champions(&self, data: &[u8]) -> Result<Champions, PortError> {
        let patch = self.patch;
        let champions: Champions = serde_json::from_slice(self.check_file(CHAMPIONS, data)?)
            .map_err(|e| {
                PortError::Invalid(format!("{patch} {CHAMPIONS}: not a champions.v1 ({e})"))
            })?;
        if champions.patch.as_str() != patch.to_string() {
            return Err(PortError::Invalid(format!(
                "{patch} {CHAMPIONS}: another patch"
            )));
        }
        Ok(champions)
    }
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
