"""Standard software effects."""

from __future__ import annotations

import math
import random

from .base import (
    RGB,
    Effect,
    RenderContext,
    brightness_factor,
    key_progress,
    lerp_color,
    scale,
    speed_factor,
    wave_phase,
)


class StaticEffect(Effect):
    name = "static"
    label = "Static"
    description = "The painted key map, held steady"
    uses_secondary = False

    def render(self, ctx: RenderContext):
        return self.frame(ctx, self.base_keys(ctx))


class BreathingEffect(Effect):
    name = "breathing"
    label = "Breathing"
    description = "Brightness oscillates over time"

    def render(self, ctx: RenderContext):
        speed = speed_factor(ctx.state)
        phase = ctx.t * (0.15 + 0.5 * speed) * math.tau
        oscillation = (math.sin(phase) + 1.0) / 2.0
        oscillation = 0.15 + 0.85 * oscillation
        base = self.base_keys(ctx)
        factor = brightness_factor(ctx.state) * oscillation
        keys = [scale(c, factor) for c in base]
        side = [scale(c, factor) for c in ctx.state.side_colors]
        return keys, side


class RainbowEffect(Effect):
    name = "rainbow"
    label = "Rainbow"
    description = "Rainbow gradient flowing across the board"

    def render(self, ctx: RenderContext):
        speed = speed_factor(ctx.state)
        hue_offset = ctx.t * (0.05 + 0.25 * speed)
        reverse = ctx.state.direction in ("right_to_left", "bottom_to_top")
        keys = []
        for key in _key_list():
            p = key_progress(key, "y" if ctx.state.direction in ("top_to_bottom", "bottom_to_top") else "x")
            if reverse:
                p = 1.0 - p
            keys.append(_hue((p * 0.75 + hue_offset) % 1.0))
        side = []
        for i, led in enumerate(_side_list()):
            p = i / max(1, len(_side_list()) - 1)
            side.append(_hue((p * 0.75 + hue_offset) % 1.0))
        return self.frame(ctx, keys, side)


class WaveEffect(Effect):
    name = "wave"
    label = "Wave"
    description = "A soft band of light sweeping across the keys"

    def render(self, ctx: RenderContext):
        color1 = ctx.state.color1
        color2 = ctx.state.color2 if ctx.state.color_mode != 0x00 else color1
        vertical = ctx.state.direction in ("top_to_bottom", "bottom_to_top")
        keys = []
        for key in _key_list():
            progress = key_progress(key, "y" if vertical else "x")
            if ctx.state.direction in ("right_to_left", "bottom_to_top"):
                progress = 1.0 - progress
            phase = wave_phase(ctx, progress, cycles=1.0)
            band = (math.sin(phase * math.tau) + 1.0) / 2.0
            band = band ** 1.5
            keys.append(lerp_color(color2, color1, band))
        side = [
            lerp_color(color2, color1, (math.sin((i / len(_side_list()) + ctx.t * -0.2) * math.tau) + 1) / 2)
            for i in range(len(_side_list()))
        ]
        return self.frame(ctx, keys, side)


class ReactiveEffect(Effect):
    name = "reactive"
    label = "Reactive"
    description = "Keys light up when pressed (needs key input)"

    def render(self, ctx: RenderContext):
        base = [scale(c, 0.35) for c in self.base_keys(ctx, default=(40, 40, 40))]
        color = ctx.state.color1
        for index in ctx.pressed:
            if 0 <= index < len(base):
                base[index] = color
        return self.frame(ctx, base)


class GradientEffect(Effect):
    name = "gradient"
    label = "Gradient"
    description = "User-defined gradient between two colors"

    def render(self, ctx: RenderContext):
        vertical = ctx.state.direction in ("top_to_bottom", "bottom_to_top")
        reverse = ctx.state.direction in ("right_to_left", "bottom_to_top")
        keys = []
        for key in _key_list():
            p = key_progress(key, "y" if vertical else "x")
            if reverse:
                p = 1.0 - p
            keys.append(lerp_color(ctx.state.color1, ctx.state.color2, p))
        side = [
            lerp_color(ctx.state.color1, ctx.state.color2, i / max(1, len(_side_list()) - 1))
            for i in range(len(_side_list()))
        ]
        return self.frame(ctx, keys, side)


class FireEffect(Effect):
    name = "fire"
    label = "Fire"
    description = "Procedural red/orange/yellow flames"
    uses_secondary = False

    _PALETTE = [(8, 0, 0), (120, 8, 0), (220, 70, 0), (255, 150, 10), (255, 235, 120)]

    def render(self, ctx: RenderContext):
        speed = speed_factor(ctx.state)
        keys = []
        for key in _key_list():
            fy = 1.0 - key.y / 4.0  # higher rows are hotter
            flicker = math.sin(ctx.t * (2.0 + 3.0 * speed) + key.x * 1.7 + key.row * 0.9)
            flicker += 0.5 * math.sin(ctx.t * (5.3 * speed) + key.col * 2.3)
            heat = max(0.0, min(1.0, fy * 0.75 + 0.35 + flicker * 0.12))
            keys.append(_heat_color(heat))
        side = [_heat_color(max(0.0, math.sin(ctx.t * speed + i) * 0.5 + 0.5)) for i in range(len(_side_list()))]
        return self.frame(ctx, keys, side)


class OceanEffect(Effect):
    name = "ocean"
    label = "Ocean"
    description = "Rolling blue/cyan swells"

    def render(self, ctx: RenderContext):
        speed = speed_factor(ctx.state)
        keys = []
        for key in _key_list():
            p = key.y / 4.0 * 0.6 + key_progress(key) * 0.4
            swell = math.sin(p * math.tau * 1.5 - ctx.t * (0.6 + 1.2 * speed))
            swell += 0.4 * math.sin(p * math.tau * 3.7 + ctx.t * (0.3 + 0.7 * speed))
            level = (swell + 1.4) / 2.8
            keys.append(lerp_color((0, 20, 60), (70, 210, 255), level))
        side = [
            lerp_color((0, 20, 60), (70, 210, 255),
                       (math.sin(i * 0.5 - ctx.t * (0.8 + speed)) + 1) / 2)
            for i in range(len(_side_list()))
        ]
        return self.frame(ctx, keys, side)


class MatrixEffect(Effect):
    name = "matrix"
    label = "Matrix"
    description = "Green rain in digital columns"
    uses_secondary = False

    def __init__(self):
        self._seed = random.Random(0xE8E57)
        self._drops: list[dict] = []
        self._init_columns()

    def _init_columns(self):
        self._drops = []
        for col in range(15):
            self._drops.append(
                {
                    "pos": self._seed.uniform(-5, 5),
                    "speed": self._seed.uniform(1.5, 3.5),
                    "len": self._seed.uniform(3, 7),
                    "col": col,
                }
            )

    def render(self, ctx: RenderContext):
        speed = speed_factor(ctx.state)
        base = ctx.state.color1 if ctx.state.color1 != (255, 255, 255) else (0, 255, 80)
        trail = ctx.state.color2 if ctx.state.color_mode == 0x10 else (0, 60, 20)

        keys = [(0, 4, 0)] * len(_key_list())
        for drop in self._drops:
            drop["pos"] += drop["speed"] * (0.5 + speed * 0.6) * (ctx.dt or 0.033)
            if drop["pos"] - drop["len"] > 6:
                drop["pos"] = -self._seed.uniform(0, 3)
                drop["speed"] = self._seed.uniform(1.5, 3.5)
                drop["len"] = self._seed.uniform(3, 7)
            for key in _key_list():
                if key.col != drop["col"] and not (drop["col"] == 14 and key.w > 2):
                    continue
                head = drop["pos"]
                tail = drop["pos"] - drop["len"]
                if tail <= key.y <= head or tail <= key.y + 1 <= head:
                    distance = head - (key.y + 0.5)
                    if distance < 1.0:
                        keys[key.index] = base
                    else:
                        fade = max(0.0, 1.0 - distance / drop["len"])
                        keys[key.index] = lerp_color((0, 4, 0), trail, fade)
        side = [(0, 6, 0)] * len(_side_list())
        return self.frame(ctx, keys, side)


# ---------------------------------------------------------------------------
# helpers / registry
# ---------------------------------------------------------------------------

def _hue(h: float) -> RGB:
    from .base import hsv_to_rgb

    return hsv_to_rgb(h, 0.95, 1.0)


def _heat_color(heat: float) -> RGB:
    palette = FireEffect._PALETTE
    heat = max(0.0, min(1.0, heat)) * (len(palette) - 1)
    i = min(int(heat), len(palette) - 2)
    return lerp_color(palette[i], palette[i + 1], heat - i)


def _key_list():
    from ..models.keyboard import KEYS

    return KEYS


def _side_list():
    from ..models.keyboard import SIDE_LED_POSITIONS

    return SIDE_LED_POSITIONS


EFFECT_CLASSES: list[type[Effect]] = [
    StaticEffect,
    BreathingEffect,
    RainbowEffect,
    WaveEffect,
    GradientEffect,
    ReactiveEffect,
    FireEffect,
    OceanEffect,
    MatrixEffect,
]

EFFECTS: dict[str, Effect] = {cls.name: cls() for cls in EFFECT_CLASSES}
