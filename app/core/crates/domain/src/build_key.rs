use serde::{Deserialize, Serialize};

use crate::Role;

/// Which published build file a champion and role need: `{region}/{elo}/{champion}/{role}.json`
/// inside a patch (contracts/README.md).
#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct BuildKey {
    pub region: String,
    pub elo: String,
    pub champion: String,
    pub role: Role,
}

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
#[error("{field} {value:?} is not a safe path segment")]
pub struct InvalidKey {
    pub field: &'static str,
    pub value: String,
}

impl BuildKey {
    /// Every segment is checked, so a key can never point outside the patch directory.
    pub fn new(region: &str, elo: &str, champion: &str, role: Role) -> Result<Self, InvalidKey> {
        for (field, value) in [("region", region), ("elo", elo), ("champion", champion)] {
            if !is_segment(value) {
                return Err(InvalidKey {
                    field,
                    value: value.to_owned(),
                });
            }
        }
        Ok(Self {
            region: region.to_owned(),
            elo: elo.to_owned(),
            champion: champion.to_owned(),
            role,
        })
    }

    /// The file's path inside its patch, as the manifest lists it.
    pub fn path(&self) -> String {
        format!(
            "{}/{}/{}/{}.json",
            self.region,
            self.elo,
            self.champion,
            self.role.as_str()
        )
    }
}

/// As manifest.v1's FileEntry.path segments: no leading '.', no separators.
fn is_segment(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 64
        && !s.starts_with('.')
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b'+' | b'.'))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn builds_the_manifest_path() {
        let key = BuildKey::new("all", "master_plus", "LeeSin", Role::Jungle);
        assert_eq!(
            key.map(|k| k.path()),
            Ok("all/master_plus/LeeSin/JUNGLE.json".to_owned())
        );
    }

    #[test]
    fn rejects_unsafe_segments() {
        for bad in ["", "..", ".hidden", "a/b", "a\\b", "Lee Sin"] {
            assert!(
                BuildKey::new("all", "master_plus", bad, Role::Top).is_err(),
                "{bad}"
            );
        }
    }
}
