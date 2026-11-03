//! The skill order (ADR-085): an order's id, and how the item set names it. The client can't
//! import a skill order, so the item set's first block carries it into the game.

/// An order's id: its keys as digits, Q 1 to R 4 (`["Q", "E", "W"]` is 132). Anything else
/// counts as 0, which no published order has.
pub fn id(keys: &[String]) -> i64 {
    keys.iter().fold(0, |id, key| {
        let digit = match key.as_str() {
            "Q" => 1,
            "W" => 2,
            "E" => 3,
            "R" => 4,
            _ => 0,
        };
        id * 10 + digit
    })
}

/// What the item set's first block adds to its name: "Q W E Q · max Q > E > W", either part
/// alone when the other is missing; None without either.
pub fn note(levels: Option<&[String]>, max: Option<&[String]>) -> Option<String> {
    let levels = levels.filter(|l| !l.is_empty()).map(|l| l.join(" "));
    let max = max
        .filter(|m| !m.is_empty())
        .map(|m| format!("max {}", m.join(" > ")));
    match (levels, max) {
        (Some(l), Some(m)) => Some(format!("{l} · {m}")),
        (l, m) => l.or(m),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn keys(s: &str) -> Vec<String> {
        s.split(' ').map(str::to_owned).collect()
    }

    #[test]
    fn an_orders_id_is_its_keys_as_digits() {
        assert_eq!(id(&keys("Q W E Q")), 1231);
        assert_eq!(id(&keys("R Q W E")), 4123);
        assert_ne!(id(&keys("Q E W")), id(&keys("Q W E")));
    }

    #[test]
    fn the_note_reads_the_first_levels_then_the_max_order() {
        let (levels, max) = (keys("Q W E Q"), keys("Q E W"));
        assert_eq!(
            note(Some(&levels), Some(&max)).as_deref(),
            Some("Q W E Q · max Q > E > W")
        );
        assert_eq!(note(Some(&levels), None).as_deref(), Some("Q W E Q"));
        assert_eq!(note(None, Some(&max)).as_deref(), Some("max Q > E > W"));
        assert_eq!(note(None, Some(&[])), None);
    }
}
