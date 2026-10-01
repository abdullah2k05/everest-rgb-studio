"""LED map and key layout consistency tests."""

from everest_rgb.hardware.led_map import (
    LED_INDEX_BY_POSITION,
    NUM_KEYS,
    NUM_SIDE_LEDS,
    SIDE_LED_INDICES,
    led_index_for_key,
)
from everest_rgb.models.keyboard import BOARD_WIDTH, KEYS, KEY_BY_NAME, KEYS_BY_ROW


def test_key_count():
    assert len(KEYS) == NUM_KEYS == 64


def test_row_counts():
    assert [len(row) for row in KEYS_BY_ROW] == [14, 14, 13, 14, 9]


def test_rows_are_fifteen_units():
    for row in KEYS_BY_ROW:
        assert abs(sum(k.w for k in row) - BOARD_WIDTH) < 1e-9


def test_key_order_matches_led_map():
    for key in KEYS:
        assert key.led_index == LED_INDEX_BY_POSITION[key.index]
    assert [k.index for k in KEYS] == list(range(NUM_KEYS))


def test_key_names_unique():
    names = [k.name for k in KEYS]
    assert len(names) == len(set(names))


def test_esc_is_led_zero():
    assert KEY_BY_NAME["ESC"].led_index == 0


def test_side_ring():
    assert NUM_SIDE_LEDS == 44
    assert SIDE_LED_INDICES == tuple(range(126, 170))


def test_led_index_lookup():
    assert led_index_for_key(KEY_BY_NAME["W"].index) == 44
    try:
        led_index_for_key(64)
    except IndexError:
        pass
    else:
        raise AssertionError("expected IndexError")


def test_keys_do_not_overlap_horizontally():
    for row in KEYS_BY_ROW:
        x = 0.0
        for key in row:
            assert abs(key.x - x) < 1e-9, f"{key.name} misplaced"
            x += key.w
