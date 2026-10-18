use std::fmt;
use std::str::FromStr;

use serde::{Deserialize, Serialize};

/// A game patch, `major.minor` (`16.20`), as published data names it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct Patch {
    pub major: u16,
    pub minor: u16,
}

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
#[error("not a patch: {0:?}")]
pub struct InvalidPatch(pub String);

impl Patch {
    /// The patch of a client or game version such as `16.20.715.1234`.
    pub fn from_version(version: &str) -> Result<Self, InvalidPatch> {
        let mut parts = version.split('.');
        match (parts.next(), parts.next()) {
            (Some(major), Some(minor)) => format!("{major}.{minor}").parse(),
            _ => Err(InvalidPatch(version.to_owned())),
        }
    }
}

impl FromStr for Patch {
    type Err = InvalidPatch;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let invalid = || InvalidPatch(s.to_owned());
        let (major, minor) = s.split_once('.').ok_or_else(invalid)?;
        let number = |part: &str| -> Result<u16, InvalidPatch> {
            if part.is_empty() || part.len() > 3 || !part.bytes().all(|b| b.is_ascii_digit()) {
                return Err(invalid());
            }
            part.parse().map_err(|_| invalid())
        };
        Ok(Self {
            major: number(major)?,
            minor: number(minor)?,
        })
    }
}

impl fmt::Display for Patch {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}.{}", self.major, self.minor)
    }
}

impl TryFrom<String> for Patch {
    type Error = InvalidPatch;
    fn try_from(s: String) -> Result<Self, Self::Error> {
        s.parse()
    }
}

impl From<Patch> for String {
    fn from(p: Patch) -> Self {
        p.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_and_prints() {
        assert_eq!(
            "16.20".parse(),
            Ok(Patch {
                major: 16,
                minor: 20
            })
        );
        assert_eq!(
            Patch {
                major: 16,
                minor: 5
            }
            .to_string(),
            "16.5"
        );
    }

    #[test]
    fn rejects_what_the_contract_rejects() {
        for bad in ["16", "16.", ".20", "16.20.1", "1234.1", "a.b", "16.+2", ""] {
            assert!(bad.parse::<Patch>().is_err(), "{bad}");
        }
    }

    #[test]
    fn reads_client_versions() {
        assert_eq!(
            Patch::from_version("16.20.715.1234"),
            Ok(Patch {
                major: 16,
                minor: 20
            })
        );
        assert!(Patch::from_version("16").is_err());
    }

    #[test]
    fn orders_numerically() {
        assert!("16.9".parse::<Patch>().unwrap() < "16.10".parse().unwrap());
    }
}
