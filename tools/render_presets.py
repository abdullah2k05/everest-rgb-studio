#!/usr/bin/env python3
"""Render built-in preset key maps to a PNG contact sheet.

    python tools/render_presets.py                       # every built-in
    python tools/render_presets.py Ultraviolet Nebula    # a shortlist
    python tools/render_presets.py --out sheet.png

Requires Pillow. Renders the *stored* map only: animated presets show the
base frame they would start from, not a live frame.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageDraw  # noqa: E402

from everest_rgb.models.keyboard import (  # noqa: E402
    BOARD_HEIGHT,
    BOARD_WIDTH,
    KEYS,
    SIDE_LED_POSITIONS,
)
from everest_rgb.presets.store import PresetStore  # noqa: E402

SCALE = 46
PAD = 14
RING_R = 26
GAP = 4
BAR = 30


def render(preset) -> Image.Image:
    width = int(BOARD_WIDTH * SCALE) + 2 * (PAD + RING_R)
    height = int(BOARD_HEIGHT * SCALE) + 2 * (PAD + RING_R)
    img = Image.new("RGB", (width, height), (14, 14, 18))
    draw = ImageDraw.Draw(img)
    ox = oy = PAD + RING_R

    for led in SIDE_LED_POSITIONS:
        x, y = ox + led.x * SCALE, oy + led.y * SCALE
        color = tuple(preset.state.side_colors[led.index])
        draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=color)

    for key in KEYS:
        x0 = ox + key.x * SCALE + GAP
        y0 = oy + key.y * SCALE + GAP
        x1 = ox + (key.x + key.w) * SCALE - GAP
        y1 = oy + (key.y + key.h) * SCALE - GAP
        color = tuple(preset.state.key_colors[key.index])
        draw.rounded_rectangle([x0, y0, x1, y1], radius=7, fill=color)
        luminance = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
        draw.text(
            (x0 + 7, y0 + 6),
            key.label[:4],
            fill=(0, 0, 0) if luminance > 150 else (255, 255, 255),
        )
    return img


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*", help="preset names (default: all built-ins)")
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--out", default=str(ROOT / "docs" / "previews" / "presets.png"))
    args = parser.parse_args()

    store = PresetStore(user_dir=ROOT / ".none", builtin_dir=ROOT / "src/everest_rgb/presets/builtin")
    presets = [p for p in store.list() if p.builtin]
    if args.names:
        wanted = set(args.names)
        presets = [p for p in presets if p.name in wanted]
        missing = wanted - {p.name for p in presets}
        if missing:
            parser.error(f"unknown presets: {', '.join(sorted(missing))}")
    if not presets:
        parser.error("nothing to render")

    cells = [(p, render(p)) for p in presets]
    cols = min(args.columns, len(cells))
    rows = (len(cells) + cols - 1) // cols
    cw = max(c.width for _, c in cells)
    ch = max(c.height for _, c in cells) + BAR

    sheet = Image.new("RGB", (cols * cw, rows * ch), (8, 8, 10))
    draw = ImageDraw.Draw(sheet)
    for i, (preset, cell) in enumerate(cells):
        cx, cy = (i % cols) * cw, (i // cols) * ch
        sheet.paste(cell, (cx, cy + BAR))
        draw.text(
            (cx + 10, cy + 9),
            f"{preset.name}  [{preset.state.mode}/{preset.state.effect}]  {preset.description[:56]}",
            fill=(240, 240, 240),
        )

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    try:
        shown = out.relative_to(ROOT)
    except ValueError:
        shown = out
    print(f"wrote {shown} {sheet.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
