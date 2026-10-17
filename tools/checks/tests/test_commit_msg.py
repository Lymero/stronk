from pathlib import Path

import pytest
from commit_msg import SUBJECT


@pytest.mark.parametrize(
    "subject",
    ["feat: add wpa reference", "fix(pipeline): handle empty tables", "refactor!: rename store"],
)
def test_accepts_conventional_subjects(subject: str) -> None:
    assert SUBJECT.match(subject)


@pytest.mark.parametrize("subject", ["Add stuff", "feat:missing space", "feature: nope", "feat: "])
def test_rejects_other_subjects(subject: str, tmp_path: Path) -> None:
    assert not SUBJECT.match(subject)
