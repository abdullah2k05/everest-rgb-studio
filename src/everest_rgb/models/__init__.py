"""Domain models: keyboard layout, lighting state, presets."""

from .keyboard import (
    BOARD_HEIGHT,
    BOARD_WIDTH,
    KEYS,
    KEY_BY_NAME,
    KEYS_BY_ROW,
    Key,
    SideLed,
    SIDE_LED_POSITIONS,
    key_index,
)
from .lighting import (
    LightingState,
    clamp_color,
    hex_to_rgb,
    rgb_to_hex,
)
from .preset import Preset

__all__ = [
    "BOARD_HEIGHT",
    "BOARD_WIDTH",
    "KEYS",
    "KEY_BY_NAME",
    "KEYS_BY_ROW",
    "Key",
    "SideLed",
    "SIDE_LED_POSITIONS",
    "key_index",
    "LightingState",
    "clamp_color",
    "hex_to_rgb",
    "rgb_to_hex",
    "Preset",
]
