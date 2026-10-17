"""Extract on the real-data corpus: sanity of what real games produce.

Opt-in locally (`just corpus` first), always run in CI once corpus.lock lists files.
"""

from pathlib import Path

import numpy as np
import pytest

from stronk_pipeline.adapters.match_store import FileMatchStore
from stronk_pipeline.domain.extract.tables import extract
from stronk_pipeline.domain.result import Ok

CORPUS = Path(__file__).resolve().parents[3] / "corpus"
CRAWLS = sorted(p for p in CORPUS.glob("*") if (p / "matches").is_dir())

pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(not CRAWLS, reason="no corpus; run `just corpus`"),
]


@pytest.mark.parametrize("crawl", CRAWLS, ids=[p.name for p in CRAWLS])
def test_real_games_extract_cleanly(crawl: Path) -> None:
    store = FileMatchStore(crawl)
    read, statics = store.read_matches(), store.read_static()
    assert isinstance(read, Ok)
    assert isinstance(statics, Ok)
    matches, unreadable = read.value
    assert unreadable == 0
    extracted = extract(matches, statics.value)
    stats = extracted.stats
    assert stats.matches >= 0.95 * len(matches), stats.dropped

    frames = extracted.frames
    assert frames.outcome.mean() == pytest.approx(0.5)  # both sides of every minute
    late = frames.minute >= 15
    gold = frames.features[late, frames.feature_names.index("gold_diff")]
    assert np.corrcoef(gold, frames.outcome[late])[0, 1] > 0.3  # leads win games

    first_items = stats.decisions_by_slot[1]
    assert first_items >= 8 * stats.matches  # most players finish a first item
    assert stats.dropped["unfinished_slot"] <= 0.3 * sum(
        n for slot, n in stats.decisions_by_slot.items() if slot > 0
    )
