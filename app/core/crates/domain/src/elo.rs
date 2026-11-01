//! Elo brackets (ADR-076, ADR-079): which games a build file comes from, named in its path. A
//! bracket is a band of tiers with every band above it, so each one holds the games of those
//! before it: Master+, Diamond+, Emerald+.

/// The bracket a build is read from when none is chosen.
pub const DEFAULT: &str = "master_plus";

/// The brackets the pipeline publishes, highest (and narrowest) first.
pub const KNOWN: [&str; 3] = [DEFAULT, "diamond_plus", "emerald_plus"];

/// `elos` once each, highest first: the known brackets in their order, then any other
/// alphabetically.
pub fn sorted(elos: impl IntoIterator<Item = String>) -> Vec<String> {
    let rank = |e: &str| KNOWN.iter().position(|k| *k == e).unwrap_or(KNOWN.len());
    let mut elos: Vec<String> = elos.into_iter().collect();
    elos.sort_by(|a, b| rank(a).cmp(&rank(b)).then(a.cmp(b)));
    elos.dedup();
    elos
}

/// Where to read a build for `wanted`, in order: the bracket itself, then each wider one, whose
/// games include its own (ADR-079), then each narrower one, closest first, for data published
/// without it. A bracket Stronk doesn't know is read first, then all of [`KNOWN`].
pub fn fallbacks(wanted: &str) -> Vec<&str> {
    match KNOWN.iter().position(|k| *k == wanted) {
        Some(at) => KNOWN
            .iter()
            .skip(at)
            .chain(KNOWN.iter().take(at).rev())
            .copied()
            .collect(),
        None => std::iter::once(wanted).chain(KNOWN).collect(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn brackets_come_highest_first_each_once() {
        let elos = [
            "gold_plus",
            "diamond_plus",
            "master_plus",
            "diamond_plus",
            "diamond",
        ]
        .map(String::from);
        assert_eq!(
            sorted(elos),
            ["master_plus", "diamond_plus", "diamond", "gold_plus"].map(String::from)
        );
    }

    #[test]
    fn a_bracket_without_a_build_falls_back_to_the_wider_ones_then_the_narrower() {
        assert_eq!(
            fallbacks("master_plus"),
            ["master_plus", "diamond_plus", "emerald_plus"]
        );
        assert_eq!(
            fallbacks("diamond_plus"),
            ["diamond_plus", "emerald_plus", "master_plus"]
        );
        // No Emerald+ data on this patch: the closest narrower bracket.
        assert_eq!(
            fallbacks("emerald_plus"),
            ["emerald_plus", "diamond_plus", "master_plus"]
        );
        // Diamond alone, published before ADR-079.
        assert_eq!(
            fallbacks("diamond"),
            ["diamond", "master_plus", "diamond_plus", "emerald_plus"]
        );
    }
}
