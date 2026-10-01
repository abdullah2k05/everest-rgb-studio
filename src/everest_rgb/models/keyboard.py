"""Everest 60 physical key layout.

Coordinates are in key units (1u = one alpha key). The key order matches
``hardware.led_map.LED_INDEX_BY_POSITION`` position for position.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from ..hardware.led_map import LED_INDEX_BY_POSITION, NUM_KEYS, NUM_SIDE_LEDS

# (name, label, width) per row. Every row totals exactly 15u.
_ROWS: tuple[tuple[tuple[str, str, float], ...], ...] = (
    # Row 0
    (
        ("ESC", "ESC", 1), ("1", "1", 1), ("2", "2", 1), ("3", "3", 1),
        ("4", "4", 1), ("5", "5", 1), ("6", "6", 1), ("7", "7", 1),
        ("8", "8", 1), ("9", "9", 1), ("0", "0", 1), ("-", "-", 1),
        ("=", "=", 1), ("BSPC", "BACKSPACE", 2),
    ),
    # Row 1
    (
        ("TAB", "TAB", 1.5), ("Q", "Q", 1), ("W", "W", 1), ("E", "E", 1),
        ("R", "R", 1), ("T", "T", 1), ("Y", "Y", 1), ("U", "U", 1),
        ("I", "I", 1), ("O", "O", 1), ("P", "P", 1), ("[", "[", 1),
        ("]", "]", 1), ("\\", "\\", 1.5),
    ),
    # Row 2
    (
        ("CAPS", "CAPS", 1.75), ("A", "A", 1), ("S", "S", 1), ("D", "D", 1),
        ("F", "F", 1), ("G", "G", 1), ("H", "H", 1), ("J", "J", 1),
        ("K", "K", 1), ("L", "L", 1), (";", ";", 1), ("'", "'", 1),
        ("ENTER", "ENTER", 2.25),
    ),
    # Row 3
    (
        ("LSHIFT", "SHIFT", 2), ("Z", "Z", 1), ("X", "X", 1), ("C", "C", 1),
        ("V", "V", 1), ("B", "B", 1), ("N", "N", 1), ("M", "M", 1),
        (",", ",", 1), (".", ".", 1), ("/", "/", 1), ("RSHIFT", "SHIFT", 1),
        ("UP", "↑", 1), ("DELETE", "DEL", 1),
    ),
    # Row 4
    (
        ("LCTRL", "CTRL", 1.25), ("LWIN", "WIN", 1.25), ("LALT", "ALT", 1.25),
        ("SPACE", "SPACE", 6.25), ("RALT", "ALT", 1), ("FN", "FN", 1),
        ("LEFT", "←", 1), ("DOWN", "↓", 1), ("RIGHT", "→", 1),
    ),
)

KEY_GAP = 0.08  # visual gap between keys, in key units


@dataclass(frozen=True)
class Key:
    """One physical key with its geometry and hardware LED address."""

    index: int          # logical position 0..63 (matches LED map order)
    name: str           # unique id, e.g. "LSHIFT", "W", "\\"
    label: str          # text drawn on the key
    row: int
    col: int
    x: float            # left edge, key units
    y: float           # top edge, key units
    w: float
    h: float = 1.0
    led_index: int = -1

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)

    @property
    def rect(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)


@dataclass(frozen=True)
class SideLed:
    """One LED of the perimeter ring."""

    index: int          # 0..43
    led_index: int      # hardware address (126..169)
    x: float
    y: float


def _build_keys() -> tuple[Key, ...]:
    keys: list[Key] = []
    position = 0
    for row, entries in enumerate(_ROWS):
        x = 0.0
        for col, (name, label, width) in enumerate(entries):
            keys.append(
                Key(
                    index=position,
                    name=name,
                    label=label,
                    row=row,
                    col=col,
                    x=x,
                    y=float(row),
                    w=float(width),
                    led_index=LED_INDEX_BY_POSITION[position],
                )
            )
            x += width
            position += 1
        assert abs(x - 15.0) < 1e-9, f"row {row} is {x}u wide, expected 15u"
    assert len(keys) == NUM_KEYS
    return tuple(keys)


KEYS: tuple[Key, ...] = _build_keys()
KEY_BY_NAME: dict[str, Key] = {key.name: key for key in KEYS}
KEYS_BY_ROW: tuple[tuple[Key, ...], ...] = tuple(
    tuple(k for k in KEYS if k.row == row) for row in range(5)
)

BOARD_WIDTH = 15.0
BOARD_HEIGHT = float(len(_ROWS))


def key_index(name: str) -> int:
    """Logical key position for a key name (raises KeyError when unknown)."""
    return KEY_BY_NAME[name].index


def _build_side_leds() -> tuple[SideLed, ...]:
    """Ring positions: clockwise from above ESC, hugging the board outline."""
    leds: list[SideLed] = []
    width, height = BOARD_WIDTH, BOARD_HEIGHT
    perimeter = 2 * (width + height)
    # Walk the outline clockwise starting top-left.
    for i in range(NUM_SIDE_LEDS):
        dist = (i / NUM_SIDE_LEDS) * perimeter
        if dist < width:                      # top edge, left -> right
            x, y = dist, -0.35
        elif dist < width + height:           # right edge, top -> bottom
            x, y = width + 0.35, dist - width
        elif dist < 2 * width + height:       # bottom edge, right -> left
            x, y = width - (dist - width - height), height + 0.35
        else:                                 # left edge, bottom -> top
            x, y = -0.35, height - (dist - 2 * width - height)
        leds.append(SideLed(index=i, led_index=126 + i, x=x, y=y))
    return tuple(leds)


SIDE_LED_POSITIONS: tuple[SideLed, ...] = _build_side_leds()

# Convenience: full width/height of the drawing area including side ring.
PADDING = 0.9


def __getattr__(name: str):  # pragma: no cover - backwards comfort
    if name == "LEDIDX":
        return LED_INDEX_BY_POSITION
    raise AttributeError(name)
