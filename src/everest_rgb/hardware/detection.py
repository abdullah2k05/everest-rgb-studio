"""Device discovery for the MOUNTAIN Everest 60.

The keyboard exposes several HID collections. Only the keyboard collection
(usage page 0x01 / usage 0x06, on interface 0) speaks the lighting protocol;
the mouse/system-control collection (usage 0x02) must never be selected.

hidraw numbers are not stable across replugs, so the path is always resolved
from the current enumeration instead of being hard coded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

try:
    import hid
except Exception:  # pragma: no cover - hidapi missing at runtime
    hid = None  # type: ignore[assignment]

VID_MOUNTAIN = 0x3282
PID_EVEREST60_ANSI = 0x0005
PID_EVEREST60_ISO = 0x0006
PRODUCT_IDS = (PID_EVEREST60_ANSI, PID_EVEREST60_ISO)

USAGE_PAGE_GENERIC_DESKTOP = 0x01
USAGE_KEYBOARD = 0x06
USAGE_MOUSE = 0x02

KEYBOARD_INTERFACE = 0


class DeviceNotFound(RuntimeError):
    """No matching Everest 60 lighting interface was found."""


@dataclass(frozen=True)
class DeviceInfo:
    """One HID collection exposed by the keyboard."""

    path: bytes
    vendor_id: int
    product_id: int
    interface: int
    usage_page: int
    usage: int
    product: str = ""
    manufacturer: str = ""
    serial: str = ""
    release: int = 0

    @property
    def path_str(self) -> str:
        return self.path.decode(errors="replace") if isinstance(self.path, bytes) else str(self.path)

    @property
    def is_keyboard_collection(self) -> bool:
        return self.usage_page == USAGE_PAGE_GENERIC_DESKTOP and self.usage == USAGE_KEYBOARD

    @property
    def is_mouse_collection(self) -> bool:
        return self.usage_page == USAGE_PAGE_GENERIC_DESKTOP and self.usage == USAGE_MOUSE

    @property
    def device_name(self) -> str:
        return self.product or "MOUNTAIN EVEREST 60"


def _as_int(value) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value, 16) if value.startswith(("0x", "0X")) else int(value, 16) if any(c in value for c in "abcdefABCDEF") else int(value)
    if isinstance(value, bytes):
        return int.from_bytes(value, "little")
    return int(value)


def enumerate_devices(vid: int = VID_MOUNTAIN, pids: tuple[int, ...] = PRODUCT_IDS) -> list[DeviceInfo]:
    """Enumerate all HID collections for the given vendor/product ids."""
    if hid is None:
        raise RuntimeError("python-hidapi is not installed (pacman: python-hidapi)")

    found: list[DeviceInfo] = []
    for pid in pids:
        try:
            entries = hid.enumerate(vid, pid)
        except Exception as exc:  # pragma: no cover - depends on host
            log.warning("hid.enumerate(%#06x, %#06x) failed: %s", vid, pid, exc)
            continue
        for entry in entries:
            try:
                found.append(
                    DeviceInfo(
                        path=entry.get("path", b""),
                        vendor_id=_as_int(entry.get("vendor_id", vid)),
                        product_id=_as_int(entry.get("product_id", pid)),
                        interface=_as_int(entry.get("interface_number", -1)),
                        usage_page=_as_int(entry.get("usage_page", 0)),
                        usage=_as_int(entry.get("usage", 0)),
                        product=entry.get("product_string") or "",
                        manufacturer=entry.get("manufacturer_string") or "",
                        serial=entry.get("serial_number") or "",
                        release=_as_int(entry.get("release_number", 0)),
                    )
                )
            except Exception as exc:  # pragma: no cover - malformed entry
                log.debug("skipping malformed HID entry: %s", exc)
    return found


def select_lighting_device(devices: list[DeviceInfo] | None = None) -> DeviceInfo | None:
    """Pick the HID collection that speaks the lighting protocol.

    Preference order:
      1. keyboard usage (0x01/0x06) on interface 0
      2. any keyboard usage collection
      3. interface 0 as a last resort (verified working on this hardware)
    """
    if devices is None:
        devices = enumerate_devices()

    keyboards = [d for d in devices if d.is_keyboard_collection]
    on_if0 = [d for d in keyboards if d.interface == KEYBOARD_INTERFACE]
    if on_if0:
        return on_if0[0]
    if keyboards:
        return keyboards[0]

    if0 = [d for d in devices if d.interface == KEYBOARD_INTERFACE]
    if if0:
        log.warning("no keyboard usage collection found; falling back to interface 0")
        return if0[0]
    return None


def find_lighting_device() -> DeviceInfo | None:
    """Enumerate and select the lighting interface, or None when unplugged."""
    try:
        devices = enumerate_devices()
    except RuntimeError:
        raise
    except Exception as exc:  # pragma: no cover
        log.error("device enumeration failed: %s", exc)
        return None
    selected = select_lighting_device(devices)
    if selected is None:
        log.debug("no Everest 60 lighting interface present")
    else:
        log.debug(
            "selected %s if=%d usage=%#04x/%#04x path=%s",
            selected.device_name,
            selected.interface,
            selected.usage_page,
            selected.usage,
            selected.path_str,
        )
    return selected
