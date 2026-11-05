import json
from dataclasses import replace
from pathlib import Path

from crawl_status import Crawl, ago, crawls, table, writing_to
from riot_builders import domain_match

from stronk_pipeline.adapters.match_store import FileMatchStore


def test_lists_each_crawl_of_the_patch_with_its_games_and_whether_it_runs(tmp_path: Path) -> None:
    master = FileMatchStore(tmp_path / "euw1-16.22")
    master.put(replace(domain_match("EUW1_1"), patch="16.22"))
    master.put(replace(domain_match("EUW1_2"), patch="16.22"))
    diamond = FileMatchStore(tmp_path / "euw1-16.22-diamond")
    diamond.set_bracket("diamond")
    FileMatchStore(tmp_path / "euw1-16.21").put(domain_match("EUW1_3"))  # another patch
    params = json.dumps({"platform": "euw1", "out": str(tmp_path / "euw1-16.22-diamond")})
    running = writing_to([f"python stronk-pipeline run crawl.run --params {params}", "zsh"])
    found = crawls(tmp_path, "16.22", running)
    assert [(c.name, c.bracket, c.games, c.running) for c in found] == [
        ("euw1-16.22", "master_plus", 2, False),
        ("euw1-16.22-diamond", "diamond", 0, True),
    ]
    assert found[0].last is not None
    assert found[1].last is None


def test_reads_as_a_table_with_a_total() -> None:
    found = [
        Crawl("kr-16.22", "master_plus", 5594, False, 1000.0),
        Crawl("kr-16.22-diamond", "diamond", 12, True, None),
    ]
    assert table(found, 1000.0 + 9 * 3600).splitlines() == [
        "crawl             bracket      games  running  last game",
        "kr-16.22          master_plus  5,594  no       9 h ago",
        "kr-16.22-diamond  diamond         12  yes      -",
        "total                          5,606",
    ]


def test_says_how_long_ago_in_the_unit_that_reads() -> None:
    assert [ago(s) for s in (30, 600, 7200, 3 * 86400)] == [
        "just now",
        "10 min ago",
        "2 h ago",
        "3 days ago",
    ]
