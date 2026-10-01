"""Lighting state and preset store tests."""

import json

import pytest

from everest_rgb.models.keyboard import KEY_BY_NAME, NUM_KEYS  # noqa: F401
from everest_rgb.models.lighting import LightingState, hex_to_rgb, rgb_to_hex
from everest_rgb.models.preset import Preset
from everest_rgb.presets.store import PresetStore


def test_hex_roundtrip():
    assert rgb_to_hex((0, 168, 255)) == "#00A8FF"
    assert hex_to_rgb("#00A8FF") == (0, 168, 255)
    assert hex_to_rgb("00a8ff") == (0, 168, 255)
    assert hex_to_rgb("#fff") == (255, 255, 255)
    with pytest.raises(ValueError):
        hex_to_rgb("#12")
    with pytest.raises(ValueError):
        hex_to_rgb("zzzzzz")


def test_state_roundtrip():
    state = LightingState()
    state.mode = "custom"
    state.brightness = 75
    state.set_key_colors([1, 2, 3], (10, 20, 30))
    state.fill_side((1, 2, 3))

    data = state.to_dict()
    restored = LightingState.from_dict(data)
    assert restored.brightness == 75
    assert restored.mode == "custom"
    assert restored.key_colors[1] == (10, 20, 30)
    assert restored.side_colors[0] == (1, 2, 3)


def test_state_named_keys():
    state = LightingState.from_dict({"keys": {"W": "#112233", "9999": "#000000"}})
    w = KEY_BY_NAME["W"].index
    assert state.key_colors[w] == (0x11, 0x22, 0x33)


def test_state_clamps_out_of_range_colors():
    state = LightingState()
    state.set_key_color(0, (999, -5, 300))
    assert state.key_colors[0] == (255, 0, 255)


def test_legacy_custom_mode_preset():
    payload = {"name": "Old", "mode": "custom", "keys": {"ESC": "#FF0000"}}
    state = LightingState.from_dict(payload)
    assert state.mode == "custom"
    assert state.key_colors[KEY_BY_NAME["ESC"].index] == (255, 0, 0)


def test_builtin_presets_are_valid():
    store = PresetStore(user_dir="/nonexistent")
    presets = store.list()
    names = [p.name for p in presets]
    assert "Ocean" in names
    assert "Cyberpunk" in names
    assert "Matrix" in names
    assert all(p.builtin for p in presets)
    for preset in presets:
        assert preset.state.brightness in range(0, 101)
        if preset.state.mode == "custom":
            assert len(preset.state.key_colors) == 64


def test_user_preset_lifecycle(tmp_path):
    store = PresetStore(user_dir=tmp_path)

    state = LightingState()
    state.mode = "custom"
    state.set_key_color(0, (255, 0, 0))
    preset = Preset.from_state("My Preset", state, "test")

    path = store.save(preset)
    assert path.exists()
    assert store.load("my preset") is not None
    assert "My Preset" in store.names()

    copy = store.duplicate(preset, "Copy")
    assert copy.name in store.names()
    assert store.load("Copy") is not None

    assert store.delete("Copy") is True
    assert store.load("Copy") is None

    with pytest.raises(ValueError):
        store.delete("Ocean")  # built-ins are protected

    exported = store.export(preset, tmp_path / "export.json")
    assert exported.exists()
    data = json.loads(exported.read_text())
    assert data["name"] == "My Preset"
    assert data["schema"] == 1

    other = PresetStore(user_dir=tmp_path / "other")
    imported = other.import_file(exported)
    assert imported.name == "My Preset"
    # re-importing into the same store must not overwrite silently
    again = store.import_file(exported)
    assert again.name == "My Preset 2"


def test_preset_json_contains_required_fields(tmp_path):
    state = LightingState()
    state.mode = "custom"
    preset = Preset.from_state("Check", state)
    path = preset.save(tmp_path / "check.json")
    data = json.loads(path.read_text())
    for key in ("schema", "name", "brightness", "speed", "mode", "effect", "keys", "side"):
        assert key in data


def test_newer_schema_rejected():
    with pytest.raises(ValueError):
        Preset.from_dict({"name": "future", "schema": 999})
