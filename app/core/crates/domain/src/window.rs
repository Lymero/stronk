//! Which games a build counts (ADR-088): the newest patch's alone, or earlier patches' pooled
//! with them. A pooled build has more games; an item changed within it is measured on the patch
//! that changed it and later ones only, and says so.

use serde::{Deserialize, Serialize};

/// The patches a build file's games come from, named in its path.
#[derive(
    Clone, Copy, Debug, Default, PartialEq, Eq, Hash, Serialize, Deserialize, schemars::JsonSchema,
)]
#[serde(rename_all = "snake_case")]
pub enum Window {
    /// The patch's games and earlier patches' pooled: `{region}/{elo}/pooled/…`.
    #[default]
    Pooled,
    /// The patch's own games: `{region}/{elo}/…`.
    Patch,
}

impl Window {
    pub const ALL: [Self; 2] = [Self::Pooled, Self::Patch];

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Pooled => "pooled",
            Self::Patch => "patch",
        }
    }

    /// Where to read a build for `self`, in order: itself, then the other window, for data
    /// published without it (every patch before ADR-088 has only its own games).
    pub fn fallbacks(self) -> [Self; 2] {
        match self {
            Self::Pooled => [Self::Pooled, Self::Patch],
            Self::Patch => [Self::Patch, Self::Pooled],
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pooled_by_default_then_the_other_window() {
        assert_eq!(Window::default(), Window::Pooled);
        assert_eq!(Window::Pooled.fallbacks(), [Window::Pooled, Window::Patch]);
        assert_eq!(Window::Patch.fallbacks(), [Window::Patch, Window::Pooled]);
    }
}
