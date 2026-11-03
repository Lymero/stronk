"""The site's screenshots recompressed losslessly (`just site-shot`): the same pixels in fewer
bytes, so each stays under the repository's 512 KB file limit (`check-added-large-files`)."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

LIMIT = 512 * 1024


def recompress(path: Path) -> int:
    """Saves `path` again at the highest PNG compression; returns its new size in bytes."""
    with Image.open(path) as image:
        image.load()
        image.save(path, optimize=True, compress_level=9)
    return path.stat().st_size


def main(paths: list[str]) -> int:
    too_big = 0
    for name in paths:
        size = recompress(Path(name))
        print(f"{name}: {size // 1024} KB")
        if size > LIMIT:
            print(f"{name} is over {LIMIT // 1024} KB: crop it or show less", file=sys.stderr)
            too_big += 1
    return 1 if too_big else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
