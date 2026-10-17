from riot_builders import domain_static

STATIC = domain_static()


def test_completed_items_exclude_boots_components_champion_and_other_maps() -> None:
    assert STATIC.completed_items == {3071, 6333, 3031}


def test_components_are_everything_in_a_completed_recipe() -> None:
    assert STATIC.components == {1036, 1028, 1037, 1038, 3133, 3044}
    assert 1001 not in STATIC.components  # boots build into boots only


def test_recipe_tree_goes_all_the_way_down() -> None:
    assert STATIC.recipe_tree(3071) == {3044, 3133, 1036, 1028}
    assert STATIC.recipe_tree(1036) == frozenset()


def test_items_built_from_components() -> None:
    assert STATIC.items_built_from([3133]) == {3071, 6333}
    assert STATIC.items_built_from([1038]) == {3031}
    assert STATIC.items_built_from([1038, 1028]) == frozenset()


def test_champion_class_is_the_main_tag() -> None:
    assert STATIC.champions[1].champion_class == "fighter"
    assert STATIC.champions[2].champion_class == "mage"
