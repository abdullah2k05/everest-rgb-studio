"""Preset storage: built-in presets (packaged) + user presets (XDG data)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..models.preset import Preset
from ..utils.logging import data_dir

log = logging.getLogger(__name__)

BUILTIN_DIR = Path(__file__).resolve().parent / "builtin"


class PresetStore:
    def __init__(self, user_dir: Path | None = None, builtin_dir: Path | None = None):
        self.user_dir = Path(user_dir) if user_dir else data_dir() / "presets"
        self.builtin_dir = Path(builtin_dir) if builtin_dir else BUILTIN_DIR

    # -- listing -----------------------------------------------------------

    def _iter_dir(self, directory: Path, *, builtin: bool) -> list[Preset]:
        presets: list[Preset] = []
        if not directory.is_dir():
            return presets
        for path in sorted(directory.glob("*.json")):
            try:
                presets.append(Preset.load(path, builtin=builtin))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                log.warning("skipping broken preset %s: %s", path, exc)
        return presets

    def list(self) -> list[Preset]:
        """Built-in presets first, then user presets, sorted by name."""
        builtin = self._iter_dir(self.builtin_dir, builtin=True)
        user = self._iter_dir(self.user_dir, builtin=False)
        return sorted(builtin, key=lambda p: p.name.lower()) + sorted(
            user, key=lambda p: p.name.lower()
        )

    def names(self) -> list[str]:
        return [p.name for p in self.list()]

    # -- lookup ------------------------------------------------------------

    def load(self, name: str) -> Preset | None:
        needle = name.strip().lower()
        for preset in self.list():
            if preset.name.lower() == needle:
                return preset
        # allow loading by file stem for user presets
        candidate = self.user_dir / f"{name}.json"
        if candidate.is_file():
            try:
                return Preset.load(candidate)
            except (OSError, ValueError) as exc:
                log.warning("could not load %s: %s", candidate, exc)
        return None

    # -- mutation ----------------------------------------------------------

    def save(self, preset: Preset, *, name: str | None = None) -> Path:
        if name:
            preset.name = name
        if preset.builtin:
            preset.builtin = False  # saving a builtin creates a user copy
        preset.path = self.user_dir / f"{_slug(preset.name)}.json"
        return preset.save()

    def delete(self, preset: Preset | str) -> bool:
        if isinstance(preset, str):
            preset_obj = self.load(preset)
            preset = preset_obj
            if preset is None:
                return False
        if preset.builtin:
            raise ValueError("built-in presets cannot be deleted")
        if preset.path is None:
            return False
        try:
            preset.path.unlink()
            return True
        except OSError as exc:
            log.warning("could not delete %s: %s", preset.path, exc)
            return False

    def duplicate(self, preset: Preset, new_name: str) -> Preset:
        copy = Preset.from_state(new_name, preset.state, preset.description)
        self.save(copy)
        return copy

    def rename(self, preset: Preset, new_name: str) -> Preset:
        if not preset.builtin and preset.path is not None and preset.path.is_file():
            try:
                preset.path.unlink()
            except OSError as exc:
                log.warning("could not remove old preset file: %s", exc)
        preset.name = new_name
        preset.path = None
        preset.builtin = False
        self.save(preset)
        return preset

    # -- import / export ---------------------------------------------------

    def import_file(self, source: Path) -> Preset:
        preset = Preset.load(Path(source))
        existing = self.load(preset.name)
        if existing is not None:
            preset.name = _unique_name(self, preset.name)
        self.save(preset)
        return preset

    def export(self, preset: Preset, target: Path) -> Path:
        target = Path(target)
        if target.is_dir():
            target = target / f"{_slug(preset.name)}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(preset.to_dict(), indent=2) + "\n", encoding="utf-8")
        return target


def _slug(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in name)
    return cleaned.strip().replace(" ", "_") or "preset"


def _unique_name(store: PresetStore, base: str) -> str:
    existing = {n.lower() for n in store.names()}
    if base.lower() not in existing:
        return base
    counter = 2
    while f"{base} {counter}".lower() in existing:
        counter += 1
    return f"{base} {counter}"
