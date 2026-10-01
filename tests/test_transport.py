"""HID transport failure handling (no real device needed)."""

from __future__ import annotations

import pytest

from everest_rgb.hardware import protocol
from everest_rgb.hardware.everest60 import Everest60, Everest60Error
from everest_rgb.hardware.hid_device import (
    DeviceDisconnected,
    HidTransport,
    TransientError,
)


def _packet() -> bytes:
    return protocol.build_set_mode(protocol.EFFECT_STATIC)


def _open_transport(path: str, device: object) -> HidTransport:
    transport = HidTransport(path)
    transport._device = device
    transport._closed = False
    return transport


class FakeDevice:
    """Minimal hidapi device double."""

    def __init__(self, *, write_result=65, read_error: BaseException | None = None):
        self.write_result = write_result
        self.read_error = read_error

    def send_feature_report(self, packet: bytes):
        return self.write_result

    def get_feature_report(self, report_id: int, size: int):
        if self.read_error is not None:
            raise self.read_error
        buf = bytearray(size)
        buf[1] = getattr(self, "cmd", 0x16)
        return bytes(buf)


def test_missing_node_is_disconnected_immediately():
    transport = _open_transport("/nonexistent/hidraw99", FakeDevice())
    with pytest.raises(DeviceDisconnected):
        transport.send_feature_report(_packet())


def test_bare_minus_one_write_is_a_transport_error():
    transport = _open_transport(__file__, FakeDevice(write_result=-1))
    with pytest.raises(TransientError):
        transport.send_feature_report(_packet())


def test_transient_read_errors_escalate_after_repeated_exchanges():
    device = FakeDevice(read_error=IOError("read error"))
    transport = _open_transport(__file__, device)

    with pytest.raises(TransientError):
        transport.exchange(_packet(), expected_cmd=0x16, retries=2, retry_delay=0)
    with pytest.raises(TransientError):
        transport.exchange(_packet(), expected_cmd=0x16, retries=2, retry_delay=0)
    with pytest.raises(DeviceDisconnected):
        transport.exchange(_packet(), expected_cmd=0x16, retries=2, retry_delay=0)


def test_success_resets_the_transient_counter():
    device = FakeDevice(read_error=IOError("read error"))
    transport = _open_transport(__file__, device)
    with pytest.raises(TransientError):
        transport.exchange(_packet(), expected_cmd=0x16, retries=1, retry_delay=0)
    with pytest.raises(TransientError):
        transport.exchange(_packet(), expected_cmd=0x16, retries=1, retry_delay=0)

    device.read_error = None  # device recovers (echo matches default cmd)
    device.cmd = 0x16
    assert transport.exchange(_packet(), expected_cmd=0x16, retries=1, retry_delay=0) is not None

    device.read_error = IOError("read error")
    with pytest.raises(TransientError):
        transport.exchange(_packet(), expected_cmd=0x16, retries=1, retry_delay=0)


def test_controller_marks_disconnected_on_transport_failure():
    class DeadTransport:
        is_open = True
        tx_count = 0
        rx_count = 0

        def exchange(self, *args, **kwargs):
            raise DeviceDisconnected("/dev/hidraw0: device removed")

        def close(self):
            self.is_open = False

    controller = Everest60()
    transport = DeadTransport()
    controller._transport = transport
    controller.status.connected = True

    with pytest.raises(Everest60Error, match="disconnected"):
        controller._exchange(_packet())

    assert controller.is_connected is False
    assert transport.is_open is False
    assert controller.status.connected is False
    assert controller.status.last_error
