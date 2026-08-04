#!/usr/bin/env python3
"""Turn a photo into an animated ASCII-art SVG that types itself in row by row.

Run this locally, not in CI. It needs a source photo that never gets committed,
and the background-removal model is a ~180MB download on first use.

    python scripts/gen_portrait.py ~/Downloads/photo.jpg

Only assets/ascii-portrait.svg is written. The photo stays on your machine.
"""

import argparse
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

# Sparse -> dense, and read as ink: dark pixels get the dense characters.
#
# The obvious mapping is the other way round — more ink where the image is
# brighter, since light text on a dark terminal reads as "glowing". It renders
# badly here. Dark hair against a dark background becomes empty space, so the
# head is only outlined by the bright rim studio lighting leaves on it, which
# looks like a stray halo rather than a face.
#
# Inverting fixes both ends at once: hair and suit render solid, and the bright
# rim falls to the sparse end of the ramp, where it disappears on its own.
RAMP = " .`:-=+*cs#%@"

# Counter-intuitively, more columns reads *better* at the small size the README
# renders this at: 60 and 80 columns come out as an anonymous skull, while 110
# resolves into an actual face once the eye integrates it.
COLS = 110
# Keep this much of the subject's height, measured from the top, so the frame
# holds the head and shoulders rather than trailing off down the torso.
KEEP_HEIGHT = 0.72
# A monospace glyph is about 0.6 as wide as it is tall, so a square image needs
# roughly 0.6 rows per column to come out square rather than stretched.
CHAR_ASPECT = 0.6
FONT_SIZE = 10
CHAR_W = FONT_SIZE * CHAR_ASPECT
LINE_H = FONT_SIZE * 1.0

PAD = 16
BG = "#0d1117"
FG = "#39d353"

# Alpha below this counts as background and renders as blank space.
ALPHA_CUTOFF = 200
# The cutout mask sits a little outside the subject. A light erode pulls it back
# in; it can stay gentle because the inverted ramp already hides the bright rim
# it would otherwise be fighting.
ERODE = 5
# Eroding snaps textured hair into a spray of islands, which renders as speckle
# floating above the head. Keeping only the largest blob and growing it back
# leaves one solid silhouette.
DILATE = 3
CONTRAST = 1.15
# Pull the darkest tones up slightly so hair and suit don't collapse into one blob.
FLOOR = 0.04
# >1 opens up the face. Skin sits in the mid-tones, and lifting those pushes the
# cheeks and forehead toward the sparse end, leaving eyes, brows and mouth as the
# dense marks that make the face legible.
GAMMA = 1.2

ROW_STAGGER = 0.035
ROW_DUR = 0.30


def largest_blob(mask: np.ndarray) -> np.ndarray:
    """Keep only the biggest connected region of a boolean mask, as uint8 0/255."""
    from scipy import ndimage

    labelled, count = ndimage.label(mask)
    if count > 1:
        sizes = ndimage.sum(mask, labelled, range(1, count + 1))
        mask = labelled == (int(np.argmax(sizes)) + 1)
    return (mask * 255).astype(np.uint8)


def cut_out_subject(src: Path, cached: Path | None = None) -> Image.Image:
    """Remove the background, returning an RGBA image cropped to the subject."""
    if cached and cached.is_file():
        cut = Image.open(cached).convert("RGBA")
    else:
        from rembg import remove

        cut = Image.open(io.BytesIO(remove(src.read_bytes()))).convert("RGBA")
        if cached:
            cut.save(cached)

    mask = cut.getchannel("A").point(lambda a: 255 if a > ALPHA_CUTOFF else 0)
    mask = mask.filter(ImageFilter.MinFilter(ERODE))
    mask = Image.fromarray(largest_blob(np.asarray(mask) > 127))
    mask = mask.filter(ImageFilter.MaxFilter(DILATE))
    cut.putalpha(mask)

    bbox = mask.getbbox()
    if bbox:
        cut = cut.crop(bbox)

    if KEEP_HEIGHT < 1.0:
        cut = cut.crop((0, 0, cut.width, round(cut.height * KEEP_HEIGHT)))
    return cut


def to_char_grid(img: Image.Image) -> list[str]:
    """Downsample to a character grid and map luminance onto the ramp."""
    rows = max(1, round(COLS * (img.height / img.width) * CHAR_ASPECT))

    # Composite onto black before shrinking, so semi-transparent edge pixels
    # fade out instead of picking up whatever the original background was.
    flat = Image.new("RGB", img.size, (0, 0, 0))
    flat.paste(img, mask=img.getchannel("A"))

    small = flat.resize((COLS, rows), Image.LANCZOS)

    # Shrink the mask on its own with a filter that can't overshoot. LANCZOS
    # rings around the hard silhouette edge, and that ringing is what scattered
    # stray characters across the empty background.
    alpha = np.asarray(
        img.getchannel("A").resize((COLS, rows), Image.BILINEAR), dtype=np.float32
    )

    gray = ImageOps.autocontrast(small.convert("L"), cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(CONTRAST)

    lum = np.asarray(gray, dtype=np.float32) / 255.0
    lum = np.clip((lum - FLOOR) / (1.0 - FLOOR), 0.0, 1.0)
    lum = lum ** (1.0 / GAMMA)

    idx = np.rint((1.0 - lum) * (len(RAMP) - 1)).astype(int)
    idx[alpha < 128] = 0  # background -> space

    return ["".join(RAMP[i] for i in row) for row in idx]


def build_svg(grid: list[str]) -> str:
    width = round(COLS * CHAR_W + PAD * 2)
    height = round(len(grid) * LINE_H + PAD * 2)
    text_len = round(COLS * CHAR_W, 2)

    # One rule per row. Each row is clipped to zero width, then wipes open
    # left-to-right on a stagger, which reads as the picture typing itself in.
    rules = [
        f".r{i}{{animation-delay:{i * ROW_STAGGER:.3f}s}}" for i in range(len(grid))
    ]

    lines = []
    for i, row in enumerate(grid):
        y = round(PAD + (i + 0.85) * LINE_H, 2)
        # XML-escape the ramp characters that matter.
        safe = row.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines.append(
            f'<text class="r{i}" x="{PAD}" y="{y}" '
            f'textLength="{text_len}" lengthAdjust="spacingAndGlyphs">{safe}</text>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="ASCII-art portrait">
<style>
text {{
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: {FONT_SIZE}px;
  fill: {FG};
  white-space: pre;
  clip-path: inset(0 100% 0 0);
  animation: wipe {ROW_DUR}s steps(24, end) forwards;
}}
@keyframes wipe {{ to {{ clip-path: inset(0 0 0 0); }} }}
{chr(10).join(rules)}
</style>
<rect width="100%" height="100%" fill="{BG}" rx="6"/>
{chr(10).join(lines)}
</svg>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("photo", type=Path, help="source photo (stays local)")
    ap.add_argument(
        "--cache",
        type=Path,
        help="reuse/store the background-removed cutout, to skip the slow model run",
    )
    ap.add_argument(
        "-o",
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "assets" / "ascii-portrait.svg",
    )
    args = ap.parse_args()

    if not args.photo.is_file():
        print(f"error: no such photo: {args.photo}", file=sys.stderr)
        return 1

    grid = to_char_grid(cut_out_subject(args.photo, args.cache))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_svg(grid), encoding="utf-8")

    filled = sum(c != " " for row in grid for c in row)
    total = sum(len(row) for row in grid)
    print(
        f"wrote {args.out} "
        f"({COLS}x{len(grid)} chars, {filled / total:.0%} ink, "
        f"{args.out.stat().st_size / 1024:.1f} KB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
