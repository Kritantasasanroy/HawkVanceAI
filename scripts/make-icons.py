"""Builds every icon the app and the website need, from one source image.

Run it after changing the logo:

    apps/engine/.venv/Scripts/python.exe scripts/make-icons.py

Source, in order of preference:

  1. assets/hawkvance-logo.png   the real artwork, if it has been dropped in
  2. assets/hawkvance-mark.svg   the drawn fallback, rendered through Chrome

A square PNG of at least 512x512 is ideal. Anything larger is fine; anything
smaller is upscaled and will look soft in the installer header.

The area outside the mark is made transparent by flooding inwards from the
border. Only pixels connected to the edge are cleared, so the white of the eye
and the beak stay white instead of punching holes through the artwork.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ARTWORK = ROOT / "assets" / "hawkvance-logo.png"
# A file saved from somewhere else often keeps its original spacing. Accepted so dropping in a
# fresh export does not also require renaming it before this will find it.
ARTWORK_ALIASES = (ARTWORK, ROOT / "assets" / "hawkvance logo.png")
DRAWN = ROOT / "assets" / "hawkvance-mark.svg"
ICONS = ROOT / "apps" / "desktop" / "src-tauri" / "icons"
WEB = ROOT / "assets" / "web"

# What Tauri looks for, plus the sizes Windows actually picks out of an .ico.
PNG_SIZES = {
    "32x32.png": 32,
    "128x128.png": 128,
    "128x128@2x.png": 256,
    "256x256.png": 256,
    "512x512.png": 512,
    "icon.png": 512,
}
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

CHROME_LOCATIONS = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
)


def render_svg(svg: Path, size: int) -> Image.Image:
    """Rasterises the drawn fallback.

    Chrome is used rather than a Python SVG library because it is already on every
    Windows machine this builds on, and it renders the same engine the app itself
    runs on, so the drawn mark cannot look different in the icon than it does in
    the window.
    """
    browser = next((path for path in CHROME_LOCATIONS if path.exists()), None)
    if browser is None:
        raise SystemExit(
            "No Chrome or Edge found to render the drawn mark.\n"
            f"Put the real artwork at {ARTWORK} instead, and run this again."
        )

    with tempfile.TemporaryDirectory() as scratch:
        page = Path(scratch) / "mark.html"
        shot = Path(scratch) / "mark.png"
        markup = svg.read_text(encoding="utf-8").replace("currentColor", "#111111")
        page.write_text(
            "<!doctype html><meta charset='utf-8'>"
            "<style>html,body{margin:0;background:transparent}"
            f"svg{{display:block;width:{size}px;height:{size}px}}</style>{markup}",
            encoding="utf-8",
        )
        subprocess.run(
            [
                str(browser),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--default-background-color=00000000",
                f"--window-size={size},{size}",
                f"--screenshot={shot}",
                page.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
        return Image.open(shot).convert("RGBA")


def clear_surround(image: Image.Image, tolerance: int = 26) -> Image.Image:
    """Makes the background transparent without hollowing out the artwork.

    A plain "every near-white pixel becomes transparent" pass would also erase the
    eye and the open beak, which are white on purpose and enclosed by the ring. So
    this floods inwards from the border and clears only what it can reach.
    """
    image = image.convert("RGBA")
    width, height = image.size
    pixels = image.load()

    def is_background(x: int, y: int) -> bool:
        red, green, blue, alpha = pixels[x, y]
        return alpha == 0 or (red > 255 - tolerance and green > 255 - tolerance and blue > 255 - tolerance)

    seen = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    for x in range(width):
        for y in (0, height - 1):
            if is_background(x, y):
                queue.append((x, y))
    for y in range(height):
        for x in (0, width - 1):
            if is_background(x, y):
                queue.append((x, y))

    while queue:
        x, y = queue.popleft()
        index = y * width + x
        if seen[index]:
            continue
        seen[index] = 1
        pixels[x, y] = (255, 255, 255, 0)
        for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= next_x < width and 0 <= next_y < height:
                if not seen[next_y * width + next_x] and is_background(next_x, next_y):
                    queue.append((next_x, next_y))

    return image


def load_source() -> tuple[Image.Image, str]:
    found = next((path for path in ARTWORK_ALIASES if path.exists()), None)
    if found is not None:
        source = Image.open(found).convert("RGBA")
        if source.width != source.height:
            side = max(source.size)
            square = Image.new("RGBA", (side, side), (255, 255, 255, 0))
            square.paste(source, ((side - source.width) // 2, (side - source.height) // 2))
            source = square
        if source.width < 512:
            print(f"  note: {found.name} is only {source.width}px, so large icons will be soft")
        return clear_surround(source), str(found.relative_to(ROOT))
    if DRAWN.exists():
        return render_svg(DRAWN, 1024), str(DRAWN.relative_to(ROOT))
    raise SystemExit(f"No logo found. Put one at {ARTWORK}.")


def main() -> None:
    source, origin = load_source()
    print(f"Source: {origin}  ({source.width}x{source.height})")

    ICONS.mkdir(parents=True, exist_ok=True)
    WEB.mkdir(parents=True, exist_ok=True)

    for name, size in PNG_SIZES.items():
        source.resize((size, size), Image.LANCZOS).save(ICONS / name)
        print(f"  {name}")

    # One .ico holding every size, so Windows picks the right one for the taskbar,
    # the desktop shortcut, Explorer and the installer header instead of scaling.
    source.resize((256, 256), Image.LANCZOS).save(
        ICONS / "icon.ico", sizes=[(size, size) for size in ICO_SIZES]
    )
    print("  icon.ico")

    for size, name in ((512, "logo-512.png"), (180, "apple-touch-icon.png"), (32, "favicon-32.png")):
        source.resize((size, size), Image.LANCZOS).save(WEB / name)
        print(f"  web/{name}")

    source.resize((256, 256), Image.LANCZOS).save(
        WEB / "favicon.ico", sizes=[(size, size) for size in (16, 32, 48)]
    )
    print("  web/favicon.ico")
    print("\nRebuild the app to pick these up:  pnpm --filter @hawkvance/desktop app:build")


if __name__ == "__main__":
    main()
