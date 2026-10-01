"""Device selection tests using synthetic enumeration results."""

from everest_rgb.hardware.detection import (
    KEYBOARD_INTERFACE,
    DeviceInfo,
    select_lighting_device,
)


def _device(path: str, *, interface: int, usage_page: int, usage: int) -> DeviceInfo:
    return DeviceInfo(
        path=path.encode(),
        vendor_id=0x3282,
        product_id=0x0005,
        interface=interface,
        usage_page=usage_page,
        usage=usage,
        product="MOUNTAIN EVEREST 360",
    )


def test_prefers_keyboard_collection_on_interface_zero():
    devices = [
        _device("/dev/hidraw0", interface=0, usage_page=0x01, usage=0x06),
        _device("/dev/hidraw1", interface=1, usage_page=0x01, usage=0x02),
        _device("/dev/hidraw1", interface=1, usage_page=0x0C, usage=0x01),
    ]
    selected = select_lighting_device(devices)
    assert selected is not None
    assert selected.path_str == "/dev/hidraw0"


def test_never_selects_mouse_usage():
    devices = [
        _device("/dev/hidraw1", interface=1, usage_page=0x01, usage=0x02),
        _device("/dev/hidraw1", interface=1, usage_page=0x0C, usage=0x01),
    ]
    assert select_lighting_device(devices) is None


def test_falls_back_to_keyboard_usage_on_other_interface():
    devices = [
        _device("/dev/hidraw3", interface=1, usage_page=0x01, usage=0x06),
        _device("/dev/hidraw4", interface=1, usage_page=0x01, usage=0x02),
    ]
    selected = select_lighting_device(devices)
    assert selected is not None
    assert selected.usage == 0x06


def test_empty_enumeration():
    assert select_lighting_device([]) is None


def test_real_layout_matches_hardware_shape():
    # The device exposes the keyboard collection on interface 0.
    dev = _device("/dev/hidraw0", interface=KEYBOARD_INTERFACE, usage_page=1, usage=6)
    assert dev.is_keyboard_collection
    assert not dev.is_mouse_collection
