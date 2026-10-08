#!/usr/bin/env python3
"""Reference-compatibility experiment: replay the known-good BaseCamp transaction.

The original BaseCamp-Linux controller physically lit the keyboard with this
exact transaction shape::

    send_feature_report(buf)   ->  sleep(write_settle)   ->  read echo
                                ->  sleep(read_settle)   ->  next command

This script deliberately bypasses ``HidTransport.exchange()`` so the current
transport implementation cannot be a variable in the experiment.  It uses the
installed ``hid`` module directly, the project's protocol builders for the
packet bytes, and the project's detection logic for the device path.

Safety: the target is verified (VID/PID/interface) before a single byte is
written.  No unknown commands, no USB resets, no kernel driver detaching.

Examples::

    # known-good pacing (50 ms / 50 ms) - static red
    python tools/reference_compat_test.py

    # print the packets without touching hardware
    python tools/reference_compat_test.py --dry-run

    # differential: zero settle delay, same packets
    python tools/reference_compat_test.py --write-settle 0 --read-settle 0
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from everest_rgb.hardware import detection, protocol  # noqa: E402

# Reference pacing from devices/everest60/controller.py::_send
REFERENCE_WRITE_SETTLE = 0.050
REFERENCE_READ_SETTLE = 0.050

REFERENCE_VID = 0x3282
REFERENCE_PIDS = (0x0005, 0x0006)
REFERENCE_INTERFACE = 0


class SafetyError(RuntimeError):
    """The target did not match the verified keyboard."""


# ---------------------------------------------------------------------------
# Device handling (raw hidapi - mirrors BaseCamp shared/hid_compat.open_path)
# ---------------------------------------------------------------------------


def open_reference_device(path: bytes):
    import hid

    if not hasattr(hid, "device"):
        raise RuntimeError("installed 'hid' module has no hid.device() (need python-hidapi)")
    dev = hid.device()
    dev.open_path(path)
    return dev


def _hex(data: bytes) -> str:
    return data.hex(" ")


def send_reference(
    dev,
    buf: bytes,
    *,
    write_settle: float,
    read_settle: float,
    retries: int = 3,
    read: bool = True,
) -> tuple[bytes | None, dict]:
    """Replay BaseCamp ``_send`` with configurable pacing.

    Returns the last response plus a timing/result record for the log.
    """
    cmd = buf[1]
    record = {
        "cmd": cmd,
        "tx": bytes(buf),
        "attempts": 0,
        "write_ms": 0.0,
        "write_to_read_ms": 0.0,
        "transaction_ms": 0.0,
        "rx": None,
        "echo_ok": not read,
    }
    response: bytes | None = None
    tx_start = time.perf_counter()

    for attempt in range(retries):
        record["attempts"] = attempt + 1
        t0 = time.perf_counter()
        dev.send_feature_report(bytes(buf))
        t1 = time.perf_counter()
        record["write_ms"] = (t1 - t0) * 1000.0

        if write_settle:
            time.sleep(write_settle)
        t2 = time.perf_counter()
        record["write_to_read_ms"] = (t2 - t1) * 1000.0

        if not read:
            record["transaction_ms"] = (t2 - tx_start) * 1000.0
            record["echo_ok"] = True
            break

        raw = dev.get_feature_report(protocol.REPORT_ID, protocol.REPORT_SIZE)
        response = bytes(raw) if raw else b""
        t3 = time.perf_counter()
        record["transaction_ms"] = (t3 - tx_start) * 1000.0
        record["rx"] = response

        if read_settle:
            time.sleep(read_settle)

        if len(response) >= 2 and response[1] == cmd:
            record["echo_ok"] = True
            break

    return response, record


def print_record(record: dict, *, index: int) -> None:
    status = "OK  " if record["echo_ok"] else "FAIL"
    print(f"[{index}] {status} TX cmd {record['cmd']:#04x}  "
          f"(attempt {record['attempts']})")
    print(f"     TX {_hex(record['tx'])}")
    rx = record["rx"]
    if rx is None:
        print("     RX <none>")
    else:
        print(f"     RX {_hex(rx)}")
    if rx is None:
        print(f"     write {record['write_ms']:.2f} ms | "
              f"transaction {record['transaction_ms']:.2f} ms")
    else:
        print(f"     write {record['write_ms']:.2f} ms | "
              f"write->read {record['write_to_read_ms']:.2f} ms | "
              f"transaction {record['transaction_ms']:.2f} ms")


# ---------------------------------------------------------------------------
# Packet sequences (project protocol builders - independently visible bytes)
# ---------------------------------------------------------------------------


def build_static_sequence(color: tuple[int, int, int], brightness: int) -> list[bytes]:
    r, g, b = color
    return [
        protocol.build_set_mode(protocol.EFFECT_STATIC),
        protocol.build_mode_details(
            protocol.EFFECT_STATIC,
            speed=50,
            brightness=brightness,
            color_mode=protocol.COLOR_SINGLE,
            direction=0,
            color1=(r, g, b),
            color2=(0, 0, 0),
        ),
        protocol.build_commit(protocol.EFFECT_STATIC),
    ]


def build_effect_sequence(
    effect: int,
    color1: tuple[int, int, int],
    color2: tuple[int, int, int],
    *,
    speed: int,
    brightness: int,
    color_mode: int,
    direction: int,
) -> list[bytes]:
    return [
        protocol.build_set_mode(effect),
        protocol.build_mode_details(
            effect,
            speed=speed,
            brightness=brightness,
            color_mode=color_mode,
            direction=direction,
            color1=color1,
            color2=color2,
        ),
        protocol.build_commit(effect),
    ]


def build_custom_sequence(
    key_colors: list[tuple[int, int, int]],
    side_colors: list[tuple[int, int, int]] | None,
    brightness: int,
) -> list[bytes]:
    """Custom mode stream - deliberately contains no 0x17 (white flash)."""
    from everest_rgb.hardware.led_map import (
        LED_INDEX_BY_POSITION,
        NUM_KEYS,
        NUM_SIDE_LEDS,
        SIDE_LED_INDICES,
    )

    colors = list(key_colors)[:NUM_KEYS]
    colors.extend([(0, 0, 0)] * (NUM_KEYS - len(colors)))
    stream: list[tuple[int, int, int, int]] = [
        (LED_INDEX_BY_POSITION[i], *colors[i]) for i in range(NUM_KEYS)
    ]
    if side_colors is not None:
        side = list(side_colors)[:NUM_SIDE_LEDS]
        side.extend([(0, 0, 0)] * (NUM_SIDE_LEDS - len(side)))
        for hw, rgb in zip(SIDE_LED_INDICES, side):
            stream.append((hw, *rgb))

    return (
        [
            protocol.build_set_mode(protocol.EFFECT_CUSTOM),
            protocol.build_commit(protocol.EFFECT_CUSTOM),
            protocol.build_custom_begin(brightness),
        ]
        + protocol.build_custom_map_packets(stream)
        + [protocol.build_custom_end(), protocol.build_commit(protocol.EFFECT_CUSTOM)]
    )


# ---------------------------------------------------------------------------
# Safety gate
# ---------------------------------------------------------------------------


def resolve_device(*, interface: int = REFERENCE_INTERFACE,
                   path: str | None = None) -> detection.DeviceInfo | None:
    """Locate the target and refuse anything that is not the verified keyboard."""
    devices = detection.enumerate_devices()
    if not devices:
        return None

    if path is not None:
        candidates = [d for d in devices if d.path_str == path]
    else:
        candidates = [d for d in devices if d.interface == interface]
        if not candidates and interface == REFERENCE_INTERFACE:
            # fall back to the normal selection logic (keyboard usage first)
            selected = detection.select_lighting_device(devices)
            candidates = [selected] if selected else []

    if not candidates:
        return None

    info = candidates[0]
    problems = []
    if info.vendor_id != REFERENCE_VID:
        problems.append(f"VID {info.vendor_id:#06x} != {REFERENCE_VID:#06x}")
    if info.product_id not in REFERENCE_PIDS:
        problems.append(f"PID {info.product_id:#06x} not in "
                        f"{[f'{p:#06x}' for p in REFERENCE_PIDS]}")
    if info.interface != interface:
        problems.append(f"interface {info.interface} != requested {interface}")
    if problems:
        raise SafetyError("refusing to send: " + "; ".join(problems))
    return info


def print_enumeration() -> None:
    try:
        devices = detection.enumerate_devices()
    except Exception as exc:  # pragma: no cover
        print(f"enumeration failed: {exc}")
        return
    for d in devices:
        print(f"  {d.path_str}  if={d.interface} "
              f"usage={d.usage_page:#04x}/{d.usage:#04x}  {d.device_name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_color(value: str) -> tuple[int, int, int]:
    from everest_rgb.models.lighting import hex_to_rgb

    return hex_to_rgb(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=("static", "custom", "off", "effect"),
                        default="static")
    parser.add_argument("--color", default="#ff0000", help="static colour (#rrggbb)")
    parser.add_argument("--side", default=None, help="side ring colour for custom mode")
    parser.add_argument("--brightness", type=int, default=100)
    parser.add_argument("--speed", type=int, default=50)
    parser.add_argument("--direction", default="left_to_right",
                        choices=sorted(protocol.DIRECTIONS))
    parser.add_argument("--color-mode", default="single",
                        choices=("single", "dual", "rainbow"))
    parser.add_argument("--color2", default="#0000ff")
    parser.add_argument("--effect", default="wave",
                        choices=sorted(protocol.EFFECTS_BY_NAME))
    parser.add_argument("--write-settle", type=float, default=REFERENCE_WRITE_SETTLE,
                        help="seconds to sleep after every feature report write")
    parser.add_argument("--read-settle", type=float, default=REFERENCE_READ_SETTLE,
                        help="seconds to sleep after every feature report read")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--no-read", action="store_true",
                        help="write only - skip every GET_FEATURE_REPORT "
                             "(tests whether reads disturb the firmware)")
    parser.add_argument("--reset", action="store_true",
                        help="lead the sequence with the 0x03 handshake that "
                             "unlocks colour payloads on the keyboard")
    parser.add_argument("--interface", type=int, default=None,
                        help="target this HID interface (default: interface 0)")
    parser.add_argument("--path", default=None,
                        help="target this hidraw path exactly (still safety checked)")
    parser.add_argument("--list", action="store_true",
                        help="list every matching HID collection and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="print packets and target, touch no hardware")
    args = parser.parse_args(argv)

    print("Everest reference-compatibility test")
    print("------------------------------------")
    print("collections:")
    print_enumeration()
    print()

    if args.list:
        return 0

    interface = REFERENCE_INTERFACE if args.interface is None else args.interface
    try:
        info = resolve_device(interface=interface, path=args.path)
    except SafetyError as exc:
        print(f"SAFETY: {exc}", file=sys.stderr)
        return 2
    if info is None:
        print("device not found", file=sys.stderr)
        return 1

    print(f"target:   {info.device_name}")
    print(f"vid:pid:  {info.vendor_id:04x}:{info.product_id:04x}")
    print(f"if:       {info.interface}")
    print(f"path:     {info.path_str}")
    print(f"pacing:   write {args.write_settle * 1000:.0f} ms / "
          f"read {args.read_settle * 1000:.0f} ms"
          + ("  (READS DISABLED)" if args.no_read else ""))
    print()

    if args.mode == "custom":
        keys = [(255, 0, 0)] * 64
        side = parse_color(args.side) * 44 if args.side else None
        packets = build_custom_sequence(keys, side, args.brightness)
        label = "custom all-red"
    elif args.mode == "off":
        packets = [protocol.build_set_mode(protocol.EFFECT_OFF),
                   protocol.build_mode_details(protocol.EFFECT_OFF,
                                               brightness=args.brightness,
                                               color_mode=protocol.COLOR_SINGLE,
                                               color1=(0, 0, 0)),
                   protocol.build_commit(protocol.EFFECT_OFF)]
        label = "lighting off"
    elif args.mode == "effect":
        effect = protocol.EFFECTS_BY_NAME[args.effect]
        packets = build_effect_sequence(
            effect,
            parse_color(args.color),
            parse_color(args.color2),
            speed=args.speed,
            brightness=args.brightness,
            color_mode={"single": protocol.COLOR_SINGLE,
                        "dual": protocol.COLOR_DUAL,
                        "rainbow": protocol.COLOR_RAINBOW}[args.color_mode],
            direction=protocol.DIRECTIONS[args.direction],
        )
        label = f"effect {args.effect} {args.color_mode}"
    else:
        packets = build_static_sequence(parse_color(args.color), args.brightness)
        label = f"static {args.color} @ {args.brightness}%"

    if args.reset:
        packets = [protocol.build_reset()] + packets
        label = f"{label} after 0x03"

    print(f"sequence: {label} ({len(packets)} packets)")
    expected = [p[1] for p in packets]
    print(f"commands: {' '.join(f'{c:#04x}' for c in expected)}")
    print()

    for i, packet in enumerate(packets):
        print(f"packet[{i}] {_hex(packet)}")
    print()

    if args.dry_run:
        print("dry run - no bytes written")
        return 0

    dev = open_reference_device(info.path)
    all_ok = True
    started = time.perf_counter()
    try:
        for i, packet in enumerate(packets):
            _, record = send_reference(
                dev,
                packet,
                write_settle=args.write_settle,
                read_settle=args.read_settle,
                retries=args.retries,
                read=not args.no_read,
            )
            print_record(record, index=i)
            all_ok = all_ok and record["echo_ok"]
    finally:
        dev.close()
    total = time.perf_counter() - started

    print()
    print(f"total {total * 1000:.0f} ms for {len(packets)} packets "
          f"({total / max(1, len(packets)) * 1000:.0f} ms/packet)")
    print("result:", "PASS" if all_ok else "FAIL")
    print()
    print("Now confirm on the physical keyboard:")
    print("  - did the LEDs change to the requested colour/state?")
    print("  - if YES with pacing and NO with --write-settle 0 --read-settle 0,")
    print("    firmware pacing is proven as the regression.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
