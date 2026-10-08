"""High level Everest 60 controller.

This is the only class the CLI / GUI / effect engine talk to. It owns the
device connection, builds packets through the protocol layer, and turns low
level transport failures into clear, catchable errors.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from . import detection, protocol
from .hid_device import (
    DeviceBusy,
    DeviceDisconnected,
    HidTransport,
    PermissionDenied,
    TransientError,
    TransportError,
)

log = logging.getLogger(__name__)

Color = tuple[int, int, int]

DEFAULT_COLOR: Color = (255, 255, 255)


@dataclass
class DeviceStatus:
    connected: bool = False
    name: str = "Everest 60"
    vendor_id: int = detection.VID_MOUNTAIN
    product_id: int = detection.PID_EVEREST60_ANSI
    interface: int = -1
    path: str = ""
    last_error: str = ""
    tx_count: int = 0
    rx_count: int = 0


class Everest60Error(RuntimeError):
    """High level controller error with a user friendly message."""


class Everest60:
    """Thread-confined controller: use one instance from one worker thread."""

    #: Wait after 0x16 activates a *different* effect. The firmware restarts
    #: that effect's renderer and drops the 0x17 that follows - it still echoes
    #: the command, so the write looks successful while the requested colour is
    #: silently replaced by the effect's own palette (measured: 20 ms is too
    #: soon, 800 ms applies). Re-sending the effect that is already running
    #: needs no delay, so live brightness/speed changes stay fast.
    EFFECT_SWITCH_SETTLE = 0.8

    def __init__(self, *, debug: bool = False, retries: int = 3):
        self._debug = debug
        self._retries = retries
        self._transport: HidTransport | None = None
        self._info: detection.DeviceInfo | None = None
        self._lock = threading.RLock()
        self._active_effect: int | None = None
        self.status = DeviceStatus()

    # -- lifecycle ---------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return (
            self.status.connected
            and self._transport is not None
            and self._transport.is_open
        )

    @property
    def path(self) -> str:
        return self._info.path_str if self._info else ""

    def detect(self) -> detection.DeviceInfo | None:
        """Find the lighting interface without opening it."""
        return detection.find_lighting_device()

    def connect(self, info: detection.DeviceInfo | None = None) -> DeviceStatus:
        """Open the lighting HID interface (reconnecting if needed)."""
        with self._lock:
            if self.is_connected:
                return self.status
            try:
                info = info or detection.find_lighting_device()
                if info is None:
                    raise Everest60Error(
                        "Everest 60 not found. Connect the keyboard and it will be "
                        "detected automatically."
                    )
                transport = HidTransport(info.path, debug=self._debug)
                transport.open()
                # a fresh handle means unknown firmware state: the lighting task
                # may have restarted, so the effect remembered from the previous
                # connection cannot be assumed to still be running
                self._active_effect = None
            except PermissionDenied as exc:
                self._set_disconnected(str(exc))
                raise Everest60Error(str(exc)) from exc
            except (DeviceDisconnected, DeviceBusy) as exc:
                self._set_disconnected(str(exc))
                raise Everest60Error(str(exc)) from exc
            except TransportError as exc:
                self._set_disconnected(str(exc))
                raise Everest60Error(f"failed to open keyboard: {exc}") from exc

            self._transport = transport
            self._info = info
            self.status = DeviceStatus(
                connected=True,
                name=info.device_name,
                vendor_id=info.vendor_id,
                product_id=info.product_id,
                interface=info.interface,
                path=info.path_str,
            )
            log.info(
                "connected to %s (%s, if %d)",
                info.device_name,
                info.path_str,
                info.interface,
            )
            return self.status

    def disconnect(self) -> None:
        with self._lock:
            transport, self._transport = self._transport, None
            self._info = None
            self._active_effect = None
            if transport is not None:
                transport.close()
            if self.status.connected:
                log.info("disconnected")
            self.status.connected = False

    def _set_disconnected(self, message: str) -> None:
        self.status.connected = False
        self.status.last_error = message

    def _require_transport(self) -> HidTransport:
        transport = self._transport
        if transport is None or not transport.is_open:
            raise DeviceDisconnected("keyboard is not connected")
        return transport

    # -- low level ---------------------------------------------------------

    def _exchange(self, packet: bytes, *, verify_echo: bool = True) -> None:
        with self._lock:
            transport = self._require_transport()
            try:
                transport.exchange(
                    packet,
                    expected_cmd=packet[1],
                    retries=self._retries,
                    verify_echo=verify_echo,
                )
            except DeviceDisconnected as exc:
                # Release the stale fd so the service's reconnect loop can
                # re-enumerate and open the new hidraw node.
                self.disconnect()
                self._set_disconnected(str(exc))
                raise Everest60Error(
                    "Everest 60 disconnected. Reconnect the keyboard and it will "
                    "be reconnected automatically."
                ) from exc
            except PermissionDenied as exc:
                self._set_disconnected(str(exc))
                raise Everest60Error(str(exc)) from exc
            except TransientError as exc:
                # A temporary I/O hiccup: keep the connection, the next frame
                # (or retry) will rewrite the whole map.
                log.debug("transient HID error: %s", exc)
                raise Everest60Error(f"keyboard I/O temporarily unavailable: {exc}") from exc
            except TransportError as exc:
                self._set_disconnected(str(exc))
                raise Everest60Error(str(exc)) from exc
            self.status.tx_count = transport.tx_count
            self.status.rx_count = transport.rx_count

    def _send(self, packet: bytes) -> None:
        self._exchange(packet, verify_echo=True)

    def _set_mode(self, effect: int) -> None:
        """0x16, waiting for the firmware to finish switching effects."""
        switching = effect != self._active_effect
        self._send(protocol.build_set_mode(effect))
        if switching:
            self._active_effect = effect
            if self.EFFECT_SWITCH_SETTLE > 0:
                time.sleep(self.EFFECT_SWITCH_SETTLE)

    # -- firmware effect control ------------------------------------------

    def set_off(self, *, brightness: int = 100) -> None:
        """Turn the lighting off."""
        self.set_effect(protocol.EFFECT_OFF, brightness=brightness, color1=(0, 0, 0))

    def set_static(self, color: Color, *, brightness: int = 100) -> None:
        """Solid single color across the board."""
        r, g, b = _clamp_color(color)
        self.set_effect(
            protocol.EFFECT_STATIC,
            brightness=brightness,
            color_mode=protocol.COLOR_SINGLE,
            color1=(r, g, b),
        )

    def set_effect(
        self,
        effect: int | str,
        *,
        speed: int = 50,
        brightness: int = 100,
        color1: Color = DEFAULT_COLOR,
        color2: Color = (0, 0, 0),
        color_mode: int | None = None,
        direction: int = 0,
        commit: bool = True,
    ) -> None:
        """Activate a firmware effect with its parameters.

        Sequence: 0x16 (set mode), 0x17 (mode details), 0x1A (commit).
        """
        effect = _resolve_effect(effect)
        if color_mode is None:
            color_mode = protocol.COLOR_SINGLE if effect == protocol.EFFECT_STATIC else protocol.COLOR_DUAL

        with self._lock:
            self._set_mode(effect)
            self._send(
                protocol.build_mode_details(
                    effect,
                    speed=speed,
                    brightness=brightness,
                    color_mode=color_mode,
                    direction=direction,
                    color1=_clamp_color(color1),
                    color2=_clamp_color(color2),
                )
            )
            if commit:
                self._send(protocol.build_commit(effect))

    def set_brightness(self, value: int, state_applier=None) -> None:
        """Set brightness 0-100 (quantized to the hardware's 25 step scale).

        Brightness lives in different packets depending on the active mode, so
        the caller supplies a callback that re-applies the current state.
        """
        if state_applier is None:
            raise Everest60Error("brightness change requires a state re-apply")
        state_applier(max(0, min(100, int(value))))

    # -- per-key RGB -------------------------------------------------------

    def apply_custom_map(
        self,
        key_colors: list[Color],
        *,
        side_colors: list[Color] | None = None,
        brightness: int = 100,
    ) -> None:
        """Paint per-key RGB (and optionally the side ring).

        ``key_colors`` is 64 entries in logical key order; ``side_colors`` is
        44 entries in side ring order.
        """
        from .led_map import LED_INDEX_BY_POSITION, NUM_KEYS, NUM_SIDE_LEDS, SIDE_LED_INDICES

        colors = list(key_colors)[:NUM_KEYS]
        colors.extend([(0, 0, 0)] * (NUM_KEYS - len(colors)))

        stream: list[tuple[int, int, int, int]] = []
        for i, (r, g, b) in enumerate(colors):
            stream.append((LED_INDEX_BY_POSITION[i], *_clamp_color((r, g, b))))

        if side_colors is not None:
            side = list(side_colors)[:NUM_SIDE_LEDS]
            side.extend([(0, 0, 0)] * (NUM_SIDE_LEDS - len(side)))
            for hw, (r, g, b) in zip(SIDE_LED_INDICES, side):
                stream.append((hw, *_clamp_color((r, g, b))))

        with self._lock:
            # Custom mode must not send 0x17: it would flash a default color
            # over the map before it lands.
            self._set_mode(protocol.EFFECT_CUSTOM)
            self._send(protocol.build_commit(protocol.EFFECT_CUSTOM))
            self._send(protocol.build_custom_begin(brightness))
            for packet in protocol.build_custom_map_packets(stream):
                self._send(packet)
            self._send(protocol.build_custom_end())
            self._send(protocol.build_commit(protocol.EFFECT_CUSTOM))


def _clamp_color(color: Color | list[int] | tuple[int, ...]) -> Color:
    r, g, b = color
    return (
        max(0, min(255, int(r))),
        max(0, min(255, int(g))),
        max(0, min(255, int(b))),
    )


def _resolve_effect(effect: int | str) -> int:
    if isinstance(effect, int):
        if effect not in protocol.EFFECT_NAMES:
            raise Everest60Error(f"unknown effect code {effect:#04x}")
        return effect
    code = protocol.EFFECTS_BY_NAME.get(effect.strip().lower())
    if code is None:
        known = ", ".join(sorted(protocol.EFFECTS_BY_NAME))
        raise Everest60Error(f"unknown effect '{effect}' (known: {known})")
    return code
