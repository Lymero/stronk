use serde::{Deserialize, Serialize};

/// A position, spelled as the data contract spells it (`TOP`, `JUNGLE`...).
#[derive(
    Clone,
    Copy,
    Debug,
    PartialEq,
    Eq,
    Hash,
    PartialOrd,
    Ord,
    Serialize,
    Deserialize,
    schemars::JsonSchema,
)]
#[serde(rename_all = "UPPERCASE")]
pub enum Role {
    Top,
    Jungle,
    Middle,
    Bottom,
    Utility,
}

impl Role {
    pub const ALL: [Self; 5] = [
        Self::Top,
        Self::Jungle,
        Self::Middle,
        Self::Bottom,
        Self::Utility,
    ];

    /// The League client's `assignedPosition` (`top`, `jungle`, `middle`, `bottom`, `utility`).
    /// Blind pick and custom games assign none: `None`.
    pub fn from_lcu(position: &str) -> Option<Self> {
        match position {
            "top" => Some(Self::Top),
            "jungle" => Some(Self::Jungle),
            "middle" => Some(Self::Middle),
            "bottom" => Some(Self::Bottom),
            "utility" => Some(Self::Utility),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Top => "TOP",
            Self::Jungle => "JUNGLE",
            Self::Middle => "MIDDLE",
            Self::Bottom => "BOTTOM",
            Self::Utility => "UTILITY",
        }
    }

    /// As players say it, as the app shows it: "Jungle", "Mid", "Support"...
    pub fn label(self) -> &'static str {
        match self {
            Self::Top => "Top",
            Self::Jungle => "Jungle",
            Self::Middle => "Mid",
            Self::Bottom => "Bot",
            Self::Utility => "Support",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_lcu_positions() {
        assert_eq!(Role::from_lcu("utility"), Some(Role::Utility));
        assert_eq!(Role::from_lcu(""), None);
        assert_eq!(Role::from_lcu("TOP"), None);
    }

    #[test]
    fn spells_roles_like_the_contract() {
        let spelled: Vec<_> = Role::ALL.iter().map(|r| r.as_str()).collect();
        assert_eq!(spelled, ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]);
    }
}
