use minisign_verify::{PublicKey, Signature};
use sha2::{Digest, Sha256};
use stronk_contracts::manifest_v1::{FileEntry, Manifest};
use stronk_domain::Patch;
use stronk_service::ports::PortError;

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
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
