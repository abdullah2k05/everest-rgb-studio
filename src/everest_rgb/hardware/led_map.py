"""Hardware LED addressing for the MOUNTAIN Everest 60.

Holds every raw LED address so no numeric hardware addresses leak into the
rest of the application.
"""

from __future__ import annotations

# Number of physical keys with per-key LEDs.
NUM_KEYS = 64

# Side LED ring: 44 RGB LEDs around the perimeter, clockwise starting above
# ESC.
SIDE_LED_INDICES: tuple[int, ...] = tuple(range(126, 170))
NUM_SIDE_LEDS = len(SIDE_LED_INDICES)

# Logical key position -> firmware LED address, row by row.
# Row order and labels must stay in sync with everest_rgb.models.keyboard.
LED_INDEX_BY_POSITION: tuple[int, ...] = (
    # Row 0: ESC  1    2    3    4    5    6    7    8    9    0    -    =   BSPC
    0, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34,
    # Row 1: TAB  Q    W    E    R    T    Y    U    I    O    P    [    ]    \
    42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
    # Row 2: CAPS A    S    D    F    G    H    J    K    L    ;    '  ENTER
    63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 76,
    # Row 3: LSFT Z    X    C    V    B    N    M    ,    .    /   RSFT  ↑  DEL
    84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 97, 99, 56,
    # Row 4: LCTL LWIN LALT SPC  RALT FN   ←    ↓    →
    105, 106, 107, 110, 113, 115, 119, 120, 121,
)

assert len(LED_INDEX_BY_POSITION) == NUM_KEYS, "LED map must cover all keys"

# Convenience view used by the protocol layer (same order as key positions).
LED_INDICES: tuple[int, ...] = LED_INDEX_BY_POSITION


def led_index_for_key(key_position: int) -> int:
    if not 0 <= key_position < NUM_KEYS:
        raise IndexError(f"key position out of range: {key_position}")
    return LED_INDEX_BY_POSITION[key_position]
