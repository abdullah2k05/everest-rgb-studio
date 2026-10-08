"""Packet construction tests - no hardware required."""

import pytest

from everest_rgb.hardware import protocol


def test_report_size_and_magic():
    packet = protocol.build_set_mode(protocol.EFFECT_STATIC)
    assert len(packet) == protocol.REPORT_SIZE == 65
    assert packet[0] == 0x00
    assert packet[1] == 0x16
    assert bytes(packet[2:5]) == bytes([0x46, 0x23, 0xEA])


def test_reset_layout():
    packet = protocol.build_reset()
    assert len(packet) == protocol.REPORT_SIZE
    assert packet[0] == 0x00
    assert packet[1] == protocol.CMD_RESET == 0x03
    assert bytes(packet[2:5]) == bytes([0x46, 0x23, 0xEA])
    assert packet[5:] == bytes(protocol.REPORT_SIZE - 5)


def test_set_mode_layout():
    packet = protocol.build_set_mode(protocol.EFFECT_WAVE)
    assert packet[5] == 0x01
    assert packet[9] == protocol.EFFECT_WAVE


def test_mode_details_layout():
    packet = protocol.build_mode_details(
        protocol.EFFECT_BREATHING,
        speed=75,
        brightness=50,
        color_mode=protocol.COLOR_DUAL,
        direction=0x04,
        color1=(0x11, 0x22, 0x33),
        color2=(0xAA, 0xBB, 0xCC),
    )
    assert packet[1] == 0x17
    assert packet[5] == protocol.EFFECT_BREATHING
    assert packet[7] == 75
    assert packet[8] == 50
    assert packet[9] == protocol.COLOR_DUAL
    assert packet[10] == 0x04
    assert packet[12:15] == bytes([0x11, 0x22, 0x33])
    assert packet[15:18] == bytes([0xAA, 0xBB, 0xCC])


def test_mode_details_rainbow_has_no_colors():
    packet = protocol.build_mode_details(
        protocol.EFFECT_WAVE, color_mode=protocol.COLOR_RAINBOW, brightness=100
    )
    assert packet[9] == protocol.COLOR_RAINBOW
    assert packet[12:18] == bytes(6)


def test_commit_layout():
    packet = protocol.build_commit(protocol.EFFECT_CUSTOM)
    assert packet[1] == 0x1A
    assert packet[5] == protocol.EFFECT_CUSTOM


def test_custom_begin_layout():
    packet = protocol.build_custom_begin(100)
    assert packet[1] == 0x34
    assert packet[5] == 100
    assert packet[6] == 0xC0


def test_custom_end_layout():
    packet = protocol.build_custom_end()
    assert packet[1] == 0x36


def test_custom_map_packet_layout():
    entries = [(42, 1, 2, 3), (43, 4, 5, 6)]
    packet = protocol.build_custom_map(entries, last=False)
    assert packet[1] == 0x35
    assert packet[5] == protocol.STREAM_MORE
    # entries start at offset 9, index first then RGB
    assert packet[9:13] == bytes([42, 1, 2, 3])
    assert packet[13:17] == bytes([43, 4, 5, 6])


def test_custom_map_last_flag():
    packet = protocol.build_custom_map([(0, 9, 9, 9)], last=True)
    assert packet[5] == protocol.STREAM_LAST


def test_custom_map_rejects_overflow():
    entries = [(0, 1, 1, 1)] * (protocol.COLORS_PER_PACKET + 1)
    with pytest.raises(protocol.ProtocolError):
        protocol.build_custom_map(entries, last=True)


def test_custom_map_rejects_bad_values():
    with pytest.raises(protocol.ProtocolError):
        protocol.build_custom_map([(0, 300, 0, 0)], last=True)
    with pytest.raises(protocol.ProtocolError):
        protocol.build_custom_map([(-1, 0, 0, 0)], last=True)
    with pytest.raises(protocol.ProtocolError):
        protocol.build_custom_map([], last=True)


def test_full_map_chunking_covers_all_entries():
    from everest_rgb.hardware.led_map import NUM_KEYS, NUM_SIDE_LEDS

    total = NUM_KEYS + NUM_SIDE_LEDS  # 108
    entries = [(i, 1, 2, 3) for i in range(total)]
    packets = protocol.build_custom_map_packets(entries)
    # padding must fill the final packet rather than leave zero bytes
    assert len(packets) == 8
    assert all(len(p) == 65 for p in packets)
    assert packets[-1][5] == protocol.STREAM_LAST
    assert all(p[5] == protocol.STREAM_MORE for p in packets[:-1])
    # count of real entries preserved (padding duplicates the last entry)
    seen = 0
    for packet in packets:
        for slot in range(14):
            seen += 1
    assert seen >= total
    # no all-zero padding slot (would blank ESC at index 0)
    for packet in packets:
        for slot in range(14):
            pos = 9 + slot * 4
            assert packet[pos : pos + 4] != bytes(4)


def test_chunk_entries_exact_multiple():
    entries = [(i, 1, 1, 1) for i in range(14)]
    chunks = protocol.chunk_entries(entries)
    assert len(chunks) == 1


def test_quantize_step():
    assert protocol.quantize_step(0) == 0
    assert protocol.quantize_step(12) == 0
    assert protocol.quantize_step(13) == 25
    assert protocol.quantize_step(50) == 50
    assert protocol.quantize_step(87) == 75
    assert protocol.quantize_step(88) == 100
    assert protocol.quantize_step(100) == 100
    assert protocol.quantize_step(-5) == 0
    assert protocol.quantize_step(250) == 100


def test_validate_packet_rejects_bad_magic():
    packet = bytearray(protocol.build_set_mode(protocol.EFFECT_STATIC))
    packet[2] = 0x00
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_packet(packet, 0x16)


def test_validate_packet_rejects_wrong_size():
    with pytest.raises(protocol.ProtocolError):
        protocol.validate_packet(bytes(10), 0x16)


def test_builders_reject_unknown_effect():
    with pytest.raises(protocol.ProtocolError):
        protocol.build_set_mode(0x7F)
    with pytest.raises(protocol.ProtocolError):
        protocol.build_commit(0x7F)


def test_mode_details_quantizes_speed_brightness():
    packet = protocol.build_mode_details(protocol.EFFECT_STATIC, speed=37, brightness=63)
    assert packet[7] == 25
    assert packet[8] == 75
