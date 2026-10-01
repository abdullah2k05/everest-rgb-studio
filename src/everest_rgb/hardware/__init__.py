"""Hardware access layer: detection, protocol, transport, controller."""

from .detection import DeviceInfo, DeviceNotFound, enumerate_devices, find_lighting_device
from .everest60 import DeviceStatus, Everest60, Everest60Error
from .hid_device import (
    DeviceBusy,
    DeviceDisconnected,
    PermissionDenied,
    TransportError,
)
from .led_map import (
    LED_INDEX_BY_POSITION,
    NUM_KEYS,
    NUM_SIDE_LEDS,
    SIDE_LED_INDICES,
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
