#!/usr/bin/env python3
"""Regenerate built-in preset JSON files.

Run from the repository root:

    python tools/gen_builtin_presets.py
"""

from __future__ import annotations

import colorsys
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from everest_rgb.hardware.protocol import COLOR_DUAL, COLOR_SINGLE  # noqa: E402
from everest_rgb.models.keyboard import BOARD_HEIGHT, BOARD_WIDTH, KEY_BY_NAME, KEYS  # noqa: E402
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


# ---------------------------------------------------------------------------
# composition helpers (for the showcase presets below)
# ---------------------------------------------------------------------------


def _ramp(colors: list[tuple], t: float) -> tuple:
    """Interpolate a stop list at 0..1."""
    t = max(0.0, min(1.0, t)) * (len(colors) - 1)
    i = min(int(t), len(colors) - 2)
    return _lerp(colors[i], colors[i + 1], t - i)


def _each_rgb(fn) -> list[tuple]:
    """Evaluate ``fn(key) -> (r, g, b)`` for every key."""
    return [tuple(fn(key)) for key in KEYS]


def _rgb(colors: list[str]) -> list[tuple]:
    return [tuple(int(c[i : i + 2], 16) for i in (1, 3, 5)) for c in colors]


def _each(fn) -> list[str]:
    return [_hex(c) for c in _each_rgb(fn)]


def _hsv(h: float, s: float = 1.0, v: float = 1.0) -> tuple:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return (round(r * 255), round(g * 255), round(b * 255))


def _radial(colors: list[tuple], *, cx: float = 7.5, cy: float = 2.5, power: float = 1.0):
    """Glow spreading outwards from a focal key position."""
    far = max(math.hypot(k.center[0] - cx, k.center[1] - cy) for k in KEYS) or 1.0

    def pick(key):
        d = math.hypot(key.center[0] - cx, key.center[1] - cy) / far
        return _ramp(colors, d**power)

    return _each(pick)


def _diagonal(colors: list[tuple], *, flip_y: bool = False, power: float = 1.0) -> list[str]:
    """Sweep corner to corner (top-left first, or bottom-left when flipped)."""

    def pick(key):
        y = key.center[1] / BOARD_HEIGHT
        if flip_y:
            y = 1.0 - y
        return _ramp(colors, ((key.center[0] / BOARD_WIDTH + y) / 2.0) ** power)

    return _each(pick)


def _blobs(base: tuple, blobs: list[tuple]) -> list[str]:
    """Additive light pools: ``(cx, cy, radius, color, strength)`` each."""

    def pick(key):
        r, g, b = base
        for cx, cy, radius, color, strength in blobs:
            d = math.hypot(key.center[0] - cx, key.center[1] - cy) / radius
            if d >= 1.0:
                continue
            f = (1.0 - d) ** 2 * strength
            r += color[0] * f
            g += color[1] * f
            b += color[2] * f
        return (min(255, round(r)), min(255, round(g)), min(255, round(b)))

    return _each(pick)


def _accent(colors: list[str], names, color: tuple) -> list[str]:
    """Force specific keys to a single colour."""
    out = list(colors)
    for name in names:
        out[KEY_BY_NAME[name].index] = _hex(color)
    return out


def _sparkle(colors: list[str], *, count: int, seed: int, star: tuple, pool=None) -> list[str]:
    """Scatter a handful of bright keys (embers, petals, stars)."""
    out = list(colors)
    rng = random.Random(seed)
    indices = list(range(len(KEYS))) if pool is None else list(pool)
    for i in rng.sample(indices, min(count, len(indices))):
        out[i] = _hex(star)
    return out


def _checker(frame: tuple, a: tuple, b: tuple) -> list[str]:
    """Neon checkerboard; anything 1.5u or wider becomes the dark frame."""

    def pick(key):
        if key.w >= 1.5:
            return frame
        return a if (key.row + key.col) % 2 == 0 else b

    return _each(pick)


def _spectrum() -> list[str]:
    """Full HSV wheel, top-left to bottom-right."""

    def pick(key):
        t = (
            key.center[0] / BOARD_WIDTH + key.center[1] / BOARD_HEIGHT
        ) / 2.0
        return _hsv(t)

    return _each(pick)


def _spectrum_ring(count: int = 45) -> list[tuple]:
    return [_hsv(i / (count - 1)) for i in range(count)]


def _software(name: str, description: str, effect: str, **overrides) -> Preset:
    state = LightingState()
    state.mode = "software"
    state.effect = effect
    for key, value in overrides.items():
        setattr(state, key, value)
    return Preset.from_state(name, state, description)


def _firmware(name: str, description: str, effect: str, **overrides) -> Preset:
    state = LightingState()
    state.mode = "hardware"
    state.effect = effect
    for key, value in overrides.items():
        setattr(state, key, value)
    return Preset.from_state(name, state, description)


def _preset(name: str, description: str, colors: list[str], **overrides) -> Preset:
    state = LightingState()
    state.mode = overrides.pop("mode", "custom")
    state.effect = overrides.pop("effect", "static")
    state.key_colors = [
        (int(colors[i][1:3], 16), int(colors[i][3:5], 16), int(colors[i][5:7], 16))
        for i in range(len(KEYS))
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

    presets.extend(showcase_presets())
    return presets


def showcase_presets() -> list[Preset]:
    """High-contrast looks built for the "wait, that's a keyboard?" reaction."""
    presets: list[Preset] = []

    # -- static showpieces -------------------------------------------------

    presets.append(
        _preset(
            "Ultraviolet",
            "Violet bloom radiating from the centre of the board",
            _radial(
                [(255, 240, 255), (196, 108, 255), (112, 16, 250), (26, 0, 64)],
                cx=7.5,
                cy=2.3,
                power=1.0,
            ),
            brightness=100,
            side_colors=_ring([(46, 0, 108), (152, 40, 255), (255, 128, 255), (46, 0, 108)]),
        )
    )

    synth = _gradient([(26, 0, 78), (134, 0, 152), (255, 44, 132), (255, 156, 64)], axis="y")
    synth = _accent(
        synth,
        ("ESC", "W", "A", "S", "D", "ENTER", "SPACE", "UP", "DOWN", "LEFT", "RIGHT"),
        (0, 240, 255),
    )
    presets.append(
        _preset(
            "Synthwave",
            "Miami sunset sweep cut with cyan neon accents",
            synth,
            brightness=100,
            side_colors=_ring([(26, 0, 78), (255, 44, 132), (255, 156, 64), (0, 240, 255)]),
        )
    )

    nuclear = _radial(
        [(240, 255, 180), (150, 255, 0), (34, 200, 0), (0, 38, 10)],
        cx=3.8,
        cy=2.2,
        power=1.0,
    )
    nuclear = _accent(nuclear, ("W", "A", "S", "D"), (255, 255, 238))
    presets.append(
        _preset(
            "Nuclear",
            "Toxic glow pooled over the gaming cluster, white-hot WASD",
            nuclear,
            brightness=100,
            side_colors=_ring([(150, 255, 0), (236, 255, 90), (20, 140, 0), (150, 255, 0)]),
        )
    )

    lava = _gradient([(10, 2, 0), (76, 8, 0), (184, 38, 0), (255, 120, 0), (255, 220, 96)], axis="y")
    lava = _sparkle(
        lava,
        count=5,
        seed=7,
        star=(255, 198, 88),
        pool=[k.index for k in KEYS if k.row <= 1],
    )
    presets.append(
        _preset(
            "Lava Flow",
            "Cracked black crust over a molten floor, embers scattered",
            lava,
            brightness=100,
            side_colors=_ring([(255, 60, 0), (255, 170, 40), (90, 14, 0), (255, 60, 0)]),
        )
    )

    presets.append(
        _preset(
            "Prism",
            "Full-spectrum diagonal, every hue edge to edge",
            _spectrum(),
            brightness=100,
            side_colors=_spectrum_ring(),
        )
    )

    nebula = _blobs(
        (5, 4, 15),
        [
            (4.6, 1.5, 7.0, (255, 0, 140), 0.90),
            (11.4, 3.6, 6.5, (0, 205, 255), 0.85),
            (8.2, 0.7, 5.5, (130, 30, 255), 0.75),
            (2.2, 4.4, 4.5, (255, 130, 20), 0.40),
        ],
    )
    nebula = _sparkle(nebula, count=9, seed=4242, star=(255, 252, 255))
    presets.append(
        _preset(
            "Nebula",
            "Deep space with magenta and cyan gas clouds between the stars",
            nebula,
            brightness=100,
            side_colors=_ring([(30, 0, 64), (200, 0, 160), (0, 190, 255), (30, 0, 64)]),
        )
    )

    gold = _diagonal(
        [(6, 5, 3), (74, 54, 8), (200, 154, 22), (255, 220, 84), (255, 251, 222)],
        flip_y=True,
        power=0.75,
    )
    gold = _accent(gold, ("ESC", "ENTER", "SPACE"), (255, 252, 236))
    presets.append(
        _preset(
            "Midnight Gold",
            "Black to liquid gold with three white-hot focal keys",
            gold,
            brightness=100,
            side_colors=_ring([(18, 14, 6), (255, 200, 70), (120, 90, 20), (18, 14, 6)]),
        )
    )

    frost = _gradient([(238, 252, 255), (140, 232, 255), (18, 170, 246), (0, 46, 118)], axis="y")
    frost = _accent(frost, ("W", "A", "S", "D", "UP", "DOWN", "LEFT", "RIGHT"), (255, 255, 255))
    presets.append(
        _preset(
            "Frostbite",
            "White frost melting into deep-sea blue, pure white WASD and arrows",
            frost,
            brightness=100,
            side_colors=_ring([(238, 252, 255), (0, 190, 255), (0, 60, 140), (238, 252, 255)]),
        )
    )

    sakura = _gradient([(255, 226, 241), (255, 150, 198), (240, 62, 142), (146, 16, 82)], axis="x")
    sakura = _sparkle(
        sakura,
        count=6,
        seed=99,
        star=(255, 255, 255),
        pool=[k.index for k in KEYS if k.center[0] >= 7.5],
    )
    presets.append(
        _preset(
            "Sakura",
            "Cherry-blossom pink sweeping left to right, petals adrift",
            sakura,
            brightness=100,
            side_colors=_ring([(255, 190, 220), (255, 70, 150), (146, 16, 82), (255, 190, 220)]),
        )
    )

    arcade = _checker((48, 8, 78), (0, 236, 255), (255, 26, 160))
    arcade = _accent(arcade, ("ESC", "ENTER", "UP", "DOWN", "LEFT", "RIGHT"), (255, 224, 0))
    presets.append(
        _preset(
            "Arcade",
            "Neon checkerboard on black, yellow coin-slot accents",
            arcade,
            brightness=100,
            side_colors=_ring([(0, 236, 255), (255, 26, 160), (255, 224, 0), (0, 236, 255)]),
        )
    )

    # -- animated (host-rendered) ------------------------------------------

    presets.append(
        _software(
            "Wildfire",
            "Host-rendered flames licking up the whole board",
            "fire",
            brightness=100,
            speed=80,
            color1=(255, 150, 10),
            color2=(120, 8, 0),
            key_colors=_rgb(_gradient([(10, 0, 0), (180, 30, 0), (255, 150, 10), (255, 235, 120)], axis="y")),
            side_colors=_ring([(255, 60, 0), (255, 170, 40), (60, 6, 0), (255, 60, 0)]),
        )
    )

    presets.append(
        _software(
            "Prismatic Wave",
            "Cyan and magenta light sweeping edge to edge",
            "wave",
            brightness=100,
            speed=85,
            direction="left_to_right",
            color1=(0, 240, 255),
            color2=(255, 0, 170),
            color_mode=COLOR_DUAL,
            key_colors=_rgb(_gradient([(0, 240, 255), (255, 0, 170)], axis="x")),
            side_colors=_ring([(0, 240, 255), (255, 0, 170), (0, 240, 255)]),
        )
    )

    presets.append(
        _software(
            "Riptide",
            "Host-rendered ocean swells rolling across the keys",
            "ocean",
            brightness=100,
            speed=70,
            color1=(0, 190, 255),
            color2=(0, 40, 120),
            key_colors=_rgb(_gradient([(0, 20, 60), (0, 110, 200), (70, 210, 255)], axis="x")),
            side_colors=_ring([(0, 20, 60), (0, 170, 255), (70, 210, 255)]),
        )
    )

    presets.append(
        _software(
            "Aurora Pulse",
            "The aurora gradient breathing in and out",
            "breathing",
            brightness=100,
            speed=75,
            color1=(16, 255, 144),
            color2=(150, 60, 255),
            color_mode=COLOR_DUAL,
            key_colors=_rgb(_gradient([(16, 255, 144), (0, 196, 255), (150, 60, 255)], axis="x")),
            side_colors=_ring([(16, 255, 144), (0, 196, 255), (150, 60, 255)]),
        )
    )

    # -- animated (on-device, zero host CPU) --------------------------------

    presets.append(
        _firmware(
            "Vortex",
            "Firmware tornado spinning cyan into magenta",
            "tornado",
            brightness=100,
            speed=70,
            direction="left_to_right",
            color1=(0, 240, 255),
            color2=(255, 0, 170),
            color_mode=COLOR_DUAL,
            key_colors=_rgb(_radial([(255, 120, 240), (0, 240, 255), (40, 0, 80)])),
            side_colors=_ring([(0, 240, 255), (255, 0, 170), (0, 240, 255)]),
        )
    )

    presets.append(
        _firmware(
            "Keypress",
            "Firmware reactive: every key you hit flashes white",
            "reactive",
            brightness=100,
            color1=(255, 255, 255),
            color2=(0, 14, 24),
            color_mode=COLOR_SINGLE,
            key_colors=_rgb(_gradient([(0, 24, 40), (0, 60, 96)], axis="y")),
            side_colors=_ring([(0, 40, 64), (0, 140, 200)]),
        )
    )

    return presets


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # Keep timestamps for presets that already exist so regeneration only
    # rewrites files whose lighting content actually changed.
    previous: dict[str, tuple[float, float]] = {}
    for path in OUT.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            previous[str(data.get("name"))] = (
                float(data.get("created", 0.0)),
                float(data.get("modified", 0.0)),
            )
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    for old in OUT.glob("*.json"):
        old.unlink()
    for preset in build_presets():
        stamp = previous.get(preset.name)
        if stamp is not None:
            preset.created, preset.modified = stamp
        path = OUT / f"{preset.name.replace(' ', '_')}.json"
        path.write_text(json.dumps(preset.to_dict(), indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
