//! What to import (ADR-043): the most played whole combination, unless an option is clearly
//! better than it. Pure: the service turns published build files into [`Candidate`]s.

use serde::Serialize;

/// Why an option was chosen; shown next to it in the UI.
#[derive(Clone, Copy, Debug, PartialEq, Serialize)]
#[serde(tag = "label", rename_all = "snake_case")]
pub enum Label {
    /// The most played option (whole page, whole pair, or most picked item).
    Popular,
    /// Beats the popular option head to head and survives false discovery control.
    ClearlyBetter {
        /// Win probability added against the popular option.
        wpa: f64,
    },
}

/// One published option, reduced to what the choice needs.
#[derive(Clone, Debug, PartialEq)]
pub struct Candidate<T> {
    pub value: T,
    /// The option's id in comparisons: keystone for rune pages, item id for items.
    pub id: i64,
    /// Games (or picks) with exactly this option: popularity.
    pub played: u64,
    /// Has a number and is neither `low_sample` nor `low_overlap`.
    pub claimable: bool,
    /// Flagged `no_clear_difference`.
    pub unclear: bool,
    /// Head to head with the most played option: (that option's id, win probability added).
    pub comparison: Option<(i64, f64)>,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Choice<T> {
    pub value: T,
    #[serde(flatten)]
    pub label: Label,
}

/// The popular candidate (most played; ties to the smallest id), or the clearly better one
/// with the largest win impact against it. `None` without candidates.
pub fn choose<T: Clone>(candidates: &[Candidate<T>]) -> Option<Choice<T>> {
    let popular = candidates
        .iter()
        .min_by_key(|c| (std::cmp::Reverse(c.played), c.id))?;
    let better = candidates
        .iter()
        .filter_map(|c| match c.comparison {
            Some((versus, wpa))
                if c.claimable && !c.unclear && versus == popular.id && wpa > 0.0 =>
            {
                Some((c, wpa))
            }
            _ => None,
        })
        .max_by(|(a, x), (b, y)| x.total_cmp(y).then(b.id.cmp(&a.id)));
    Some(match better {
        Some((c, wpa)) => Choice {
            value: c.value.clone(),
            label: Label::ClearlyBetter { wpa },
        },
        None => Choice {
            value: popular.value.clone(),
            label: Label::Popular,
        },
    })
}

pub const FLASH: i64 = 4;

/// The chosen pair on the player's keys: Flash stays on the key it is on now (D or F); a
/// spell already on a key stays there; otherwise the pair's usual order.
pub fn arrange_spells(pair: (i64, i64), current: (i64, i64)) -> (i64, i64) {
    let (a, b) = pair;
    let other = |s: i64| if s == a { b } else { a };
    let has = |s: i64| s == a || s == b;
    if has(FLASH) {
        if current.1 == FLASH {
            return (other(FLASH), FLASH);
        }
        if current.0 == FLASH {
            return (FLASH, other(FLASH));
        }
    }
    if has(current.0) {
        (current.0, other(current.0))
    } else if has(current.1) {
        (other(current.1), current.1)
    } else {
        pair
    }
}

/// A rune page in the client, as far as ownership goes.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PageInfo {
    pub id: i64,
    pub name: String,
    pub editable: bool,
}

pub const PREFIX: &str = "Stronk: ";

/// Stronk owns a page or item set exactly when its name starts with [`PREFIX`].
pub fn is_ours(name: &str) -> bool {
    name.starts_with(PREFIX)
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PagePlan {
    /// Stronk's own pages, deleted before the new one is created.
    pub delete: Vec<i64>,
}

/// Which pages to delete so a new Stronk page fits; `None` when it would take deleting one of
/// the player's. `capacity` is how many editable pages the account may have.
pub fn plan_rune_page(pages: &[PageInfo], capacity: usize) -> Option<PagePlan> {
    let editable: Vec<&PageInfo> = pages.iter().filter(|p| p.editable).collect();
    let ours: Vec<i64> = editable
        .iter()
        .filter(|p| is_ours(&p.name))
        .map(|p| p.id)
        .collect();
    let theirs = editable.len() - ours.len();
    (theirs < capacity).then_some(PagePlan { delete: ours })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn candidate(id: i64, played: u64, comparison: Option<(i64, f64)>) -> Candidate<i64> {
        Candidate {
            value: id,
            id,
            played,
            claimable: true,
            unclear: false,
            comparison,
        }
    }

    #[test]
    fn the_most_played_wins_without_a_clear_alternative() {
        let c = [
            candidate(1, 10, None),
            candidate(2, 30, None),
            candidate(3, 20, Some((2, 0.03))),
        ];
        let mut unclear = c.clone();
        unclear[2].unclear = true;
        assert_eq!(
            choose(&unclear),
            Some(Choice {
                value: 2,
                label: Label::Popular
            })
        );
    }

    #[test]
    fn a_clearly_better_option_replaces_the_popular_one() {
        let c = [
            candidate(1, 10, Some((2, 0.01))),
            candidate(2, 30, None),
            candidate(3, 20, Some((2, 0.03))),
        ];
        assert_eq!(
            choose(&c),
            Some(Choice {
                value: 3,
                label: Label::ClearlyBetter { wpa: 0.03 }
            })
        );
    }

    #[test]
    fn better_means_against_the_popular_option_positive_and_claimable() {
        let worse = [candidate(2, 30, None), candidate(3, 20, Some((2, -0.03)))];
        let elsewhere = [candidate(2, 30, None), candidate(3, 20, Some((9, 0.03)))];
        let mut low_sample = [candidate(2, 30, None), candidate(3, 20, Some((2, 0.03)))];
        low_sample[1].claimable = false;
        for c in [&worse[..], &elsewhere[..], &low_sample[..]] {
            assert_eq!(choose(c).map(|c| c.label), Some(Label::Popular));
        }
        assert_eq!(choose::<i64>(&[]), None);
    }

    #[test]
    fn ties_go_to_the_smallest_id() {
        assert_eq!(
            choose(&[candidate(5, 10, None), candidate(4, 10, None)]).map(|c| c.value),
            Some(4)
        );
    }

    #[test]
    fn flash_stays_on_its_key() {
        let (smite, ignite, ghost) = (11, 14, 6);
        assert_eq!(
            arrange_spells((smite, FLASH), (FLASH, ignite)),
            (FLASH, smite)
        );
        assert_eq!(
            arrange_spells((FLASH, smite), (ignite, FLASH)),
            (smite, FLASH)
        );
        assert_eq!(
            arrange_spells((FLASH, smite), (smite, ghost)),
            (smite, FLASH)
        ); // smite stays on D
        assert_eq!(
            arrange_spells((smite, FLASH), (ghost, ignite)),
            (smite, FLASH)
        ); // usual order
        assert_eq!(
            arrange_spells((ghost, ignite), (ignite, FLASH)),
            (ignite, ghost)
        ); // ignite stays on D
    }

    #[test]
    fn only_stronk_pages_make_room() {
        let page = |id, name: &str, editable| PageInfo {
            id,
            name: name.into(),
            editable,
        };
        let pages = [
            page(1, "Mine", true),
            page(2, "Stronk: Ahri MIDDLE", true),
            page(3, "Preset", false),
        ];
        assert_eq!(
            plan_rune_page(&pages, 2),
            Some(PagePlan { delete: vec![2] })
        );
        let full = [page(1, "Mine", true), page(4, "Also mine", true)];
        assert_eq!(plan_rune_page(&full, 2), None);
        assert_eq!(plan_rune_page(&full, 3), Some(PagePlan { delete: vec![] }));
        assert!(!is_ours("Stronk Ahri") && is_ours("Stronk: Ahri"));
    }
}
