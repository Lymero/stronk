use minisign_verify::{PublicKey, Signature};
use sha2::{Digest, Sha256};
use stronk_contracts::build_v1::Build;
use stronk_contracts::champions_v1::Champions;
use stronk_contracts::manifest_v1::{FileEntry, Manifest};
use stronk_domain::{BuildKey, Patch, Window};
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

    /// The elo brackets the manifest has builds for, in either window, highest first.
    pub fn elos(&self) -> Vec<String> {
        stronk_domain::elo::sorted(self.builds().map(|(elo, _)| elo.to_owned()))
    }

    /// The windows the manifest has builds for (ADR-088), pooled first.
    pub fn windows(&self) -> Vec<Window> {
        let found: Vec<Window> = self.builds().map(|(_, window)| window).collect();
        Window::ALL
            .into_iter()
            .filter(|w| found.contains(w))
            .collect()
    }

    /// Each build file's bracket and window: `{region}/{elo}/{champion}/{role}.json` or
    /// `{region}/{elo}/pooled/{champion}/{role}.json`.
    fn builds(&self) -> impl Iterator<Item = (&str, Window)> {
        self.manifest.files.iter().filter_map(|f| {
            match f.path.as_str().split('/').collect::<Vec<_>>().as_slice() {
                [_, elo, _, role] if role.ends_with(".json") => Some((*elo, Window::Patch)),
                [_, elo, "pooled", _, role] if role.ends_with(".json") => {
                    Some((*elo, Window::Pooled))
                }
                _ => None,
            }
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
        let pooled = build.patches.is_some();
        if build.champion.as_str() != key.champion
            || build.patch.as_str() != patch.to_string()
            || pooled != (key.window == Window::Pooled)
        {
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

#[cfg(test)]
mod tests {
    // Tests may panic: that is how they fail.
    #![allow(clippy::unwrap_used, clippy::indexing_slicing)]

    use stronk_domain::Role;

    use super::*;

    /// The contract's example pooling 26.19 and 26.20 at `pooled`, and as 26.20 alone at
    /// `alone`, listed with their hashes.
    fn manifest(pooled: &str, alone: &str) -> (VerifiedManifest, Vec<u8>, Vec<u8>) {
        let example = concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../../../contracts/examples/build.v1.json"
        );
        let mut build: serde_json::Value =
            serde_json::from_slice(&std::fs::read(example).unwrap()).unwrap();
        let pooled_bytes = serde_json::to_vec(&build).unwrap();
        build.as_object_mut().unwrap().remove("patches");
        let alone_bytes = serde_json::to_vec(&build).unwrap();
        let entry = |path: &str, data: &[u8]| serde_json::json!({"path": path, "sha256": hex(&Sha256::digest(data)), "bytes": data.len()});
        let manifest: Manifest = serde_json::from_value(serde_json::json!({
            "schemaVersion": 1, "patch": "26.20", "generatedAt": "2026-11-04T12:00:00Z",
            "runId": "r", "keyId": "0123456789ABCDEF",
            "files": [entry(pooled, &pooled_bytes), entry(alone, &alone_bytes)],
        }))
        .unwrap();
        let verified = VerifiedManifest {
            patch: "26.20".parse().unwrap(),
            manifest,
        };
        (verified, pooled_bytes, alone_bytes)
    }

    fn key(window: Window) -> BuildKey {
        BuildKey::new("euw1", "diamond_plus", "Viego", Role::Jungle)
            .unwrap()
            .in_window(window)
    }

    #[test]
    fn lists_both_windows_pooled_first() {
        let (m, _, _) = manifest(
            "euw1/diamond_plus/pooled/Viego/JUNGLE.json",
            "euw1/diamond_plus/Viego/JUNGLE.json",
        );
        assert_eq!(m.windows(), [Window::Pooled, Window::Patch]);
        assert_eq!(m.elos(), ["diamond_plus"]);
    }

    #[test]
    fn a_build_must_count_the_games_its_path_says() {
        // The pooled file listed where the patch's own belongs, and the other way round.
        let (swapped, pooled, alone) = manifest(
            "euw1/diamond_plus/Viego/JUNGLE.json",
            "euw1/diamond_plus/pooled/Viego/JUNGLE.json",
        );
        for (window, data) in [(Window::Patch, &pooled), (Window::Pooled, &alone)] {
            let refused = swapped.parse_build(&key(window), data);
            assert!(
                matches!(&refused, Err(PortError::Invalid(m)) if m.contains("another build")),
                "{refused:?}"
            );
        }
        let (right, pooled, alone) = manifest(
            "euw1/diamond_plus/pooled/Viego/JUNGLE.json",
            "euw1/diamond_plus/Viego/JUNGLE.json",
        );
        assert!(right.parse_build(&key(Window::Pooled), &pooled).is_ok());
        assert!(right.parse_build(&key(Window::Patch), &alone).is_ok());
    }
}
