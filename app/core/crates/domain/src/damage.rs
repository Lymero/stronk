//! The enemy team's damage (ADR-074): physical, mixed or magic, from the champions' damage
//! ratings and the cuts the data publishes, so the app classifies a team as the pipeline did.

use serde::{Deserialize, Serialize};

/// What kind of damage an enemy team deals.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Against {
    Physical,
    Mixed,
    Magic,
}

impl Against {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Physical => "physical",
            Self::Mixed => "mixed",
            Self::Magic => "magic",
        }
    }
}

/// Enemy picks needed before their damage is read: with fewer, one pick decides too much, and
/// boots are chosen over every game.
pub const ENEMIES_KNOWN: usize = 3;

/// The enemy team's damage from the ratings (`attack`, `magic`) of the enemies picked so far:
/// its magic share against the cuts. None with fewer than [`ENEMIES_KNOWN`] rated enemies.
pub fn against(
    enemies: &[i64],
    ratings: impl Fn(i64) -> Option<(u64, u64)>,
    physical_below: f64,
    magic_from: f64,
) -> Option<Against> {
    let rated: Vec<(u64, u64)> = enemies.iter().filter_map(|&id| ratings(id)).collect();
    if rated.len() < ENEMIES_KNOWN {
        return None;
    }
    let attack: u64 = rated.iter().map(|r| r.0).sum();
    let magic: u64 = rated.iter().map(|r| r.1).sum();
    #[allow(clippy::cast_precision_loss)] // ratings are 0 to 10
    let share = if attack + magic == 0 {
        0.5
    } else {
        magic as f64 / (attack + magic) as f64
    };
    Some(if share < physical_below {
        Against::Physical
    } else if share >= magic_from {
        Against::Magic
    } else {
        Against::Mixed
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rating(id: i64) -> Option<(u64, u64)> {
        match id {
            1 => Some((8, 2)), // a fighter
            2 => Some((2, 9)), // a mage
            3 => Some((5, 5)),
            _ => None,
        }
    }

    #[test]
    fn a_team_is_read_from_its_ratings_against_the_cuts() {
        assert_eq!(
            against(&[1, 1, 1], rating, 0.43, 0.5),
            Some(Against::Physical)
        );
        assert_eq!(against(&[2, 2, 1], rating, 0.43, 0.5), Some(Against::Magic));
        assert_eq!(
            against(&[1, 1, 2, 3], rating, 0.43, 0.5),
            Some(Against::Mixed)
        ); // 18 of 41
    }

    #[test]
    fn fewer_than_three_rated_enemies_read_nothing() {
        assert_eq!(against(&[2, 2], rating, 0.43, 0.5), None);
        assert_eq!(against(&[2, 2, 99], rating, 0.43, 0.5), None); // 99 has no rating
    }
}
