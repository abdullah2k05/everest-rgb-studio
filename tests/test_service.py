"""Hardware service tests with a fake controller (no device needed)."""

from __future__ import annotations

import time

import pytest

from everest_rgb.hardware.everest60 import Everest60Error
from everest_rgb.hardware.service import HardwareService
from everest_rgb.models.lighting import LightingState
from everest_rgb.utils.config import Settings


class FakeController:
    """Records the high-level calls the service makes."""

    def __init__(self, *, connected: bool = True):
        from everest_rgb.hardware.everest60 import DeviceStatus

        self.status = DeviceStatus(connected=connected, path="/dev/fake")
        self.calls: list[tuple] = []
        self._connected = connected

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self):
        self._connected = True
        self.status.connected = True
        self.calls.append(("connect",))
        return self.status

    def disconnect(self):
        self._connected = False
        self.status.connected = False
        self.calls.append(("disconnect",))

    def set_off(self, *, brightness=100):
        self.calls.append(("off", brightness))

    def set_effect(self, name, **kwargs):
        self.calls.append(("effect", name, kwargs))

    def apply_custom_map(self, keys, side_colors=None, brightness=100):
        self.calls.append(("map", tuple(keys), tuple(side_colors or ()), brightness))


def make_service(controller: FakeController | None = None, **settings_kwargs) -> HardwareService:
    settings = Settings(reconnect_interval_s=0.05, **settings_kwargs)
    settings.remember_last_state = False
    return HardwareService(settings, controller=controller or FakeController())


def test_hardware_effect_routes_to_set_effect():
    controller = FakeController()
    service = make_service(controller)
    state = LightingState()
    state.mode = "hardware"
    state.effect = "wave"
    state.color1 = (1, 2, 3)
    service.run_sync(lambda: service._apply(state))
    kind, name, kwargs = controller.calls[-1]
    assert kind == "effect"
    assert name == "wave"
    assert kwargs["color1"] == (1, 2, 3)


def test_off_routes_to_set_off():
    controller = FakeController()
    service = make_service(controller)
    state = LightingState()
    state.mode = "hardware"
    state.effect = "off"
    service.run_sync(lambda: service._apply(state))
    assert controller.calls[-1][0] == "off"


def test_custom_mode_routes_to_map():
    controller = FakeController()
    service = make_service(controller)
    state = LightingState()
    state.mode = "custom"
    state.fill_keys((9, 9, 9))
    service.run_sync(lambda: service._apply(state))
    kind, keys, side, brightness = controller.calls[-1]
    assert kind == "map"
    assert keys[0] == (9, 9, 9)
    assert brightness == 100


def test_software_mode_renders_frame_before_map():
    controller = FakeController()
    service = make_service(controller)
    state = LightingState()
    state.mode = "software"
    state.effect = "gradient"
    state.color1 = (0, 0, 0)
    state.color2 = (255, 255, 255)
    service.run_sync(lambda: service._apply(state))
    kind, keys, _side, _bri = controller.calls[-1]
    assert kind == "map"
    assert keys[0] != keys[-1], "gradient should differ across the board"


def test_worker_applies_state_and_ignores_hardware_jobs_while_unplugged():
    controller = FakeController(connected=False)
    service = make_service(controller, auto_reconnect=False)
    service.start()
    try:
        future = service.submit(lambda: "ran")
        with pytest.raises(Exception):
            future.result(timeout=2)
        # no connect happened (auto_reconnect off)
        assert ("connect",) not in controller.calls
    finally:
        service.stop()


def test_auto_reconnect_restores_state():
    controller = FakeController(connected=False)
    service = make_service(controller, auto_reconnect=True)
    state = LightingState()
    state.mode = "hardware"
    state.effect = "static"
    state.color1 = (10, 20, 30)
    service.desired_state = state
    service.settings.remember_last_state = True
    service.settings.restore_on_connect = True
    service.start()
    try:
        deadline = time.time() + 3
        while time.time() < deadline and not controller.is_connected:
            time.sleep(0.05)
        assert controller.is_connected
        deadline = time.time() + 3
        while time.time() < deadline and not controller.calls:
            time.sleep(0.05)
        assert any(call[0] == "effect" for call in controller.calls)
    finally:
        service.stop()


def test_frame_coalescing_keeps_only_latest():
    controller = FakeController()
    service = make_service(controller)
    service.start()
    try:
        for i in range(30):
            service.push_frame([(i, 0, 0)] * 64, [(0, 0, 0)] * 44, 100)
        # give the worker time to drain
        deadline = time.time() + 3
        while time.time() < deadline:
            snap = service.snapshot()
            if not snap.busy:
                break
            time.sleep(0.05)
        maps = [c for c in controller.calls if c[0] == "map"]
        assert 1 <= len(maps) < 30, f"frames should coalesce, got {len(maps)}"
        # the last frame wins
        assert maps[-1][1][0] == (29, 0, 0)
    finally:
        service.stop()


def test_snapshot_status_text():
    controller = FakeController(connected=True)
    service = make_service(controller)
    snap = service.snapshot()
    assert snap.connected
    assert snap.status_text.startswith("●")
    controller.status.connected = False
    assert service.snapshot().status_text.startswith("○")
