"""HID transport failure handling (no real device needed)."""

from __future__ import annotations

import types

import pytest

from everest_rgb.hardware import everest60, hid_device, protocol
from everest_rgb.hardware.everest60 import Everest60, Everest60Error
from everest_rgb.hardware.hid_device import (
    DeviceDisconnected,
    HidTransport,
    ReportFailed,
    TransientError,
)


def _packet() -> bytes:
    return protocol.build_set_mode(protocol.EFFECT_STATIC)


def _open_transport(path: str, device: object) -> HidTransport:
    transport = HidTransport(path, inter_packet_delay=0, reset_settle=0)
    transport._device = device
    transport._closed = False
    return transport


class FakeDevice:
    """Minimal hidapi device double."""

    def __init__(self, *, write_result=65, read_error: BaseException | None = None):
        self.write_result = write_result
        self.read_error = read_error
        self.cmd = 0x16

    def send_feature_report(self, packet: bytes):
        self.cmd = packet[1]
        return self.write_result

    def get_feature_report(self, report_id: int, size: int):
        if self.read_error is not None:
            raise self.read_error
        buf = bytearray(size)
        buf[1] = self.cmd
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


class _OpenableDevice:
    """hidapi double that records writes and echoes the last command sent."""

    def __init__(self, *, echo: int | None = None):
        self.echo = echo
        self.writes: list[bytes] = []
        self._last_cmd = 0
        self.opened_path: bytes | None = None

    def open_path(self, path: bytes) -> None:
        self.opened_path = path

    def close(self) -> None:
        pass

    def send_feature_report(self, packet: bytes) -> int:
        self.writes.append(bytes(packet))
        self._last_cmd = packet[1]
        return len(packet)

    def get_feature_report(self, report_id: int, size: int) -> bytes:
        buf = bytearray(size)
        buf[1] = self._last_cmd if self.echo is None else self.echo
        return bytes(buf)


def _open_with_fake(
    monkeypatch, tmp_path, device, *, delay: float = 0.0, settle: float = 0.0
) -> HidTransport:
    node = tmp_path / "hidraw0"
    node.write_bytes(b"")
    monkeypatch.setattr(hid_device, "hid", types.SimpleNamespace(device=lambda: device))
    transport = HidTransport(str(node), inter_packet_delay=delay, reset_settle=settle)
    transport.open()
    return transport


def test_connecting_alone_writes_nothing(monkeypatch, tmp_path):
    """``0x03`` blanks the LEDs, so opening the device must not send it."""
    device = _OpenableDevice()
    transport = _open_with_fake(monkeypatch, tmp_path, device)
    try:
        assert transport.is_open
        assert device.writes == []
    finally:
        transport.close()


def test_first_command_leads_with_the_reset_handshake(monkeypatch, tmp_path):
    device = _OpenableDevice()
    transport = _open_with_fake(monkeypatch, tmp_path, device)
    try:
        transport.exchange(_packet(), expected_cmd=0x16, retries=1, retry_delay=0)
        assert [w[1] for w in device.writes] == [protocol.CMD_RESET, 0x16]
        protocol.validate_packet(device.writes[0], protocol.CMD_RESET)
    finally:
        transport.close()


def test_handshake_is_sent_once_per_connection(monkeypatch, tmp_path):
    device = _OpenableDevice()
    transport = _open_with_fake(monkeypatch, tmp_path, device)
    try:
        for _ in range(3):
            transport.exchange(_packet(), expected_cmd=0x16, retries=1, retry_delay=0)
        assert [w[1] for w in device.writes] == [protocol.CMD_RESET, 0x16, 0x16, 0x16]

        transport.close()
        transport.open()
        transport.exchange(_packet(), expected_cmd=0x16, retries=1, retry_delay=0)
        assert device.writes[-2][1] == protocol.CMD_RESET
    finally:
        transport.close()


def test_failed_reset_handshake_is_reported(monkeypatch, tmp_path):
    device = _OpenableDevice(echo=0x7F)  # device never acknowledges 0x03
    transport = _open_with_fake(monkeypatch, tmp_path, device)

    with pytest.raises(ReportFailed, match="0x03"):
        transport.exchange(_packet(), expected_cmd=0x16, retries=1, retry_delay=0)

    assert device.writes[0][1] == protocol.CMD_RESET
    assert transport._handshake_done is False
    transport.close()


def test_exchange_paces_consecutive_packets(monkeypatch, tmp_path):
    slept: list[float] = []
    device = _OpenableDevice()
    transport = _open_with_fake(monkeypatch, tmp_path, device, delay=0.05)
    try:
        monkeypatch.setattr(hid_device.time, "sleep", slept.append)
        transport.exchange(_packet(), expected_cmd=0x16, retries=1, retry_delay=0)
        transport.exchange(_packet(), expected_cmd=0x16, retries=1, retry_delay=0)
        # handshake, first packet, second packet
        assert slept.count(0.05) == 3
    finally:
        transport.close()


def test_handshake_waits_for_the_firmware_to_settle(monkeypatch, tmp_path):
    slept: list[float] = []
    device = _OpenableDevice()
    transport = _open_with_fake(monkeypatch, tmp_path, device, settle=0.15)
    try:
        monkeypatch.setattr(hid_device.time, "sleep", slept.append)
        transport.exchange(_packet(), expected_cmd=0x16, retries=1, retry_delay=0)
        assert slept == [0.15]
    finally:
        transport.close()


def test_switching_effect_waits_for_the_firmware_but_repeating_it_does_not(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(everest60.time, "sleep", slept.append)

    class FakeTransport:
        is_open = True
        tx_count = 0
        rx_count = 0

        def exchange(self, *args, **kwargs):
            self.tx_count += 1
            self.rx_count += 1

        def close(self):
            self.is_open = False

    controller = Everest60()
    controller._transport = FakeTransport()
    controller.status.connected = True

    controller.set_effect(protocol.EFFECT_WAVE)
    assert slept == [Everest60.EFFECT_SWITCH_SETTLE]

    controller.set_effect(protocol.EFFECT_WAVE, color1=(1, 2, 3))
    assert slept == [Everest60.EFFECT_SWITCH_SETTLE]

    controller.set_effect(protocol.EFFECT_STATIC)
    assert slept == [Everest60.EFFECT_SWITCH_SETTLE] * 2

    controller.disconnect()
    assert controller._active_effect is None


def test_reopening_a_connection_forgets_the_active_effect(monkeypatch):
    """A new handle means the firmware may have restarted - never skip the wait."""
    class FakeTransport:
        is_open = False
        tx_count = 0
        rx_count = 0

        def __init__(self, *args, **kwargs):
            pass

        def open(self):
            self.is_open = True

        def close(self):
            self.is_open = False

        def exchange(self, *args, **kwargs):
            self.tx_count += 1
            self.rx_count += 1

    info = types.SimpleNamespace(
        path=b"/dev/hidraw0",
        path_str="/dev/hidraw0",
        device_name="MOUNTAIN EVEREST 60",
        vendor_id=0x3282,
        product_id=0x0005,
        interface=0,
    )
    monkeypatch.setattr(everest60.detection, "find_lighting_device", lambda: info)
    monkeypatch.setattr(everest60, "HidTransport", FakeTransport)

    controller = Everest60()
    controller._active_effect = protocol.EFFECT_WAVE
    controller.connect()
    assert controller._active_effect is None
