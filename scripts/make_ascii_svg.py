"""
Convert a portrait photo into a CLEAN, monochrome ASCII-art SVG (Andrew6rant
style: one light-gray color, subject isolated on a dark background) that plays
two grid-aligned falling-block assemblies in succession:
  1. Square 80x80 blocks dropping and stacking into the portrait
  2. Board clears downward, then interlocking Tetris tetrominoes drop & lock

GitHub renders SVGs embedded via <img> and runs their SMIL animations there (JS
does not run). Blocks are sliced along exact character/line boundaries so there
is zero <use> or per-block <clipPath> overhead.
"""
from PIL import Image, ImageEnhance, ImageFilter
import html
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "assets", "source-prepped.png")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "avi-ascii.svg")

COLS = 100
ROWS = 53
CELL_W = 8
CELL_H = 16
RAMP = " .`:-=+*cs#%@"  # bright(sparse) -> dark(dense); leading space clears bg

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
BLOCK_SIZE = 80       # exact square aligned to character cell boundaries

BG = "#0d1117"
BG2 = "#111722"
FRAME = "#30363d"
TITLE_TEXT = "#7d8590"
INK = "#c9d1d9"      # the single ascii color (matches Andrew6rant)

# ---- timing ---------------------------------------------------------------
BASE_FALL_DUR = 0.62
STEP_GAP = 0.13
COL_SPREAD = 0.85
HOLD_BETWEEN = 0.90
CLEAR_DUR = 0.42

BASE_TETROMINOES = {
    "I": [(0, 0), (1, 0), (2, 0), (3, 0)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "T": [(0, 0), (1, 0), (2, 0), (1, 1)],
    "S": [(1, 0), (2, 0), (0, 1), (1, 1)],
    "Z": [(0, 0), (1, 0), (1, 1), (2, 1)],
    "J": [(0, 0), (0, 1), (1, 1), (2, 1)],
    "L": [(2, 0), (0, 1), (1, 1), (2, 1)],
}
BASE_TRIMINOES = {
    "L3": [(0, 0), (0, 1), (1, 1)],
    "I3": [(0, 0), (1, 0), (2, 0)],
}
TETRIS_COLORS = {
    "I": "#39c5cf",
    "O": "#e3b341",
    "T": "#bc8cff",
    "S": "#3fb950",
    "Z": "#f85149",
    "J": "#58a6ff",
    "L": "#ffa657",
    "L3": "#7d8590",
    "I3": "#7d8590",
}


def rotations(cells):
    """Return unique normalized rotations of a polyomino."""
    out = set()
    cur = list(cells)
    for _ in range(4):
        minx = min(x for x, y in cur)
        miny = min(y for x, y in cur)
        out.add(tuple(sorted((x - minx, y - miny) for x, y in cur)))
        cur = [(-y, x) for x, y in cur]
    return list(out)


def tile_tetris_grid(grid_cols, grid_rows, seed=7):
    """Tile a grid bottom-up into tetrominoes (plus minimal triminoes if area % 4 != 0)."""
    rng = random.Random(seed)
    tet_vars = [(n, r) for n, b in BASE_TETROMINOES.items() for r in rotations(b)]
    tri_vars = [(n, r) for n, b in BASE_TRIMINOES.items() for r in rotations(b)]
    tri_budget = (4 - (grid_cols * grid_rows) % 4) % 4  # 2 for 10x15 -> two 3-cell pieces

    grid = [[-1] * grid_cols for _ in range(grid_rows)]
    pieces = []

    def next_empty():
        for y in range(grid_rows - 1, -1, -1):
            for x in range(grid_cols):
                if grid[y][x] == -1:
                    return x, y
        return None

    def components_feasible(tri_left):
        seen = [[False] * grid_cols for _ in range(grid_rows)]
        small_need = 0
        for sy in range(grid_rows):
            for sx in range(grid_cols):
                if grid[sy][sx] != -1 or seen[sy][sx]:
                    continue
                stack = [(sx, sy)]
                seen[sy][sx] = True
                cnt = 0
                while stack:
                    cx, cy = stack.pop()
                    cnt += 1
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < grid_cols and 0 <= ny < grid_rows and not seen[ny][nx] and grid[ny][nx] == -1:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
                if cnt < 3:
                    return False
                rem = cnt % 4
                if rem in (1, 2):
                    if rem == 2 and tri_left >= 2:
                        small_need += 2
                    else:
                        return False
                elif rem == 3:
                    small_need += 1
        return small_need <= tri_left

    def solve(tri_left):
        pos = next_empty()
        if pos is None:
            return tri_left == 0
        ax, ay = pos
        cands = []
        for name, shape in tet_vars:
            for ox, oy in shape:
                pts = [(ax + x - ox, ay + y - oy) for x, y in shape]
                if all(0 <= px < grid_cols and 0 <= py < grid_rows and grid[py][px] == -1 for px, py in pts):
                    cands.append((name, pts, 0))
        if tri_left > 0 and ay <= 3:
            for name, shape in tri_vars:
                for ox, oy in shape:
                    pts = [(ax + x - ox, ay + y - oy) for x, y in shape]
                    if all(0 <= px < grid_cols and 0 <= py < grid_rows and grid[py][px] == -1 for px, py in pts):
                        cands.append((name, pts, 1))
        rng.shuffle(cands)
        cands.sort(key=lambda item: item[2])
        for name, pts, cost in cands:
            pid = len(pieces)
            for px, py in pts:
                grid[py][px] = pid
            if components_feasible(tri_left - cost):
                pieces.append((pid, name, pts))
                if solve(tri_left - cost):
                    return True
                pieces.pop()
            for px, py in pts:
                grid[py][px] = -1
        return False

    assert solve(tri_budget), f"Failed to tile {grid_cols}x{grid_rows} grid"
    return grid, pieces


def piece_outline_path(pts, origin_x, origin_y, size):
    """Build exact outer boundary path of a connected polyomino."""
    cell_set = set(pts)
    edges = {}
    for gx, gy in pts:
        x0, y0 = origin_x + gx * size, origin_y + gy * size
        x1, y1 = x0 + size, y0 + size
        if (gx, gy - 1) not in cell_set:
            edges.setdefault((x0, y0), []).append((x1, y0))
        if (gx + 1, gy) not in cell_set:
            edges.setdefault((x1, y0), []).append((x1, y1))
        if (gx, gy + 1) not in cell_set:
            edges.setdefault((x1, y1), []).append((x0, y1))
        if (gx - 1, gy) not in cell_set:
            edges.setdefault((x0, y1), []).append((x0, y0))
    loops = []
    while edges:
        start = next(iter(edges))
        cur = start
        loop = [cur]
        while True:
            nxt = edges[cur].pop(0)
            if not edges[cur]:
                del edges[cur]
            if nxt == start:
                break
            loop.append(nxt)
            cur = nxt
        loops.append(loop)
    return "".join(
        f"M{lp[0][0]:.1f} {lp[0][1]:.1f}" + "".join(f"L{x:.1f} {y:.1f}" for x, y in lp[1:]) + "Z"
        for lp in loops
    )


def inner_mino_seams(pts, origin_x, origin_y, size):
    """Internal lines between adjacent minos of the same polyomino."""
    cell_set = set(pts)
    segs = []
    for gx, gy in pts:
        x0, y0 = origin_x + gx * size, origin_y + gy * size
        if (gx + 1, gy) in cell_set:
            segs.append(f"M{x0+size:.1f} {y0:.1f}V{y0+size:.1f}")
        if (gx, gy + 1) in cell_set:
            segs.append(f"M{x0:.1f} {y0+size:.1f}H{x0+size:.1f}")
    return "".join(segs)


def render_cell_texts(padded_rows, gx, gy, art_top, font_size):
    """Render the sliced <text> lines belonging to a single grid square."""
    bx = PAD + gx * BLOCK_SIZE
    by = art_top + gy * BLOCK_SIZE
    c0 = gx * CHARS_PER_BLK
    c1 = c0 + CHARS_PER_BLK
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
    return "".join(texts)


def drop_group(inner, fall_dist, t_start, fall_dur):
    """Wrap content in a SMIL gravity-drop + settle <g>."""
    return (
        f'<g transform="translate(0,-{fall_dist})">{inner}'
        f'<animateTransform attributeName="transform" type="translate" '
        f'values="0 -{fall_dist}; 0 0; 0 -3; 0 0" '
        f'keyTimes="0; 0.88; 0.95; 1" '
        f'keySplines="0.45 0 1 0.9; 0.2 0.8 0.4 1; 0.4 0 0.8 1" '
        f'calcMode="spline" begin="{t_start:.3f}s" dur="{fall_dur:.3f}s" fill="freeze"/>'
        f'</g>'
    )

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
font_size = CELL_H * 0.86

if STATIC:
    parts.append(f'<text x="{CANVAS_W/2}" y="{TITLEBAR_H/2 + 4}" fill="{TITLE_TEXT}" font-size="12" '
                 f'text-anchor="middle">abrez-rizvi@github: ~$ ./portrait.sh</text>')
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
    # ---- Phase 1: square 80x80 blocks dropping & stacking ----
    col_order = sorted(range(GRID_COLS), key=lambda c: ((c * 5 + 3) % GRID_COLS))
    col_delays = [0.0] * GRID_COLS
    for rank, col in enumerate(col_order):
        col_delays[col] = (rank / max(1, GRID_COLS - 1)) * COL_SPREAD

    p1_blocks = []
    p1_max_land = 0.0
    for gx in range(GRID_COLS):
        for gy in range(GRID_ROWS - 1, -1, -1):
            stack_idx = (GRID_ROWS - 1) - gy
            fall_dist = (gy + 1) * BLOCK_SIZE
            fall_dur = max(0.22, BASE_FALL_DUR * math.sqrt(fall_dist / GRID_H))
            jitter = ((gx * 7 + gy * 3) % 5) * 0.010
            t_start = col_delays[gx] + stack_idx * STEP_GAP + jitter
            p1_max_land = max(p1_max_land, t_start + fall_dur)
            inner = render_cell_texts(padded_rows, gx, gy, art_top, font_size)
            p1_blocks.append(drop_group(inner, fall_dist, t_start, fall_dur))

    t_clear = p1_max_land + HOLD_BETWEEN
    t_p2 = t_clear + CLEAR_DUR

    # ---- Phase 2: interlocking Tetris tetrominoes ----
    grid, pieces = tile_tetris_grid(GRID_COLS, GRID_ROWS, seed=7)
    deps = {pid: set() for pid, _, _ in pieces}
    for pid, _, pts in pieces:
        for gx, gy in pts:
            if gy + 1 < GRID_ROWS:
                below = grid[gy + 1][gx]
                if below != pid:
                    deps[pid].add(below)

    depth = {}
    def get_depth(pid):
        if pid not in depth:
            depth[pid] = 0 if not deps[pid] else 1 + max(get_depth(q) for q in deps[pid])
        return depth[pid]

    for pid, _, _ in pieces:
        get_depth(pid)

    order_pids = sorted(
        range(len(pieces)),
        key=lambda p: (depth[p], -max(y for _, y in pieces[p][2]), min(x for x, _ in pieces[p][2])),
    )
    t_start_map, t_land_map = {}, {}
    for pid in order_pids:
        _, _, pts = pieces[pid]
        max_y = max(y for _, y in pts)
        min_x = min(x for x, _ in pts)
        fall_dist = (max_y + 1) * BLOCK_SIZE
        fall_dur = max(0.24, BASE_FALL_DUR * math.sqrt(fall_dist / GRID_H))
        if not deps[pid]:
            t_start = (min_x % 5) * 0.08 + (pid % 3) * 0.05
        else:
            min_land = max(t_land_map[q] for q in deps[pid]) + 0.11
            col_wave = ((min_x * 3 + depth[pid] * 5) % 4) * 0.04
            t_start = max(0.0, min_land - fall_dur + col_wave)
        t_start_map[pid] = t_start
        t_land_map[pid] = t_start + fall_dur

    p2_base = t_p2 + 0.08
    p2_blocks = []
    for pid in order_pids:
        _, name, pts = pieces[pid]
        max_y = max(y for _, y in pts)
        fall_dist = (max_y + 1) * BLOCK_SIZE
        t_start = p2_base + t_start_map[pid]
        t_land = p2_base + t_land_map[pid]
        fall_dur = t_land_map[pid] - t_start_map[pid]
        color = TETRIS_COLORS[name]
        outline = piece_outline_path(pts, PAD, art_top, BLOCK_SIZE)
        seams = inner_mino_seams(pts, PAD, art_top, BLOCK_SIZE)
        border_grp = (
            f'<g opacity="0.9">'
            f'<path d="{outline}" fill="{color}" fill-opacity="0.09" stroke="{color}" '
            f'stroke-width="2" stroke-linejoin="round"/>'
            + (f'<path d="{seams}" fill="none" stroke="{color}" stroke-width="1" stroke-opacity="0.32"/>' if seams else '')
            + f'<animate attributeName="opacity" from="0.9" to="0" '
            f'begin="{t_land + 0.08:.3f}s" dur="0.35s" fill="freeze"/></g>'
        )
        texts = "".join(render_cell_texts(padded_rows, gx, gy, art_top, font_size) for gx, gy in pts)
        p2_blocks.append(drop_group(border_grp + texts, fall_dist, t_start, fall_dur))

    p2_end = p2_base + max(t_land_map.values()) + 0.43

    # Titlebar command switches from ./portrait.sh -> ./tetris_portrait.sh
    parts.append(
        f'<text x="{CANVAS_W/2}" y="{TITLEBAR_H/2 + 4}" fill="{TITLE_TEXT}" font-size="12" '
        f'text-anchor="middle">abrez-rizvi@github: ~$ ./portrait.sh'
        f'<set attributeName="display" to="none" begin="{t_p2:.3f}s"/></text>'
    )
    parts.append(
        f'<text x="{CANVAS_W/2}" y="{TITLEBAR_H/2 + 4}" fill="{TITLE_TEXT}" font-size="12" '
        f'text-anchor="middle" display="none">abrez-rizvi@github: ~$ ./tetris_portrait.sh'
        f'<set attributeName="display" to="inline" begin="{t_p2:.3f}s"/></text>'
    )

    parts.append('<g clip-path="url(#art-vp)">')
    parts.append(
        f'<g>{"".join(p1_blocks)}'
        f'<animateTransform attributeName="transform" type="translate" '
        f'from="0 0" to="0 {GRID_H}" begin="{t_clear:.3f}s" dur="{CLEAR_DUR:.3f}s" '
        f'calcMode="spline" keySplines="0.55 0 1 1" fill="freeze"/>'
        f'<set attributeName="display" to="none" begin="{t_p2:.3f}s"/></g>'
    )
    parts.append(
        f'<g visibility="hidden">{"".join(p2_blocks)}'
        f'<set attributeName="visibility" to="visible" begin="{t_p2:.3f}s"/></g>'
    )
    parts.append('</g>')
    print(f"timeline: blocks 0->{p1_max_land:.2f}s, clear {t_clear:.2f}->{t_p2:.2f}s, "
          f"tetris {p2_base:.2f}->{p2_end:.2f}s")

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
