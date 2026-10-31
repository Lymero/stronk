//! Rune pages: a page's rows, the rule's choice row by row (ADR-065), and the client's layout
//! (ADR-059).

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::select::{Candidate, Choice, Label, choose};

/// A whole rune page: perks are the keystone, three primary runes, two secondary runes, then
/// three shards.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize, schemars::JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Page {
    pub primary_style: i64,
    pub sub_style: i64,
    pub perks: Vec<i64>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum RowKind {
    Primary,
    Secondary,
    Shard,
}

/// One rune row: a primary tree's row, a secondary tree's pair, or a shard row. Rows sort
/// primary first, then pairs, then shards.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct RowKey {
    pub kind: RowKind,
    /// The tree, for primary rows and pairs.
    pub style: Option<i64>,
    /// The row within its tree, or the shard row (1 to 3); none for a pair.
    pub row: Option<u64>,
}

/// What `page` has in row `key`: one rune, or the pair smallest first; none when the row
/// belongs to a tree the page doesn't use.
pub fn in_page(page: &Page, key: RowKey) -> Option<Vec<i64>> {
    let at = |i: u64| {
        usize::try_from(i)
            .ok()
            .and_then(|i| page.perks.get(i))
            .copied()
    };
    match key.kind {
        RowKind::Primary if key.style == Some(page.primary_style) => at(key.row?).map(|r| vec![r]),
        RowKind::Secondary if key.style == Some(page.sub_style) => {
            let mut pair = vec![at(4)?, at(5)?];
            pair.sort_unstable();
            Some(pair)
        }
        RowKind::Shard => at(key.row? + 5).map(|r| vec![r]),
        RowKind::Primary | RowKind::Secondary => None,
    }
}

/// A row's choice as one id for comparisons: the rune, or a pair as `low * 100000 + high`.
pub fn perks_id(perks: &[i64]) -> i64 {
    match perks {
        [one] => *one,
        [low, high] => low.saturating_mul(100_000).saturating_add(*high),
        _ => -1,
    }
}

/// Stronk's page with each of its rows chosen by the rule (ADR-065): the page is chosen whole by
/// its keystone; then, row by row (the primary tree's rows, the secondary pair, the shards), the
/// row's choice replaces the page's rune: its best bet against the row's most played rune, else
/// that most played one (a page's rune that trails it is the worse bet). A popular page that
/// changed by a best bet is labelled by its largest. `rows` are each row's options, in row order.
pub fn with_row_bets(
    choice: Choice<Page>,
    rows: &[(RowKey, Vec<Candidate<Vec<i64>>>)],
) -> Choice<Page> {
    let Choice {
        mut value,
        mut label,
    } = choice;
    let mut largest: Option<(f64, Label)> = None;
    for (key, candidates) in rows {
        let applies = match key.kind {
            RowKind::Primary => key.style == Some(value.primary_style),
            RowKind::Secondary => key.style == Some(value.sub_style),
            RowKind::Shard => true,
        };
        if !applies {
            continue;
        }
        let Some(chosen) = choose(candidates) else {
            continue;
        };
        let gain = match chosen.label {
            Label::BestBet { wpa, .. } | Label::ClearlyBetter { wpa, .. } => Some(wpa),
            Label::Popular | Label::Picked => None,
        };
        let at = |i: Option<u64>| i.and_then(|i| usize::try_from(i).ok());
        let placed = match (key.kind, chosen.value.as_slice()) {
            (RowKind::Primary, [rune]) => at(key.row)
                .and_then(|i| value.perks.get_mut(i))
                .map(|p| *p = *rune),
            (RowKind::Shard, [shard]) => at(key.row.map(|r| r + 5))
                .and_then(|i| value.perks.get_mut(i))
                .map(|p| *p = *shard),
            // The same pair in another order is the page's own: it keeps its order.
            (RowKind::Secondary, [low, high]) => value.perks.get_mut(4..6).map(|p| {
                if !(p.contains(low) && p.contains(high)) {
                    p.copy_from_slice(&[*low, *high]);
                }
            }),
            _ => None,
        };
        if let (Some(_), Some(wpa)) = (placed, gain)
            && largest.as_ref().is_none_or(|(w, _)| wpa > *w)
        {
            largest = Some((wpa, chosen.label));
        }
    }
    if let (Label::Popular, Some((_, row_label))) = (label, largest) {
        label = row_label;
    }
    Choice { value, label }
}

/// Whether a rune page is one the client accepts, by the client's own layout (ADR-059): a
/// keystone and one rune per row of the primary tree, two runes from two different rows of
/// another tree, and one shard per shard row. `trees` maps a tree to its rows, keystones first;
/// `shards` holds the shard rows. The reason when it isn't.
pub fn valid_page(
    primary: i64,
    secondary: i64,
    perks: &[i64],
    trees: &BTreeMap<i64, Vec<Vec<i64>>>,
    shards: &[Vec<i64>],
) -> Result<(), String> {
    let (Some(main), Some(side)) = (trees.get(&primary), trees.get(&secondary)) else {
        return Err("unknown rune tree".into());
    };
    if primary == secondary {
        return Err("the secondary tree must differ from the primary".into());
    }
    let [k, r1, r2, r3, s1, s2, f1, f2, f3] = perks else {
        return Err("a page has nine runes".into());
    };
    for (row, rune) in [k, r1, r2, r3].into_iter().enumerate() {
        if !main.get(row).is_some_and(|r| r.contains(rune)) {
            return Err(format!("rune {rune} isn't in row {row} of its tree"));
        }
    }
    let row_of =
        |rune: &i64| (1..side.len()).find(|&i| side.get(i).is_some_and(|r| r.contains(rune)));
    match (row_of(s1), row_of(s2)) {
        (Some(a), Some(b)) if a != b => {}
        (Some(_), Some(_)) => return Err("the two secondary runes share a row".into()),
        _ => return Err("a secondary rune isn't in its tree".into()),
    }
    for (row, shard) in [f1, f2, f3].into_iter().enumerate() {
        if !shards.get(row).is_some_and(|r| r.contains(shard)) {
            return Err(format!("shard {shard} isn't in shard row {}", row + 1));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::select::Comparison;

    const PAGE: [i64; 9] = [8010, 9111, 9104, 8014, 8347, 8304, 5005, 5008, 5001];

    fn page(perks: [i64; 9]) -> Page {
        Page {
            primary_style: 8000,
            sub_style: 8300,
            perks: perks.to_vec(),
        }
    }

    fn key(kind: RowKind, style: Option<i64>, row: Option<u64>) -> RowKey {
        RowKey { kind, style, row }
    }

    /// A row option: `played` games, unclear against `versus` by `wpa` within `ci`.
    fn option(
        perks: &[i64],
        played: u64,
        versus: Option<(i64, f64, (f64, f64))>,
    ) -> Candidate<Vec<i64>> {
        Candidate {
            value: perks.to_vec(),
            id: perks_id(perks),
            played,
            wpa: Some(0.0),
            ci: Some((-0.02, 0.02)),
            too_few: false,
            low_overlap: false,
            unclear: true,
            fragile: false,
            comparison: versus.map(|(versus, wpa, ci)| Comparison {
                versus,
                wpa,
                ci: Some(ci),
            }),
        }
    }

    #[test]
    fn a_page_has_each_row_and_the_pair_smallest_first() {
        let p = page(PAGE);
        let primary = |row| key(RowKind::Primary, Some(8000), Some(row));
        assert_eq!(in_page(&p, primary(3)), Some(vec![8014]));
        assert_eq!(
            in_page(&p, key(RowKind::Primary, Some(8100), Some(3))),
            None
        );
        assert_eq!(
            in_page(&p, key(RowKind::Secondary, Some(8300), None)),
            Some(vec![8304, 8347])
        );
        assert_eq!(
            in_page(&p, key(RowKind::Shard, None, Some(1))),
            Some(vec![5005])
        );
        assert_eq!(perks_id(&[8304, 8347]), 830_408_347);
    }

    #[test]
    fn a_rows_best_bet_replaces_the_pages_rune_and_the_rest_stays() {
        // Lee Sin jungle: Cut Down against Coup de Grace, +2.7 likely between 0.0 and +5.6.
        let rows = [
            (
                key(RowKind::Primary, Some(8000), Some(3)),
                vec![
                    option(&[8014], 2194, None),
                    option(&[8017], 1704, Some((8014, 0.027, (-0.000_05, 0.055_55)))),
                ],
            ),
            (
                key(RowKind::Primary, Some(8100), Some(3)),
                vec![option(&[8135], 68, Some((8106, 0.05, (0.04, 0.06))))],
            ),
            (
                key(RowKind::Shard, None, Some(1)),
                vec![
                    option(&[5005], 3765, None),
                    option(&[5008], 425, Some((5005, 0.013, (-0.04, 0.066)))),
                ],
            ),
        ];
        let popular = |perks| Choice {
            value: page(perks),
            label: Label::Popular,
        };
        // Cut Down takes row 3; the noisy shard and the other tree's row change nothing.
        let chosen = with_row_bets(popular(PAGE), &rows);
        let mut expected = PAGE;
        expected[3] = 8017;
        assert_eq!(chosen.value.perks, expected);
        assert_eq!(
            chosen.label,
            Label::BestBet {
                wpa: 0.027,
                ci: Some((-0.000_05, 0.055_55)),
                games: 1704
            }
        );
        // A page whose shard trails its row's most played one takes the most played.
        let mut trailing = PAGE;
        trailing[6] = 5008;
        assert_eq!(with_row_bets(popular(trailing), &rows).value.perks[6], 5005);
    }

    /// Trees by id, and the shard rows.
    type Layout = (BTreeMap<i64, Vec<Vec<i64>>>, Vec<Vec<i64>>);

    fn layout() -> Layout {
        let trees = BTreeMap::from([
            (
                8000,
                vec![
                    vec![8005, 8010],
                    vec![9111, 8009],
                    vec![9104, 9105],
                    vec![8014, 8017],
                ],
            ),
            (
                8300,
                vec![
                    vec![8369],
                    vec![8304, 8321],
                    vec![8345, 8313],
                    vec![8347, 8410],
                ],
            ),
        ]);
        (
            trees,
            vec![vec![5008, 5005], vec![5008, 5010], vec![5011, 5001]],
        )
    }

    #[test]
    fn a_page_is_valid_only_in_the_clients_layout() {
        let (trees, shards) = layout();
        let ok = [8010, 9111, 9104, 8014, 8304, 8347, 5005, 5008, 5001];
        assert_eq!(valid_page(8000, 8300, &ok, &trees, &shards), Ok(()));
        let with = |i: usize, v: i64| {
            let mut p = ok;
            p[i] = v;
            valid_page(8000, 8300, &p, &trees, &shards)
        };
        assert!(with(0, 9111).is_err()); // not a keystone
        assert!(with(2, 9111).is_err()); // a row 1 rune in row 2
        assert!(with(5, 8321).is_err()); // two secondary runes from the same row
        assert!(with(5, 9104).is_err()); // a secondary rune from the primary tree
        assert!(with(8, 5005).is_err()); // an offense shard in the defense row
        assert!(valid_page(8000, 8000, &ok, &trees, &shards).is_err());
        assert!(valid_page(8000, 8100, &ok, &trees, &shards).is_err()); // unknown tree
        assert!(valid_page(8000, 8300, &ok[..8], &trees, &shards).is_err());
    }
}
