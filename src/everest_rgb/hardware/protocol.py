"""Everest 60 HID packet builders.

Pure functions: no I/O, no device handles. Every packet produced here is
validated (65 bytes, correct command byte, magic bytes) before it is handed to
the transport layer.

Packet layout (65 byte feature report):

    byte 0     report id (0x00)
    byte 1     command
    bytes 2..4 magic 0x46 0x23 0xEA
    byte 5+    command payload

Verified against real hardware - see README "Protocol reference".
"""

from __future__ import annotations

REPORT_SIZE = 65
REPORT_ID = 0x00
MAGIC = (0x46, 0x23, 0xEA)
MAGIC_BYTES = bytes(MAGIC)

# Commands
CMD_RESET = 0x03
CMD_SET_MODE = 0x16
CMD_MODE_DETAILS = 0x17
CMD_COMMIT = 0x1A
CMD_CUSTOM_BEGIN = 0x34
CMD_CUSTOM_MAP = 0x35
CMD_CUSTOM_END = 0x36

# Firmware effects
EFFECT_STATIC = 0x01
EFFECT_WAVE = 0x02
EFFECT_TORNADO = 0x03
EFFECT_BREATHING = 0x04
EFFECT_REACTIVE = 0x05
EFFECT_MATRIX = 0x06
EFFECT_CUSTOM = 0x07
EFFECT_YETI = 0x08
EFFECT_OFF = 0x09

EFFECT_NAMES: dict[int, str] = {
    EFFECT_STATIC: "Static",
    EFFECT_WAVE: "Wave",
    EFFECT_TORNADO: "Tornado",
    EFFECT_BREATHING: "Breathing",
    EFFECT_REACTIVE: "Reactive",
    EFFECT_MATRIX: "Matrix",
    EFFECT_CUSTOM: "Custom",
    EFFECT_YETI: "Yeti",
    EFFECT_OFF: "Off",
}

EFFECTS_BY_NAME: dict[str, int] = {name.lower(): code for code, name in EFFECT_NAMES.items()}

# Color modes
COLOR_SINGLE = 0x00
COLOR_RAINBOW = 0x02
COLOR_DUAL = 0x10

# Direction values for Wave / Tornado
DIRECTIONS = {
    "left_to_right": 0x00,
    "top_to_bottom": 0x02,
    "right_to_left": 0x04,
    "bottom_to_top": 0x06,
    "cw": 0x0A,
    "ccw": 0x09,
}

# Custom map streaming control
STREAM_MORE = 0x0E
STREAM_LAST = 0x0A

# 65 byte packet - 9 byte header (id/cmd/magic/5 payload bytes) = 56 bytes for
# entries, 56 // 4 = 14 entries per map packet.
COLORS_PER_PACKET = 14

CUSTOM_BEGIN_FLAG = 0xC0


class ProtocolError(ValueError):
    """Raised when a packet or protocol argument is invalid."""


def quantize_step(pct: int | float) -> int:
    """Quantize a 0-100 percentage to the hardware's 25 step scale."""
    value = int(round(max(0, min(100, pct)) / 25) * 25)
    return max(0, min(100, value))


def _check_rgb(r: int, g: int, b: int) -> tuple[int, int, int]:
    for name, v in (("r", r), ("g", g), ("b", b)):
        if not isinstance(v, int) or not 0 <= v <= 255:
            raise ProtocolError(f"{name} must be an int in 0..255, got {v!r}")
    return r, g, b


def _make_buf(cmd: int) -> list[int]:
    if not 0 <= cmd <= 0xFF:
        raise ProtocolError(f"command out of range: {cmd!r}")
    buf = [0x00] * REPORT_SIZE
    buf[1] = cmd
    buf[2], buf[3], buf[4] = MAGIC
    return buf


def validate_packet(packet: bytes | list[int], expected_cmd: int | None = None) -> None:
    """Validate a packet before it is written to the device."""
    if len(packet) != REPORT_SIZE:
        raise ProtocolError(f"packet must be {REPORT_SIZE} bytes, got {len(packet)}")
    if packet[0] != REPORT_ID:
        raise ProtocolError(f"report id must be 0x00, got {packet[0]:#04x}")
    if bytes(packet[2:5]) != MAGIC_BYTES:
        raise ProtocolError(f"bad magic bytes: {bytes(packet[2:5]).hex(' ')}")
    if expected_cmd is not None and packet[1] != expected_cmd:
        raise ProtocolError(
            f"expected command {expected_cmd:#04x}, got {packet[1]:#04x}"
        )


def finalize(buf: list[int], expected_cmd: int) -> bytes:
    """Validate a freshly built buffer and return it as immutable bytes."""
    validate_packet(buf, expected_cmd)
    return bytes(buf)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_reset() -> bytes:
    """0x03 - handshake, sent once per connection before any lighting command.

    Measured on hardware: without it the keyboard acknowledges ``0x17`` and
    ``0x35`` (echo in response byte 1) but discards every colour byte, so only
    ``0x16`` effect selection reaches the LEDs. Sending this first makes colour
    payloads take effect immediately. The unlocked state survives a replug, so
    this is cheap insurance on every open rather than a fix-up for a stuck unit.

    OpenRGB's Mountain 60 controller sends the same packet in its constructor.
    """
    return finalize(_make_buf(CMD_RESET), CMD_RESET)


def build_set_mode(effect: int) -> bytes:
    """0x16 - activate a firmware effect."""
    if effect not in EFFECT_NAMES:
        raise ProtocolError(f"unknown effect code {effect:#04x}")
    buf = _make_buf(CMD_SET_MODE)
    buf[5] = 0x01
    buf[9] = effect
    return finalize(buf, CMD_SET_MODE)


def build_mode_details(
    effect: int,
    *,
    speed: int = 50,
    brightness: int = 100,
    color_mode: int = COLOR_SINGLE,
    direction: int = 0,
    color1: tuple[int, int, int] = (255, 255, 255),
    color2: tuple[int, int, int] = (0, 0, 0),
) -> bytes:
    """0x17 - colors / speed / brightness / direction for an active effect."""
    if effect not in EFFECT_NAMES:
        raise ProtocolError(f"unknown effect code {effect:#04x}")
    if color_mode not in (COLOR_SINGLE, COLOR_RAINBOW, COLOR_DUAL):
        raise ProtocolError(f"unknown color mode {color_mode:#04x}")
    if not 0 <= direction <= 0xFF:
        raise ProtocolError(f"direction out of range: {direction}")

    r1, g1, b1 = _check_rgb(*color1)
    r2, g2, b2 = _check_rgb(*color2)

    buf = _make_buf(CMD_MODE_DETAILS)
    buf[5] = effect
    buf[7] = quantize_step(speed)
    buf[8] = quantize_step(brightness)
    buf[9] = color_mode
    buf[10] = direction
    if color_mode != COLOR_RAINBOW:
        buf[12], buf[13], buf[14] = r1, g1, b1
        if color_mode == COLOR_DUAL:
            buf[15], buf[16], buf[17] = r2, g2, b2
    return finalize(buf, CMD_MODE_DETAILS)


def build_commit(effect: int) -> bytes:
    """0x1A - latch the active effect / just-written custom map."""
    if effect not in EFFECT_NAMES:
        raise ProtocolError(f"unknown effect code {effect:#04x}")
    buf = _make_buf(CMD_COMMIT)
    buf[5] = effect
    return finalize(buf, CMD_COMMIT)


def build_custom_begin(brightness: int) -> bytes:
    """0x34 - start a per-key RGB map transfer."""
    buf = _make_buf(CMD_CUSTOM_BEGIN)
    buf[5] = quantize_step(brightness)
    buf[6] = CUSTOM_BEGIN_FLAG
    return finalize(buf, CMD_CUSTOM_BEGIN)


def build_custom_map(
    entries: list[tuple[int, int, int, int]],
    *,
    last: bool,
) -> bytes:
    """0x35 - one chunk of the per-key map.

    ``entries`` items are ``(led_index, r, g, b)`` - the hardware index comes
    first in every 4 byte slot.
    """
    if not entries:
        raise ProtocolError("map packet requires at least one entry")
    if len(entries) > COLORS_PER_PACKET:
        raise ProtocolError(
            f"at most {COLORS_PER_PACKET} entries per packet, got {len(entries)}"
        )
    buf = _make_buf(CMD_CUSTOM_MAP)
    buf[5] = STREAM_LAST if last else STREAM_MORE
    pos = 9
    for led_index, r, g, b in entries:
        if not 0 <= led_index <= 0xFF:
            raise ProtocolError(f"led index out of range: {led_index}")
        r, g, b = _check_rgb(r, g, b)
        buf[pos] = led_index
        buf[pos + 1] = r
        buf[pos + 2] = g
        buf[pos + 3] = b
        pos += 4
    return finalize(buf, CMD_CUSTOM_MAP)


def build_custom_end() -> bytes:
    """0x36 - end a per-key RGB map transfer."""
    return finalize(_make_buf(CMD_CUSTOM_END), CMD_CUSTOM_END)


def chunk_entries(
    entries: list[tuple[int, int, int, int]],
) -> list[list[tuple[int, int, int, int]]]:
    """Split a full entry stream into packets, padding the final one.

    The final packet must be full: zero padding would be written as index 0
    (ESC) black. Padding duplicates the last real entry instead, which is
    idempotent.
    """
    stream = list(entries)
    if not stream:
        return []
    while len(stream) % COLORS_PER_PACKET != 0:
        stream.append(stream[-1])
    return [
        stream[i : i + COLORS_PER_PACKET]
        for i in range(0, len(stream), COLORS_PER_PACKET)
    ]


def build_custom_map_packets(
    entries: list[tuple[int, int, int, int]],
) -> list[bytes]:
    """All 0x35 packets for an entry stream (padding handled)."""
    packets = []
    chunks = chunk_entries(entries)
    for i, chunk in enumerate(chunks):
        packets.append(build_custom_map(chunk, last=(i == len(chunks) - 1)))
    return packets
