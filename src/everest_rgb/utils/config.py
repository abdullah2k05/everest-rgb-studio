"""Application settings and persisted lighting state (JSON in XDG config)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from ..utils.logging import config_dir, data_dir

log = logging.getLogger(__name__)

SETTINGS_FILE = "settings.json"
STATE_FILE = "last_state.json"


@dataclass
class Settings:
    debug_logging: bool = False
    auto_reconnect: bool = True
    reconnect_interval_s: float = 3.0
    remember_last_state: bool = True
    restore_on_connect: bool = True
    launch_on_startup: bool = False
    start_minimized: bool = False
    frame_rate: int = 25
    show_side_ring: bool = True

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        target = path or (config_dir() / SETTINGS_FILE)
        settings = cls()
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return settings
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("could not read %s: %s", target, exc)
            return settings
        known = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key in known:
                setattr(settings, key, value)
        return settings

    def save(self, path: Path | None = None) -> Path:
        target = path or (config_dir() / SETTINGS_FILE)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(self), indent=2)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(payload + "\n", encoding="utf-8")
        tmp.replace(target)
        return target


class StateStore:
    """Persists the last applied lighting state for reconnect restoration."""

    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / STATE_FILE)

    def load(self) -> dict[str, Any] | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("could not read last state %s: %s", self.path, exc)
            return None
        return data if isinstance(data, dict) else None

    def save(self, state_dict: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state_dict, indent=2) + "\n", encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            log.warning("could not save last state: %s", exc)

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass
