"""commit-msg hook: the subject line follows Conventional Commits."""

from __future__ import annotations

import re
import sys
from pathlib import Path

TYPES = "feat|fix|refactor|perf|test|docs|build|ci|chore|revert|style"
SUBJECT = re.compile(rf"^({TYPES})(\([a-z0-9._/-]+\))?!?: \S.{{0,98}}$")


def main() -> int:
    subject = Path(sys.argv[1]).read_text().splitlines()[0] if len(sys.argv) > 1 else ""
    if subject.startswith(("Merge ", "Revert ", "fixup! ", "squash! ")) or SUBJECT.match(subject):
        return 0
    print(f"commit-msg: not a Conventional Commit subject: {subject!r}", file=sys.stderr)
    print(f"  expected: <{TYPES}>[(scope)][!]: <summary>", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
