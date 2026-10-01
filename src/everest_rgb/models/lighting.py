"""Central lighting state.

The UI mutates this object, the hardware service applies it. Everything that
needs to survive restarts (presets, undo, reconnect restore) serialises
through here.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields
from typing import Any, Iterable

from ..hardware import protocol
from ..hardware.led_map import NUM_KEYS, NUM_SIDE_LEDS

Color = tuple[int, int, int]

DEFAULT_KEY_COLOR: Color = (0, 0, 0)
DEFAULT_SIDE_COLOR: Color = (0, 0, 0)


def clamp_color(color: Iterable[int], default: Color = DEFAULT_KEY_COLOR) -> Color:
    try:
        r, g, b = (int(c) for c in color)
    except (TypeError, ValueError):
        return default
    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


def hex_to_rgb(value: str) -> Color:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ValueError(f"invalid hex color: {value!r}")
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError as exc:
        raise ValueError(f"invalid hex color: {value!r}") from exc


def rgb_to_hex(color: Color) -> str:
    r, g, b = clamp_color(color)
    return f"#{r:02X}{g:02X}{b:02X}"


@dataclass
class LightingState:
    """Everything needed to reproduce the keyboard's lighting."""

    brightness: int = 100
    speed: int = 50
    mode: str = "hardware"                # hardware | software | custom
    effect: str = "static"                # effect name within the active mode
    color1: Color = (255, 255, 255)
    color2: Color = (0, 0, 0)
    color_mode: int = protocol.COLOR_SINGLE
    direction: str = "left_to_right"
    key_colors: list[Color] = field(
        default_factory=lambda: [DEFAULT_KEY_COLOR] * NUM_KEYS
    )
    side_colors: list[Color] = field(
        default_factory=lambda: [DEFAULT_SIDE_COLOR] * NUM_SIDE_LEDS
    )
    selected_color: Color = (255, 255, 255)

    # -- helpers -----------------------------------------------------------

    def copy(self) -> "LightingState":
        return copy.deepcopy(self)

    @property
    def is_custom(self) -> bool:
        return self.mode == "custom"

    @property
    def is_hardware(self) -> bool:
        return self.mode == "hardware"

    @property
    def is_software(self) -> bool:
        return self.mode == "software"

    def key_color(self, index: int) -> Color:
        if 0 <= index < len(self.key_colors):
            return self.key_colors[index]
        return DEFAULT_KEY_COLOR

    def set_key_color(self, index: int, color: Color) -> None:
        if 0 <= index < len(self.key_colors):
            self.key_colors[index] = clamp_color(color)

    def set_key_colors(self, indices: Iterable[int], color: Color) -> None:
        color = clamp_color(color)
        for i in indices:
            self.set_key_color(i, color)

    def fill_keys(self, color: Color) -> None:
        self.key_colors = [clamp_color(color)] * NUM_KEYS

    def fill_side(self, color: Color) -> None:
        self.side_colors = [clamp_color(color)] * NUM_SIDE_LEDS

    # -- serialisation -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "brightness": int(self.brightness),
            "speed": int(self.speed),
            "mode": self.mode,
            "effect": self.effect,
            "color1": rgb_to_hex(self.color1),
            "color2": rgb_to_hex(self.color2),
            "color_mode": int(self.color_mode),
            "direction": self.direction,
            "keys": {str(i): rgb_to_hex(c) for i, c in enumerate(self.key_colors)},
            "side": [rgb_to_hex(c) for c in self.side_colors],
            "selected_color": rgb_to_hex(self.selected_color),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LightingState":
        state = cls()
        state.brightness = int(data.get("brightness", 100))
        state.speed = int(data.get("speed", 50))
        state.effect = str(data.get("effect", "static"))
        mode = data.get("mode")
        if mode is None:
            # Legacy presets: {"mode": "custom"} without an effect field.
            mode = "custom" if state.effect == "custom" else "hardware"
        state.mode = str(mode)
        if state.effect == "custom":
            state.mode = "custom"
            state.effect = "static"
        if state.mode not in ("hardware", "software", "custom"):
            state.mode = "hardware"
        state.color1 = clamp_color(hex_to_rgb(data.get("color1", "#FFFFFF")))
        state.color2 = clamp_color(hex_to_rgb(data.get("color2", "#000000")))
        state.color_mode = int(data.get("color_mode", protocol.COLOR_SINGLE))
        state.direction = str(data.get("direction", "left_to_right"))
        state.selected_color = clamp_color(
            hex_to_rgb(data.get("selected_color", "#FFFFFF"))
        )

        keys = data.get("keys") or {}
        if isinstance(keys, dict):
            # Accept both {"0": "#RRGGBB"} and {"W": "#RRGGBB"} forms.
            from .keyboard import KEY_BY_NAME

            for key_ref, value in keys.items():
                try:
                    index = (
                        KEY_BY_NAME[key_ref].index
                        if str(key_ref) in KEY_BY_NAME
                        else int(key_ref)
                    )
                except (KeyError, ValueError):
                    continue
                state.set_key_color(index, hex_to_rgb(str(value)))
        elif isinstance(keys, list):
            for i, value in enumerate(keys[:NUM_KEYS]):
                state.set_key_color(i, hex_to_rgb(str(value)))

        side = data.get("side")
        if isinstance(side, list):
            for i, value in enumerate(side[:NUM_SIDE_LEDS]):
                state.side_colors[i] = hex_to_rgb(str(value))
        elif isinstance(side, dict):
            for key_ref, value in side.items():
                try:
                    i = int(key_ref)
                except ValueError:
                    continue
                if 0 <= i < NUM_SIDE_LEDS:
                    state.side_colors[i] = hex_to_rgb(str(value))
        return state

    def update(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if not hasattr(self, key):
                raise AttributeError(f"unknown lighting attribute: {key}")
            setattr(self, key, value)
