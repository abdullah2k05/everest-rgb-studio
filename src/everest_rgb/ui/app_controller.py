"""Application controller: owns state, hardware service, effect engine, undo.

All UI panels talk to this object; it is the only place that decides when the
keyboard gets written to. Hardware work happens on the service thread.
"""

from __future__ import annotations

import logging
from collections import deque

from PySide6.QtCore import QObject, Signal

from ..effects.engine import EffectEngine
from ..hardware.led_map import NUM_KEYS
from ..hardware.service import HardwareService, ServiceSnapshot
from ..models.lighting import LightingState, clamp_color
from ..models.preset import Preset
from ..presets.store import PresetStore
from ..utils.config import Settings, StateStore

log = logging.getLogger(__name__)

UNDO_LIMIT = 100

# Firmware effect -> software preview used purely for the on-screen keyboard.
PREVIEW_EFFECT = {
    "static": "static",
    "wave": "wave",
    "tornado": "wave",
    "breathing": "breathing",
    "reactive": "reactive",
    "matrix": "matrix",
    "yeti": "rainbow",
    "off": "static",
}


class AppController(QObject):
    stateChanged = Signal()
    presetsChanged = Signal()
    message = Signal(str, str)      # text, level (info|warn|error)

    def __init__(self, settings: Settings | None = None, *, debug: bool = False, parent=None):
        super().__init__(parent)
        self.settings = settings or Settings.load()
        self.debug = debug
        self.state_store = StateStore()
        self.store = PresetStore()

        self.state = LightingState()
        if self.settings.remember_last_state:
            data = self.state_store.load()
            if data:
                try:
                    self.state = LightingState.from_dict(data)
                    log.info("restored last lighting state (%s)", self.state.effect)
                except (ValueError, KeyError) as exc:
                    log.warning("could not restore state: %s", exc)

        self.service = HardwareService(self.settings, debug=debug)
        self.engine = EffectEngine(self._on_frame, fps=self.settings.frame_rate)

        self.preview_keys = list(self.state.key_colors)
        self.preview_side = list(self.state.side_colors)

        self._undo: deque[dict] = deque(maxlen=UNDO_LIMIT)
        self._redo: deque[dict] = deque(maxlen=UNDO_LIMIT)
        self._last_status: ServiceSnapshot | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self.service.start()
        self.engine.set_state(self._preview_state())
        self.engine.start()
        self.engine.invalidate()

    def stop(self) -> None:
        self.engine.stop()
        self.service.stop()

    # -- state mutations ---------------------------------------------------

    def snapshot_colors(self) -> tuple[list, list]:
        return list(self.preview_keys), list(self.preview_side)

    def update(self, *, apply: bool = True, **kwargs) -> None:
        """Mutate lighting state fields and (optionally) push to hardware."""
        changed = False
        for key, value in kwargs.items():
            if not hasattr(self.state, key):
                raise AttributeError(key)
            if getattr(self.state, key) != value:
                setattr(self.state, key, value)
                changed = True
        if not changed:
            return
        self.stateChanged.emit()
        if apply:
            self.apply()

    def set_selected_color(self, color) -> None:
        color = clamp_color(color)
        if self.state.selected_color == color:
            return
        self.state.selected_color = color
        self.stateChanged.emit()

    def paint_keys(self, indices, color=None) -> None:
        """Paint key indices with a color (default: current picker color)."""
        indices = [i for i in indices if 0 <= i < NUM_KEYS]
        if not indices:
            return
        color = clamp_color(color if color is not None else self.state.selected_color)
        self._push_undo()
        before = [i for i in indices if self.state.key_colors[i] != color]
        self.state.set_key_colors(indices, color)
        if self.state.mode == "hardware":
            # painting implies per-key mode
            self.state.mode = "custom"
            self.state.effect = "static"
        elif self.state.mode == "software" and self.state.effect == "static":
            pass
        self._redo.clear()
        self.stateChanged.emit()
        self.apply()
        if not before:
            log.debug("paint: keys already had %s", color)

    def fill_keys(self, color) -> None:
        self._push_undo()
        self.state.fill_keys(color)
        self._redo.clear()
        if self.state.mode == "hardware":
            self.state.mode = "custom"
        self.stateChanged.emit()
        self.apply()

    def fill_side(self, color) -> None:
        self._push_undo()
        self.state.fill_side(color)
        self._redo.clear()
        if self.state.mode == "hardware":
            self.state.mode = "custom"
        self.stateChanged.emit()
        self.apply()

    # -- undo / redo -------------------------------------------------------

    def _push_undo(self) -> None:
        self._undo.append(
            {
                "key_colors": list(self.state.key_colors),
                "side_colors": list(self.state.side_colors),
                "mode": self.state.mode,
                "effect": self.state.effect,
            }
        )
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append(
            {
                "key_colors": list(self.state.key_colors),
                "side_colors": list(self.state.side_colors),
                "mode": self.state.mode,
                "effect": self.state.effect,
            }
        )
        self._restore(self._undo.pop())

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(
            {
                "key_colors": list(self.state.key_colors),
                "side_colors": list(self.state.side_colors),
                "mode": self.state.mode,
                "effect": self.state.effect,
            }
        )
        self._restore(self._redo.pop())

    def _restore(self, snapshot: dict) -> None:
        self.state.key_colors = list(snapshot["key_colors"])
        self.state.side_colors = list(snapshot["side_colors"])
        self.state.mode = snapshot["mode"]
        self.state.effect = snapshot["effect"]
        self.stateChanged.emit()
        self.apply()

    # -- applying ----------------------------------------------------------

    def apply(self) -> None:
        """Push the current state to hardware + preview engine."""
        self.engine.set_state(self._preview_state())
        self.engine.invalidate()
        # One apply gives instant feedback; for software effects the engine
        # keeps streaming frames afterwards.
        self.service.apply_state(self.state.copy())
        if self.settings.remember_last_state:
            self.state_store.save(self.state.to_dict())

    def _preview_state(self) -> LightingState:
        preview = self.state.copy()
        if preview.mode == "hardware":
            if preview.effect == "off":
                preview.mode = "software"
                preview.effect = "static"
                preview.key_colors = [(0, 0, 0)] * len(preview.key_colors)
                preview.side_colors = [(0, 0, 0)] * len(preview.side_colors)
                return preview
            if preview.effect == "static":
                preview.mode = "software"
                preview.effect = "static"
                preview.key_colors = [preview.color1] * len(preview.key_colors)
                preview.side_colors = [preview.color1] * len(preview.side_colors)
                return preview
            preview.mode = "software"
            preview.effect = PREVIEW_EFFECT.get(preview.effect, "static")
            if preview.effect in ("wave", "breathing", "matrix", "reactive"):
                preview.key_colors = [preview.color1] * len(preview.key_colors)
            return preview
        if preview.mode == "custom":
            preview.mode = "software"
            preview.effect = "static"
        return preview

    def _on_frame(self, keys, side, brightness) -> None:
        """Engine callback (engine thread): update preview, stream to hardware."""
        self.preview_keys = list(keys)
        self.preview_side = list(side)
        if self.state.mode == "software" and self.service.controller.is_connected:
            self.service.push_frame(keys, side, brightness)

    # -- connection --------------------------------------------------------

    def status(self) -> ServiceSnapshot:
        return self.service.snapshot()

    def notify_status(self, snapshot: ServiceSnapshot) -> None:
        """Called by the UI timer; emits user-visible messages on transitions."""
        previous = self._last_status
        self._last_status = snapshot
        if previous is None:
            return
        if previous.connected and not snapshot.connected:
            self.message.emit(
                "Everest 60 disconnected. Reconnect the keyboard and it will "
                "be restored automatically.",
                "warn",
            )
        elif not previous.connected and snapshot.connected:
            self.message.emit(f"{snapshot.name} connected ({snapshot.path})", "info")

    # -- presets -----------------------------------------------------------

    def list_presets(self):
        return self.store.list()

    def load_preset(self, preset: Preset) -> None:
        self._push_undo()
        self.state = preset.state.copy()
        self._redo.clear()
        self.stateChanged.emit()
        self.apply()
        self.message.emit(f"Preset '{preset.name}' loaded", "info")

    def save_preset(self, name: str, description: str = "") -> Preset:
        preset = Preset.from_state(name, self.state, description)
        self.store.save(preset)
        self.presetsChanged.emit()
        self.message.emit(f"Preset '{name}' saved", "info")
        return preset

    def delete_preset(self, preset: Preset) -> None:
        self.store.delete(preset)
        self.presetsChanged.emit()
        self.message.emit(f"Preset '{preset.name}' deleted", "info")

    def rename_preset(self, preset: Preset, new_name: str) -> Preset:
        renamed = self.store.rename(preset, new_name)
        self.presetsChanged.emit()
        return renamed

    def duplicate_preset(self, preset: Preset) -> Preset:
        copy = self.store.duplicate(preset, f"{preset.name} copy")
        self.presetsChanged.emit()
        return copy

    def import_preset(self, path) -> Preset:
        imported = self.store.import_file(path)
        self.presetsChanged.emit()
        self.message.emit(f"Imported preset '{imported.name}'", "info")
        return imported

    def export_preset(self, preset: Preset, path):
        exported = self.store.export(preset, path)
        self.message.emit(f"Exported to {exported}", "info")
        return exported

    # -- settings ----------------------------------------------------------

    def save_settings(self) -> None:
        self.settings.save()
        self.engine.fps = self.settings.frame_rate
        self.message.emit("Settings saved", "info")
