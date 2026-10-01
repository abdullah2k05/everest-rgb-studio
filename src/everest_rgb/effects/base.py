"""Effect base types and shared math."""

from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass
from typing import Sequence

from ..models.keyboard import KEYS, SIDE_LED_POSITIONS, Key
from ..models.lighting import LightingState

RGB = tuple[int, int, int]


@dataclass
class RenderContext:
    """Everything an effect needs to produce one frame."""

    state: LightingState
    t: float                      # seconds since start (monotonic)
    dt: float = 0.0               # seconds since previous frame
    pressed: Sequence[int] = ()   # logical key indices currently pressed
    width: float = 15.0
    height: float = 5.0


def clamp8(value: float) -> int:
    return max(0, min(255, int(round(value))))


def scale(color: RGB, factor: float) -> RGB:
    return (clamp8(color[0] * factor), clamp8(color[1] * factor), clamp8(color[2] * factor))


def lerp_color(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return (
        clamp8(a[0] + (b[0] - a[0]) * t),
        clamp8(a[1] + (b[1] - a[1]) * t),
        clamp8(a[2] + (b[2] - a[2]) * t),
    )


def hsv_to_rgb(h: float, s: float, v: float) -> RGB:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return (clamp8(r * 255), clamp8(g * 255), clamp8(b * 255))


def key_progress(key: Key, axis: str = "x") -> float:
    """0..1 position of a key along the board."""
    if axis == "x":
        center = key.x + key.w / 2
        return center / 15.0
    return (key.y + key.h / 2) / 5.0


def brightness_factor(state: LightingState) -> float:
    return max(0.0, min(1.0, state.brightness / 100.0))


def speed_factor(state: LightingState) -> float:
    """0..1.4 multiplier so speed 50 feels neutral."""
    return max(0.0, min(100, state.speed)) / 50.0


class Effect:
    """Base class for all software effects."""

    name: str = "base"
    label: str = "Base"
    description: str = ""
    uses_secondary: bool = True
    editable: bool = True

    def render(self, ctx: RenderContext) -> tuple[list[RGB], list[RGB]]:
        """Return (key colors, side colors) for this frame."""
        raise NotImplementedError

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def base_keys(ctx: RenderContext, default: RGB | None = None) -> list[RGB]:
        """The user's painted key map, or a flat color fallback."""
        if default is None:
            default = ctx.state.color1
        return list(ctx.state.key_colors) or [default] * len(KEYS)

    def frame(self, ctx: RenderContext, keys: list[RGB], side: list[RGB] | None = None) -> tuple[list[RGB], list[RGB]]:
        factor = brightness_factor(ctx.state)
        keys = [scale(c, factor) for c in keys]
        if side is None:
            side = [ctx.state.side_colors[i] for i in range(len(SIDE_LED_POSITIONS))]
        side = [scale(c, factor) for c in side]
        return keys, side


def wave_phase(ctx: RenderContext, spatial: float, *, cycles: float = 1.0) -> float:
    """Shared travelling-wave phase, 0..1."""
    speed = speed_factor(ctx.state)
    direction = ctx.state.direction
    if direction in ("right_to_left", "bottom_to_top"):
        spatial = 1.0 - spatial
    if direction in ("top_to_bottom", "bottom_to_top"):
        spatial = spatial  # vertical callers pass vertical progress
    return (spatial * cycles - ctx.t * (0.15 + 0.6 * speed)) % 1.0
