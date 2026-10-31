//! Summoner spells: a pair's id, and the pair on the player's keys (ADR-043).

pub const FLASH: i64 = 4;

/// A pair's id, whatever its order: `low * 1000 + high`.
pub fn pair_id(a: i64, b: i64) -> i64 {
    a.min(b) * 1_000 + a.max(b)
}

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

#[cfg(test)]
mod tests {
    use super::*;

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
}
