"""The site's screenshots as lossless WebP (`just site-shot`): the same pixels as Playwright's
PNGs in about half the bytes, for visitors and for the repository's 512 KB file limit
(`check-added-large-files`).

    site_webp.py <out dir> <screenshot.png>...
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

LIMIT = 512 * 1024


def convert(png: Path, out: Path) -> Path:
    """Writes `png` as `<out>/<name>.webp`, lossless; returns the WebP's path."""
    webp = out / f"{png.stem}.webp"
    with Image.open(png) as image:
        image.save(webp, "WEBP", lossless=True, quality=100, method=6)
    return webp


def main(args: list[str]) -> int:
    out, pngs = Path(args[0]), [Path(a) for a in args[1:]]
    out.mkdir(parents=True, exist_ok=True)
    too_big = 0
    for png in pngs:
        webp = convert(png, out)
        size = webp.stat().st_size
        print(f"{webp}: {size // 1024} KB (PNG {png.stat().st_size // 1024} KB)")
        if size > LIMIT:
            print(f"{webp} is over {LIMIT // 1024} KB: crop it or show less", file=sys.stderr)
            too_big += 1
    return 1 if too_big else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
