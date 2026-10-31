//! Stronk's item set: each slot's block, its choice first and then the slot's other items in
//! Stronk's order (ADR-067, ADR-069, ADR-070), and the purchases (ADR-071, ADR-072).

use std::num::NonZeroU64;

use crate::select::{Ranked, Row, by_judgement};

/// Items in a slot's block of the item set: its choice, then the most played others.
pub const SLOT_ITEMS: usize = 4;
/// Items in the late slot's block, which stands for three or four items.
pub const LATE_ITEMS: usize = 6;
/// An alternative needs this share of its slot's games to be listed in the block.
pub const BLOCK_MIN_SHARE: f64 = 0.02;

/// Items in a slot's block: [`LATE_ITEMS`] for the late slot (ADR-067), else [`SLOT_ITEMS`].
pub fn block_size(late: bool) -> usize {
    if late { LATE_ITEMS } else { SLOT_ITEMS }
}

/// A slot's options with [`BLOCK_MIN_SHARE`] of its games, in Stronk's order.
pub fn block_order(ranked: &Ranked<i64>) -> Vec<i64> {
    let mut rows: Vec<&Row<i64>> = ranked
        .rows
        .iter()
        .filter(|r| r.share >= BLOCK_MIN_SHARE)
        .collect();
    by_judgement(&mut rows);
    rows.iter().map(|r| r.value).collect()
}

/// A block's items after its first: the first `size - 1` of `order` not `taken`.
pub fn block_others(order: &[i64], taken: &[i64], size: usize) -> Vec<i64> {
    order
        .iter()
        .copied()
        .filter(|v| !taken.contains(v))
        .take(size.saturating_sub(1))
        .collect()
}

/// A purchase's items, smallest id first, each once, whatever order they come in.
pub fn purchase_items(items: &[NonZeroU64]) -> Vec<i64> {
    let mut value: Vec<i64> = items
        .iter()
        .map(|i| i64::try_from(i.get()).unwrap_or(-1))
        .collect();
    value.sort_unstable();
    value.dedup();
    value
}

/// One id for a set of items, to match a purchase with the one it is compared with.
pub fn purchase_id(items: &[i64]) -> i64 {
    items
        .iter()
        .fold(0_i64, |id, i| id.wrapping_mul(1_000_003).wrapping_add(*i))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_block_skips_items_other_slots_take() {
        let order = [3026, 6333, 3156, 3053];
        assert_eq!(
            block_others(&order, &[6333], SLOT_ITEMS),
            [3026, 3156, 3053]
        );
        assert_eq!(block_others(&order, &[], 2), [3026]);
        assert!(block_others(&order, &[], 0).is_empty());
        assert_eq!(block_size(true), LATE_ITEMS);
    }

    #[test]
    fn a_purchase_is_its_items_once_in_any_order() {
        let ids = |v: &[u64]| -> Vec<NonZeroU64> {
            v.iter().filter_map(|i| NonZeroU64::new(*i)).collect()
        };
        assert_eq!(purchase_items(&ids(&[1055, 2003, 2003])), [1055, 2003]);
        assert_eq!(
            purchase_id(&purchase_items(&ids(&[2003, 1055]))),
            purchase_id(&[1055, 2003])
        );
    }
}
