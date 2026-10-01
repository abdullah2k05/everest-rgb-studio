#!/usr/bin/env python3
"""Regenerate built-in preset JSON files.

Run from the repository root:

    python tools/gen_builtin_presets.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from everest_rgb.models.keyboard import KEY_BY_NAME, KEYS  # noqa: E402
from everest_rgb.models.lighting import LightingState  # noqa: E402
from everest_rgb.models.preset import Preset  # noqa: E402

OUT = ROOT / "src" / "everest_rgb" / "presets" / "builtin"


def _lerp(a, b, t: float):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _gradient(colors: list[tuple], *, axis: str = "x") -> list[str]:
    """Horizontal/vertical gradient over the whole board."""
    x0, x1 = min(k.x for k in KEYS), max(k.x + k.w for k in KEYS)
    y0, y1 = min(k.y for k in KEYS), max(k.y + k.h for k in KEYS)
    out = []
    for key in KEYS:
        if axis == "x":
            t = ((key.x + key.w / 2) - x0) / (x1 - x0)
        else:
            t = ((key.y + key.h / 2) - y0) / (y1 - y0)
        t = max(0.0, min(1.0, t)) * (len(colors) - 1)
        i = min(int(t), len(colors) - 2)
        out.append(_hex(_lerp(colors[i], colors[i + 1], t - i)))
    return out


def _solid(color: tuple) -> list[str]:
    return [_hex(color)] * len(KEYS)


def _ring(colors: list[tuple], count: int = 44) -> list[tuple]:
    """Smooth gradient of RGB tuples around the 44 LED side ring."""
    out = []
    for i in range(count):
        t = i / max(count - 1, 1) * (len(colors) - 1)
        j = min(int(t), len(colors) - 2)
        out.append(_lerp(colors[j], colors[j + 1], t - j))
    return out


def _wasd(base: list[str], accent: str) -> list[str]:
    colors = list(base)
    for name in ("W", "A", "S", "D"):
        colors[KEY_BY_NAME[name].index] = accent
    return colors


def _preset(name: str, description: str, colors: list[str], **overrides) -> Preset:
    state = LightingState()
    state.mode = overrides.pop("mode", "custom")
    state.effect = overrides.pop("effect", "static")
    state.key_colors = [
        tuple(int(colors[i][j : j + 2], 16) for j in (1, 3, 5)) for i in range(len(KEYS))
    ]
    for key, value in overrides.items():
        setattr(state, key, value)
    return Preset.from_state(name, state, description)


def build_presets() -> list[Preset]:
    presets = []

    presets.append(
        _preset(
            "Ocean",
            "Deep blue to cyan gradient across the board",
            _gradient([(0, 32, 84), (0, 119, 182), (72, 202, 228)]),
            side_colors=_ring([(0, 32, 84), (0, 119, 182), (72, 202, 228)]),
        )
    )
    presets.append(
        _preset(
            "Cyberpunk",
            "Near-black board, WASD in neon cyan",
            _wasd([_hex((18, 4, 34))] * len(KEYS), "#00F0FF"),
            side_colors=_ring([(0, 240, 255), (255, 0, 170)]),
        )
    )
    presets.append(
        _preset(
            "Sunset",
            "Warm top-to-bottom sunset gradient",
            _gradient([(255, 94, 58), (255, 0, 95), (58, 7, 109)], axis="y"),
            side_colors=_ring([(255, 94, 58), (255, 0, 95)]),
        )
    )
    presets.append(
        _preset(
            "Aurora",
            "Green to violet aurora band",
            _gradient([(16, 255, 144), (0, 196, 255), (150, 60, 255)]),
            side_colors=_ring([(16, 255, 144), (0, 196, 255), (150, 60, 255)]),
        )
    )
    presets.append(
        _preset(
            "Minimal White",
            "Soft white backlight",
            _solid((232, 232, 232)),
            side_colors=_ring([(180, 180, 190), (232, 232, 232)]),
        )
    )
    presets.append(
        _preset(
            "Red Alert",
            "Solid red",
            _solid((255, 32, 32)),
            side_colors=_ring([(255, 32, 32), (140, 0, 0)]),
        )
    )
    presets.append(
        _preset(
            "Deep Blue",
            "Midnight blue gradient",
            _gradient([(0, 12, 64), (0, 40, 160), (20, 90, 255)]),
            side_colors=_ring([(0, 40, 160), (20, 90, 255)]),
        )
    )
    presets.append(
        _preset(
            "Purple Night",
            "Purple to magenta gradient",
            _gradient([(58, 12, 163), (114, 9, 183), (181, 23, 158)]),
            side_colors=_ring([(58, 12, 163), (181, 23, 158)]),
        )
    )
    presets.append(
        _preset(
            "Fire",
            "Black through red and orange to yellow",
            _gradient([(12, 0, 0), (180, 20, 0), (255, 140, 0), (255, 230, 90)], axis="y"),
            brightness=100,
            side_colors=_ring([(180, 20, 0), (255, 140, 0), (255, 230, 90)]),
        )
    )

    # --- Purple-themed presets ---
    presets.append(
        _preset(
            "Deep Purple",
            "Rich purple to violet gradient",
            _gradient([(48, 0, 96), (88, 28, 168), (138, 43, 226), (186, 85, 211)]),
            side_colors=_ring([(48, 0, 96), (138, 43, 226), (186, 85, 211)]),
        )
    )
    presets.append(
        _preset(
            "Amethyst",
            "Soft amethyst to lavender gradient",
            _gradient([(99, 30, 153), (138, 80, 190), (186, 140, 220), (221, 160, 221)]),
            side_colors=_ring([(99, 30, 153), (186, 140, 220), (221, 160, 221)]),
        )
    )
    presets.append(
        _preset(
            "Royal Purple",
            "Deep royal purple with magenta accents",
            _gradient([(36, 0, 72), (75, 0, 130), (123, 104, 238), (147, 112, 219)]),
            side_colors=_ring([(36, 0, 72), (123, 104, 238), (147, 112, 219)]),
        )
    )
    presets.append(
        _preset(
            "Violet Dream",
            "Dark violet to bright violet gradient",
            _gradient([(28, 0, 56), (75, 0, 130), (138, 43, 226), (238, 130, 238)]),
            side_colors=_ring([(28, 0, 56), (138, 43, 226), (238, 130, 238)]),
        )
    )
    presets.append(
        _preset(
            "Plum Crazy",
            "Rich plum with pink highlights",
            _gradient([(55, 10, 80), (102, 20, 153), (158, 50, 180), (219, 112, 147)]),
            side_colors=_ring([(55, 10, 80), (158, 50, 180), (219, 112, 147)]),
        )
    )
    presets.append(
        _preset(
            "Purple Haze",
            "Misty purple with cyan highlights (Jimi style)",
            _gradient([(51, 0, 76), (102, 25, 153), (153, 51, 204), (178, 102, 255)]),
            side_colors=_ring([(51, 0, 76), (153, 51, 204), (178, 102, 255)]),
        )
    )
    presets.append(
        _preset(
            "Lavender Fields",
            "Soft lavender to white gradient",
            _gradient([(160, 140, 200), (190, 170, 220), (220, 200, 240), (245, 240, 255)]),
            brightness=80,
            side_colors=_ring([(160, 140, 200), (220, 200, 240), (245, 240, 255)]),
        )
    )

    # --- Additional color presets ---
    presets.append(
        _preset(
            "Emerald Forest",
            "Deep green to emerald gradient",
            _gradient([(0, 40, 20), (0, 100, 50), (50, 200, 100), (100, 255, 150)]),
            side_colors=_ring([(0, 40, 20), (50, 200, 100), (100, 255, 150)]),
        )
    )
    presets.append(
        _preset(
            "Golden Hour",
            "Warm gold to amber gradient",
            _gradient([(80, 50, 0), (180, 120, 0), (255, 180, 50), (255, 220, 120)]),
            side_colors=_ring([(80, 50, 0), (255, 180, 50), (255, 220, 120)]),
        )
    )
    presets.append(
        _preset(
            "Arctic Ice",
            "Cool cyan to ice blue gradient",
            _gradient([(0, 80, 120), (0, 150, 200), (100, 200, 255), (180, 230, 255)]),
            side_colors=_ring([(0, 80, 120), (100, 200, 255), (180, 230, 255)]),
        )
    )
    presets.append(
        _preset(
            "Rose Gold",
            "Elegant rose gold gradient",
            _gradient([(80, 40, 50), (180, 100, 120), (230, 160, 170), (255, 210, 220)]),
            brightness=85,
            side_colors=_ring([(80, 40, 50), (230, 160, 170), (255, 210, 220)]),
        )
    )
    presets.append(
        _preset(
            "Neon Green",
            "Bright matrix-style green with dark base",
            _wasd([_hex((0, 15, 0))] * len(KEYS), "#00FF44"),
            side_colors=_ring([(0, 15, 0), (0, 255, 68), (0, 100, 30)]),
        )
    )
    presets.append(
        _preset(
            "Hot Pink",
            "Vibrant hot pink with magenta accent",
            _gradient([(80, 0, 50), (180, 20, 120), (255, 60, 180), (255, 150, 220)]),
            side_colors=_ring([(80, 0, 50), (255, 60, 180), (255, 150, 220)]),
        )
    )
    presets.append(
        _preset(
            "Electric Blue",
            "Intense electric blue with cyan pop",
            _gradient([(0, 20, 80), (0, 80, 180), (0, 180, 255), (100, 220, 255)]),
            side_colors=_ring([(0, 20, 80), (0, 180, 255), (100, 220, 255)]),
        )
    )

    # --- Software effect presets (animated, rendered on host) ---
    software_effects = [
        ("Matrix", "matrix", "Classic green matrix rain", 55, (0, 255, 80), (0, 120, 255)),
        ("Fire Storm", "fire", "Intense fire animation", 80, (255, 60, 0), (255, 200, 0)),
        ("Ocean Breeze", "ocean", "Calm ocean waves", 40, (0, 100, 180), (0, 200, 255)),
        ("Rainbow Flow", "rainbow", "Full spectrum rainbow wave", 60, (255, 0, 0), (0, 0, 255)),
        ("Breathing Ember", "breathing", "Slow breathing ember glow", 25, (200, 40, 0), (0, 0, 0)),
        ("Purple Pulse", "breathing", "Slow purple breathing", 20, (120, 0, 180), (0, 0, 0)),
        ("Reactive Spark", "reactive", "Keys spark on press", 70, (255, 255, 255), (100, 100, 255)),
        ("Gradient Shift", "gradient", "Smooth gradient animation", 45, (180, 0, 180), (0, 180, 180)),
    ]
    for name, effect, desc, speed, c1, c2 in software_effects:
        s = LightingState()
        s.mode = "software"
        s.effect = effect
        s.color1 = c1
        s.color2 = c2
        s.color_mode = 0x10
        s.speed = speed
        s.brightness = 100
        presets.append(Preset.from_state(name, s, desc))

    # --- Hardware effect presets (firmware-driven) ---
    hardware_effects = [
        ("Static Purple", "static", (100, 0, 180), (0, 0, 0), 0, 100, "left_to_right", "Solid purple"),
        ("Static Cyan", "static", (0, 200, 255), (0, 0, 0), 0, 100, "left_to_right", "Solid cyan"),
        ("Static White", "static", (255, 255, 255), (0, 0, 0), 0, 90, "left_to_right", "Solid white"),
        ("Purple Wave", "wave", (100, 0, 180), (180, 0, 255), 0x10, 65, "left_to_right", "Purple/cyan wave"),
        ("Purple Breathing", "breathing", (130, 0, 200), (60, 0, 120), 0x10, 30, "left_to_right", "Purple breathing"),
        ("Purple Tornado", "tornado", (120, 0, 190), (180, 40, 255), 0x10, 55, "clockwise", "Purple tornado"),
        ("Purple Reactive", "reactive", (140, 0, 210), (50, 0, 100), 0x10, 75, "left_to_right", "Purple reactive"),
        ("Purple Matrix", "matrix", (80, 0, 160), (160, 60, 255), 0x10, 50, "left_to_right", "Purple matrix"),
        ("Rainbow Wave HW", "wave", (255, 0, 0), (0, 0, 255), 2, 70, "left_to_right", "Firmware rainbow wave"),
        ("Yeti Purple", "yeti", (100, 0, 180), (180, 0, 255), 0x10, 60, "left_to_right", "Yeti purple"),
    ]
    for name, effect, c1, c2, cmode, speed, direction, desc in hardware_effects:
        s = LightingState()
        s.mode = "hardware"
        s.effect = effect
        s.color1 = c1
        s.color2 = c2
        s.color_mode = cmode
        s.speed = speed
        s.brightness = 100
        s.direction = direction
        presets.append(Preset.from_state(name, s, desc))

    return presets


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    for preset in build_presets():
        path = OUT / f"{preset.name.replace(' ', '_')}.json"
        path.write_text(json.dumps(preset.to_dict(), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
