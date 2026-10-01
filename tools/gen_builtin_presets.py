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
        )
    )
    presets.append(
        _preset(
            "Cyberpunk",
            "Near-black board, WASD in neon cyan",
            _wasd([_hex((18, 4, 34))] * len(KEYS), "#00F0FF"),
        )
    )
    presets.append(
        _preset(
            "Sunset",
            "Warm top-to-bottom sunset gradient",
            _gradient([(255, 94, 58), (255, 0, 95), (58, 7, 109)], axis="y"),
        )
    )
    presets.append(
        _preset(
            "Aurora",
            "Green to violet aurora band",
            _gradient([(16, 255, 144), (0, 196, 255), (150, 60, 255)]),
        )
    )
    presets.append(
        _preset("Minimal White", "Soft white backlight", _solid((232, 232, 232)))
    )
    presets.append(_preset("Red Alert", "Solid red", _solid((255, 32, 32))))
    presets.append(
        _preset(
            "Deep Blue",
            "Midnight blue gradient",
            _gradient([(0, 12, 64), (0, 40, 160), (20, 90, 255)]),
        )
    )
    presets.append(
        _preset(
            "Purple Night",
            "Purple to magenta gradient",
            _gradient([(58, 12, 163), (114, 9, 183), (181, 23, 158)]),
        )
    )
    presets.append(
        _preset(
            "Fire",
            "Black through red and orange to yellow",
            _gradient([(12, 0, 0), (180, 20, 0), (255, 140, 0), (255, 230, 90)], axis="y"),
            brightness=100,
        )
    )

    # Firmware-driven presets (no per-key map needed).
    matrix = LightingState()
    matrix.mode = "hardware"
    matrix.effect = "matrix"
    matrix.color1 = (0, 255, 80)
    matrix.color2 = (0, 120, 255)
    matrix.color_mode = 0x10
    matrix.speed = 60
    presets.append(
        Preset.from_state("Matrix", matrix, "Firmware matrix effect (green/blue)")
    )

    wave = LightingState()
    wave.mode = "hardware"
    wave.effect = "wave"
    wave.color1 = (0, 168, 255)
    wave.color2 = (170, 0, 255)
    wave.color_mode = 0x10
    wave.speed = 65
    wave.direction = "left_to_right"
    presets.append(
        Preset.from_state("Neon Wave", wave, "Firmware wave effect (blue/purple)")
    )

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
