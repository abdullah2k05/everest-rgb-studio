"""Preset model: serialisable snapshot of a lighting configuration."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .lighting import LightingState

SCHEMA_VERSION = 1


@dataclass
class Preset:
    name: str
    description: str = ""
    state: LightingState = field(default_factory=LightingState)
    created: float = 0.0
    modified: float = 0.0
    builtin: bool = False
    path: Path | None = None

    # -- serialisation -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        payload = self.state.to_dict()
        payload.update(
            {
                "schema": SCHEMA_VERSION,
                "name": self.name,
                "description": self.description,
                "created": self.created,
                "modified": self.modified,
            }
        )
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, path: Path | None = None, builtin: bool = False) -> "Preset":
        schema = int(data.get("schema", 1))
        if schema > SCHEMA_VERSION:
            raise ValueError(f"preset schema {schema} is newer than supported {SCHEMA_VERSION}")
        name = str(data.get("name") or (path.stem if path else "Unnamed"))
        state = LightingState.from_dict(data)
        return cls(
            name=name,
            description=str(data.get("description", "")),
            state=state,
            created=float(data.get("created", 0.0)),
            modified=float(data.get("modified", 0.0)),
            builtin=builtin,
            path=path,
        )

    @classmethod
    def from_state(
        cls,
        name: str,
        state: LightingState,
        description: str = "",
        *,
        now: float | None = None,
    ) -> "Preset":
        timestamp = time.time() if now is None else now
        return cls(
            name=name,
            description=description,
            state=state.copy(),
            created=timestamp,
            modified=timestamp,
        )

    # -- file I/O ----------------------------------------------------------

    @classmethod
    def load(cls, path: Path, *, builtin: bool = False) -> "Preset":
        with Path(path).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"preset file {path} is not a JSON object")
        return cls.from_dict(data, path=Path(path), builtin=builtin)

    def save(self, path: Path | None = None) -> Path:
        """Write the preset to disk (default: user preset directory)."""
        target = Path(path or self.path or _default_preset_path(self.name))
        target.parent.mkdir(parents=True, exist_ok=True)
        self.modified = time.time()
        if not self.created:
            self.created = self.modified
        payload = json.dumps(self.to_dict(), indent=2, sort_keys=False)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(payload + "\n", encoding="utf-8")
        tmp.replace(target)
        self.path = target
        return target

    @property
    def summary(self) -> str:
        mode = self.state.mode
        if mode == "custom":
            return f"per-key · brightness {self.state.brightness}%"
        return f"{self.state.effect} ({mode}) · brightness {self.state.brightness}%"


def _default_preset_path(name: str) -> Path:
    from ..utils.logging import data_dir

    slug = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in name)
    return data_dir() / "presets" / f"{slug.strip().replace(' ', '_') or 'preset'}.json"
