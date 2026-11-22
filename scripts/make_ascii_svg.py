"""
Convert a portrait photo into a CLEAN, monochrome ASCII-art SVG (Andrew6rant
style: one light-gray color, subject isolated on a dark background) divided into
a grid of square blocks that fall from above and stack on top of each other to
assemble the portrait, then hold.

GitHub renders SVGs embedded via <img> and runs their SMIL animations there (JS
does not run). Each square block drops under gravity into its column (bottom
blocks first, upper blocks landing cleanly on top) and freezes in place.
"""
from PIL import Image, ImageEnhance, ImageFilter
import html
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# defaults to the prepped grayscale image (see prep_photo.py), which already has
# the background removed + local contrast applied.
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "assets", "source-prepped.png")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "avi-ascii.svg")

COLS = 100
ROWS = 53
CELL_W = 8
CELL_H = 16
RAMP = " .`:-=+*cs#%@"  # bright(sparse) -> dark(dense); leading space clears bg

# the prepped image already has bg removed + CLAHE local contrast, so only
# light global tuning is needed here.
CONTRAST = 1.05
BRIGHTNESS = 1.0
GAMMA = 1.18          # >1 brightens mids -> face lands in sparser chars
SHARPEN = False
WHITE_FLOOR = 0.80    # luminance above this is forced to blank (space)

PAD = 20
TITLEBAR_H = 30
STATUS_H = 30
CHARS_PER_BLK = 10    # 10 * 8  = 80px wide
LINES_PER_BLK = 5     #  5 * 16 = 80px tall
BLOCK_SIZE = 80       # exact square aligned to character cell boundaries (no per-block clip/use)

BG = "#0d1117"
BG2 = "#111722"
FRAME = "#30363d"
TITLE_TEXT = "#7d8590"
INK = "#c9d1d9"      # the single ascii color (matches Andrew6rant)

# ---- falling block timing (one-shot; columns rain down and stack bottom-up) -
BASE_FALL_DUR = 0.65  # drop duration for a full-height fall
STEP_GAP = 0.13       # delay between consecutive blocks in the same column
COL_SPREAD = 0.85     # max stagger across columns

TXT_SRC = os.path.join(HERE, "..", "assets", "ascii-art.txt")
if not os.path.exists(TXT_SRC):
    TXT_SRC = os.path.join(HERE, "..", "ascii-art.txt")

if os.path.exists(TXT_SRC):
    with open(TXT_SRC, "r", encoding="utf-8") as f:
        rows_txt = [line.rstrip("\r\n") for line in f if line.strip()]
    ROWS = len(rows_txt)
    COLS = max(len(l) for l in rows_txt) if rows_txt else 100
    rows_txt = [l.ljust(COLS) for l in rows_txt]
else:
    im = Image.open(SRC).convert("L")               # grayscale
    if SHARPEN:
        im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=140, threshold=2))
    im = ImageEnhance.Brightness(im).enhance(BRIGHTNESS)
    im = ImageEnhance.Contrast(im).enhance(CONTRAST)
    im = im.resize((COLS, ROWS), Image.LANCZOS)
    px = im.load()

    rows_txt = []
    for y in range(ROWS):
        chars = []
        for x in range(COLS):
            lum = px[x, y] / 255.0
            lum = pow(lum, GAMMA)
            if lum >= WHITE_FLOOR:
                chars.append(" ")
                continue
            idx = int((1.0 - lum) * (len(RAMP) - 1) + 0.5)
            idx = max(0, min(len(RAMP) - 1, idx))
            chars.append(RAMP[idx])
        rows_txt.append("".join(chars))

STATIC = bool(os.environ.get("STATIC"))  # emit frozen state for previews

# Pad rows/cols cleanly to an exact grid of BLOCK_SIZE x BLOCK_SIZE squares
GRID_COLS = math.ceil(COLS / CHARS_PER_BLK)
GRID_ROWS = math.ceil(ROWS / LINES_PER_BLK)
PADDED_COLS = GRID_COLS * CHARS_PER_BLK
PADDED_ROWS = GRID_ROWS * LINES_PER_BLK

pad_left = (PADDED_COLS - COLS) // 2
pad_top = (PADDED_ROWS - ROWS) // 2
pad_bottom = PADDED_ROWS - ROWS - pad_top
padded_rows = (
    [" " * PADDED_COLS] * pad_top
    + [(" " * pad_left + l).ljust(PADDED_COLS) for l in rows_txt]
    + [" " * PADDED_COLS] * pad_bottom
)

GRID_W = GRID_COLS * BLOCK_SIZE
GRID_H = GRID_ROWS * BLOCK_SIZE

CANVAS_W = GRID_W + PAD * 2
CANVAS_H = TITLEBAR_H + GRID_H + STATUS_H + PAD

art_top = TITLEBAR_H + PAD * 0.35

# ---- 2. assemble SVG ------------------------------------------------------
parts = []
parts.append(
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" '
    f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" font-family="ui-monospace, SFMono-Regular, '
    f'Menlo, Consolas, monospace">'
)
parts.append(
    f'<defs>'
    f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
    f'<stop offset="0" stop-color="{BG2}"/><stop offset="1" stop-color="{BG}"/>'
    f'</linearGradient>'
    f'<clipPath id="art-vp"><rect x="{PAD}" y="{art_top:.1f}" '
    f'width="{GRID_W}" height="{GRID_H}"/></clipPath>'
    f'</defs>'
)

parts.append(f'<rect width="{CANVAS_W}" height="{CANVAS_H}" rx="12" fill="url(#bg)"/>')
parts.append(f'<rect x="0.5" y="0.5" width="{CANVAS_W-1}" height="{CANVAS_H-1}" rx="12" '
             f'fill="none" stroke="{FRAME}" stroke-width="1"/>')

parts.append(f'<line x1="0" y1="{TITLEBAR_H}" x2="{CANVAS_W}" y2="{TITLEBAR_H}" stroke="{FRAME}"/>')
for i, dotcol in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
    parts.append(f'<circle cx="{PAD + i*16}" cy="{TITLEBAR_H/2}" r="5" fill="{dotcol}"/>')
parts.append(f'<text x="{CANVAS_W/2}" y="{TITLEBAR_H/2 + 4}" fill="{TITLE_TEXT}" font-size="12" '
             f'text-anchor="middle">abrez-rizvi@github: ~$ ./portrait.sh</text>')

font_size = CELL_H * 0.86

if STATIC:
    parts.append('<g clip-path="url(#art-vp)">')
    for ry, line in enumerate(padded_rows):
        y = art_top + ry * CELL_H + CELL_H * 0.74
        parts.append(
            f'<text xml:space="preserve" x="{PAD}" y="{y:.1f}" fill="{INK}" '
            f'font-size="{font_size:.1f}" textLength="{GRID_W}" lengthAdjust="spacing">'
            f'{html.escape(line)}</text>'
        )
    parts.append('</g>')
else:
    # Deterministic non-linear column stagger so blocks rain down organically
    col_order = sorted(range(GRID_COLS), key=lambda c: ((c * 5 + 3) % GRID_COLS))
    col_delays = [0.0] * GRID_COLS
    for rank, col in enumerate(col_order):
        col_delays[col] = (rank / max(1, GRID_COLS - 1)) * COL_SPREAD

    parts.append('<g clip-path="url(#art-vp)">')
    for gx in range(GRID_COLS):
        bx = PAD + gx * BLOCK_SIZE
        c0 = gx * CHARS_PER_BLK
        c1 = c0 + CHARS_PER_BLK
        # Bottom-to-top within each column so each block lands on top of the one below
        for gy in range(GRID_ROWS - 1, -1, -1):
            by = art_top + gy * BLOCK_SIZE
            stack_idx = (GRID_ROWS - 1) - gy
            fall_dist = (gy + 1) * BLOCK_SIZE
            fall_dur = max(0.22, BASE_FALL_DUR * math.sqrt(fall_dist / GRID_H))
            jitter = ((gx * 7 + gy * 3) % 5) * 0.010
            t_start = col_delays[gx] + stack_idx * STEP_GAP + jitter

            texts = []
            for lr in range(LINES_PER_BLK):
                ry = gy * LINES_PER_BLK + lr
                ty = by + lr * CELL_H + CELL_H * 0.74
                slice_txt = html.escape(padded_rows[ry][c0:c1])
                texts.append(
                    f'<text xml:space="preserve" x="{bx}" y="{ty:.1f}" fill="{INK}" '
                    f'font-size="{font_size:.1f}" textLength="{BLOCK_SIZE}" lengthAdjust="spacing">'
                    f'{slice_txt}</text>'
                )

            parts.append(
                f'<g transform="translate(0,-{fall_dist})">{"".join(texts)}'
                f'<animateTransform attributeName="transform" type="translate" '
                f'values="0 -{fall_dist}; 0 0; 0 -3; 0 0" '
                f'keyTimes="0; 0.88; 0.95; 1" '
                f'keySplines="0.45 0 1 0.9; 0.2 0.8 0.4 1; 0.4 0 0.8 1" '
                f'calcMode="spline" begin="{t_start:.3f}s" dur="{fall_dur:.3f}s" fill="freeze"/>'
                f'</g>'
            )
    parts.append('</g>')

# status bar with a steady blinking cursor
status_line_y = TITLEBAR_H + GRID_H + PAD * 0.35
status_y = status_line_y + 19
parts.append(f'<line x1="0" y1="{status_line_y:.1f}" x2="{CANVAS_W}" y2="{status_line_y:.1f}" stroke="{FRAME}"/>')
parts.append(f'<text x="{PAD}" y="{status_y:.1f}" fill="{TITLE_TEXT}" font-size="13">'
             f'abrez-rizvi@github:~$ whoami <tspan fill="{INK}">Abrez Rizvi</tspan></text>')
parts.append(f'<rect x="{PAD+318}" y="{status_y-12:.1f}" width="8" height="14" fill="{INK}">'
             f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.51;1" '
             f'dur="1s" repeatCount="indefinite"/></rect>')

parts.append("</svg>")
svg = "".join(parts)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(svg)
print("wrote", OUT, len(svg), "bytes;", CANVAS_W, "x", CANVAS_H,
      f"grid={GRID_COLS}x{GRID_ROWS} ({BLOCK_SIZE}px squares)")
