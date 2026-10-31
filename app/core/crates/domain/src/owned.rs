//! What Stronk owns in the client: the rune pages and item sets named with [`PREFIX`]. The
//! player's own are never changed (ADR-043).

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
