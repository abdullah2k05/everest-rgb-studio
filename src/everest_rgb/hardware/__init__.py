"""Hardware access layer: detection, protocol, transport, controller."""

from .detection import DeviceInfo, DeviceNotFound, find_lighting_device, enumerate_devices
from .everest60 import Everest60, Everest60Error, DeviceStatus
from .led_map import (
    LED_INDEX_BY_POSITION,
    NUM_KEYS,
    NUM_SIDE_LEDS,
    SIDE_LED_INDICES,
)
from .hid_device import (
    DeviceBusy,
    DeviceDisconnected,
    PermissionDenied,
    TransportError,
)

__all__ = [
    "DeviceInfo",
    "DeviceNotFound",
    "find_lighting_device",
    "enumerate_devices",
    "Everest60",
    "Everest60Error",
    "DeviceStatus",
    "LED_INDEX_BY_POSITION",
    "NUM_KEYS",
    "NUM_SIDE_LEDS",
    "SIDE_LED_INDICES",
    "DeviceBusy",
    "DeviceDisconnected",
    "PermissionDenied",
    "TransportError",
]
