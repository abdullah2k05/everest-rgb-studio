"""Everest RGB Studio command line interface.

Examples::

    everest-rgb detect
    everest-rgb test
    everest-rgb static --color "#ff0000"
    everest-rgb effect wave --color1 "#0080ff" --speed 75
    everest-rgb off
    everest-rgb preset load Coding
    everest-rgb gui
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Sequence

from . import __version__
from .hardware import detection, protocol
from .hardware.everest60 import Everest60, Everest60Error
from .models.lighting import hex_to_rgb, rgb_to_hex
from .utils.logging import setup_logging

log = logging.getLogger(__name__)


def _color(value: str) -> tuple[int, int, int]:
    try:
        return hex_to_rgb(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--debug", action="store_true", help="verbose logging incl. HID packets")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="everest-rgb",
        description="RGB control for the MOUNTAIN Everest 60 keyboard (Linux).",
    )
    parser.add_argument("--version", action="version", version=f"everest-rgb {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")

    p = sub.add_parser("detect", help="find the keyboard and print its HID info")
    _add_common(p)

    p = sub.add_parser("status", help="show connection status")
    _add_common(p)

    p = sub.add_parser("test", help="safe hardware round-trip test (0x16 echo)")
    _add_common(p)

    p = sub.add_parser("static", help="set a solid color")
    p.add_argument("--color", type=_color, required=True, help='e.g. "#ff0000"')
    p.add_argument("--brightness", type=int, default=100, help="0-100 (quantized to 25 steps)")
    _add_common(p)

    p = sub.add_parser("off", help="turn the lighting off")
    _add_common(p)

    p = sub.add_parser("effect", help="run a firmware effect")
    p.add_argument(
        "name",
        choices=sorted(k for k in protocol.EFFECTS_BY_NAME if k not in ("custom", "static")),
        help="firmware effect",
    )
    p.add_argument("--color1", type=_color, default=(255, 255, 255))
    p.add_argument("--color2", type=_color, default=(0, 0, 0))
    p.add_argument("--speed", type=int, default=50)
    p.add_argument("--brightness", type=int, default=100)
    p.add_argument("--direction", default="left_to_right", choices=sorted(protocol.DIRECTIONS))
    p.add_argument("--color-mode", default=None, choices=["single", "dual", "rainbow"])
    _add_common(p)

    p = sub.add_parser("brightness", help="set brightness by re-applying the given mode")
    p.add_argument("value", type=int, help="0-100")
    p.add_argument("--color", type=_color, default=(255, 255, 255), help="color when mode is static")
    _add_common(p)

    p = sub.add_parser("color", help="paint keys per-key (custom mode)")
    p.add_argument("--color", type=_color, default=(255, 255, 255), help="color for all keys")
    p.add_argument("--keys", default="", help="comma separated key names, e.g. W,A,S,D (default: all)")
    p.add_argument("--side", type=_color, default=None, help="also set the side ring color")
    p.add_argument("--brightness", type=int, default=100)
    _add_common(p)

    p = sub.add_parser("side", help="set the side LED ring color")
    p.add_argument("--color", type=_color, required=True)
    p.add_argument("--brightness", type=int, default=100)
    _add_common(p)

    p = sub.add_parser("preset", help="apply or list presets")
    p.add_argument("action", choices=["list", "load", "save"])
    p.add_argument("name", nargs="?", help="preset name for load/save")
    p.add_argument("--from-state", default=None, help="JSON file to save as preset")
    _add_common(p)

    p = sub.add_parser("gui", help="launch the graphical interface")
    _add_common(p)

    return parser


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _connect(debug: bool) -> Everest60:
    kb = Everest60(debug=debug)
    kb.connect()
    return kb


def cmd_detect(_args: argparse.Namespace) -> int:
    print("Everest RGB Studio")
    print("------------------")
    try:
        devices = detection.enumerate_devices()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not devices:
        print("Device:        not found")
        print("Status:        Disconnected")
        print("Hint:          plug in the Everest 60 (VID 3282 PID 0005)")
        return 1

    selected = detection.select_lighting_device(devices)
    for info in devices:
        marker = "->" if selected is info else "  "
        role = "keyboard (lighting)" if info.is_keyboard_collection else (
            "mouse/system" if info.is_mouse_collection else "other"
        )
        print(
            f"{marker} {info.path_str}  if={info.interface} "
            f"usage={info.usage_page:#04x}/{info.usage:#04x}  {role}"
        )

    if selected is None:
        print("Status:        Disconnected (no lighting interface)")
        return 1

    print()
    print(f"Device:        {selected.device_name}")
    print(f"VID:           {selected.vendor_id:04x}")
    print(f"PID:           {selected.product_id:04x}")
    print(f"Interface:     {selected.interface}")
    print(f"Usage page:    {selected.usage_page:#04x}")
    print(f"Usage:         {selected.usage:#04x}")
    print(f"Path:          {selected.path_str}")
    print("Status:        Connected")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    try:
        kb = _connect(args.debug)
    except Everest60Error as exc:
        print("Status:    Disconnected")
        print(f"Error:     {exc}")
        return 1
    try:
        print(f"Status:    Connected ({kb.status.name} @ {kb.status.path})")
        print(f"Interface: {kb.status.interface}")
        return 0
    finally:
        kb.disconnect()


def cmd_test(args: argparse.Namespace) -> int:
    """Harmless round trip: activate static white, verify the command echo."""
    print("Everest 60 hardware test")
    print("------------------------")
    info = detection.find_lighting_device()
    if info is None:
        print("FAIL: device not found")
        return 1
    print(f"device:   {info.device_name} @ {info.path_str} (if {info.interface})")
    try:
        kb = Everest60(debug=args.debug)
        kb.connect(info)
    except Everest60Error as exc:
        print(f"FAIL: could not open device: {exc}")
        return 1

    ok = True
    try:
        for label, packet in (
            ("set mode 0x16", protocol.build_set_mode(protocol.EFFECT_STATIC)),
            ("mode details 0x17", protocol.build_mode_details(protocol.EFFECT_STATIC)),
            ("commit 0x1A", protocol.build_commit(protocol.EFFECT_STATIC)),
        ):
            transport = kb._require_transport()  # noqa: SLF001 - diagnostic command
            response = transport.exchange(packet, expected_cmd=packet[1])
            echoed = response is not None and len(response) >= 2 and response[1] == packet[1]
            print(f"{'ok  ' if echoed else 'FAIL'} {label}")
            ok = ok and echoed
        print(f"tx={transport.tx_count} rx={transport.rx_count}")
    except Everest60Error as exc:
        print(f"FAIL: {exc}")
        ok = False
    finally:
        kb.disconnect()
    print("result:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def cmd_static(args: argparse.Namespace) -> int:
    try:
        kb = _connect(args.debug)
        kb.set_static(args.color, brightness=args.brightness)
    except Everest60Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    kb.disconnect()
    print(f"static {rgb_to_hex(args.color)} @ {args.brightness}%")
    return 0


def cmd_off(args: argparse.Namespace) -> int:
    try:
        kb = _connect(args.debug)
        kb.set_off()
    except Everest60Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    kb.disconnect()
    print("lighting off")
    return 0


def cmd_effect(args: argparse.Namespace) -> int:
    color_mode = {
        "single": protocol.COLOR_SINGLE,
        "dual": protocol.COLOR_DUAL,
        "rainbow": protocol.COLOR_RAINBOW,
    }.get(args.color_mode, protocol.COLOR_DUAL)
    try:
        kb = _connect(args.debug)
        kb.set_effect(
            args.name,
            speed=args.speed,
            brightness=args.brightness,
            color1=args.color1,
            color2=args.color2,
            color_mode=color_mode,
            direction=protocol.DIRECTIONS[args.direction],
        )
    except Everest60Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    kb.disconnect()
    print(f"effect {args.name} ({'dual' if color_mode == protocol.COLOR_DUAL else 'single' if color_mode == protocol.COLOR_SINGLE else 'rainbow'})")
    return 0


def cmd_brightness(args: argparse.Namespace) -> int:
    try:
        kb = _connect(args.debug)
        kb.set_static(args.color, brightness=args.value)
    except Everest60Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    kb.disconnect()
    print(f"brightness {protocol.quantize_step(args.value)}%")
    return 0


def cmd_color(args: argparse.Namespace) -> int:
    from .models.keyboard import KEY_BY_NAME, KEYS

    colors = [(0, 0, 0)] * len(KEYS)
    if args.keys:
        names = [n.strip().upper() for n in args.keys.split(",") if n.strip()]
        for name in names:
            if name not in KEY_BY_NAME:
                print(f"error: unknown key '{name}'", file=sys.stderr)
                return 1
        for name in names:
            colors[KEY_BY_NAME[name].index] = args.color
        for key in KEYS:
            if colors[key.index] == (0, 0, 0):
                colors[key.index] = (25, 25, 25)  # dim base so others stay visible
    else:
        colors = [args.color] * len(KEYS)

    side = [args.side] * 44 if args.side else None
    try:
        kb = _connect(args.debug)
        kb.apply_custom_map(colors, side_colors=side, brightness=args.brightness)
    except Everest60Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    kb.disconnect()
    print(f"painted {rgb_to_hex(args.color)}" + (" with side ring" if side else ""))
    return 0


def cmd_side(args: argparse.Namespace) -> int:
    from .hardware.led_map import NUM_KEYS, NUM_SIDE_LEDS

    try:
        kb = _connect(args.debug)
        kb.apply_custom_map(
            [(0, 0, 0)] * NUM_KEYS,
            side_colors=[args.color] * NUM_SIDE_LEDS,
            brightness=args.brightness,
        )
    except Everest60Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    kb.disconnect()
    print(f"side ring {rgb_to_hex(args.color)}")
    return 0


def cmd_preset(args: argparse.Namespace) -> int:
    from .presets.store import PresetStore

    store = PresetStore()
    if args.action == "list":
        for preset in store.list():
            origin = "built-in" if preset.builtin else "user"
            print(f"{preset.name:24s} [{origin}] {preset.summary}")
        return 0

    if args.action == "load":
        if not args.name:
            print("error: preset name required", file=sys.stderr)
            return 1
        preset = store.load(args.name)
        if preset is None:
            print(f"error: preset '{args.name}' not found", file=sys.stderr)
            return 1
        state = preset.state
        try:
            kb = _connect(args.debug)
            if state.mode == "hardware":
                if state.effect == "off":
                    kb.set_off()
                else:
                    kb.set_effect(
                        state.effect,
                        speed=state.speed,
                        brightness=state.brightness,
                        color1=state.color1,
                        color2=state.color2,
                        color_mode=state.color_mode,
                        direction=protocol.DIRECTIONS.get(state.direction, 0),
                    )
            else:
                keys, side = list(state.key_colors), list(state.side_colors)
                if state.mode == "software":
                    from .hardware.service import _render_frame

                    keys, side = _render_frame(state)
                kb.apply_custom_map(
                    keys, side_colors=side, brightness=state.brightness
                )
                if state.mode == "software":
                    print("note: software effects animate in the GUI; CLI applies one frame")
        except Everest60Error as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        kb.disconnect()
        print(f"loaded preset {preset.name}")
        return 0

    if args.action == "save":
        if not args.name or not args.from_state:
            print("error: --from-state JSON and preset name required", file=sys.stderr)
            return 1
        import json
        from pathlib import Path

        data = json.loads(Path(args.from_state).read_text(encoding="utf-8"))
        data.setdefault("name", args.name)
        from .models.preset import Preset

        preset = Preset.from_dict(data)
        preset.name = args.name
        path = store.save(preset)
        print(f"saved {path}")
        return 0
    return 1


def cmd_gui(args: argparse.Namespace) -> int:
    from .main import main as gui_main

    return gui_main(debug=args.debug)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    debug = bool(getattr(args, "debug", False))
    setup_logging(debug=debug, log_file=False)

    if not getattr(args, "command", None):
        parser.print_help()
        return 1

    handlers = {
        "detect": cmd_detect,
        "status": cmd_status,
        "test": cmd_test,
        "static": cmd_static,
        "off": cmd_off,
        "effect": cmd_effect,
        "brightness": cmd_brightness,
        "color": cmd_color,
        "side": cmd_side,
        "preset": cmd_preset,
        "gui": cmd_gui,
    }
    try:
        return handlers[args.command](args)
    except Everest60Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
