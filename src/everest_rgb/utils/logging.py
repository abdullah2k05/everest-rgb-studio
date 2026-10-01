"""Logging setup."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DEBUG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s [%(threadName)s]: %(message)s"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "everest-rgb-studio"


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "everest-rgb-studio"


def setup_logging(debug: bool = False, *, log_file: bool = True) -> logging.Logger:
    """Configure root logging. Detailed packet tracing only in debug mode."""
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:  # reconfigure on repeated calls (CLI restarts, tests)
        for handler in list(root.handlers):
            root.removeHandler(handler)

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(DEBUG_FORMAT if debug else LOG_FORMAT))
    root.addHandler(console)

    if log_file:
        try:
            log_path = data_dir() / "logs"
            log_path.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_path / "everest-rgb.log", maxBytes=512_000, backupCount=2
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter(DEBUG_FORMAT))
            root.addHandler(file_handler)
        except OSError as exc:  # pragma: no cover - unwritable home
            root.warning("file logging disabled: %s", exc)

    # hidapi is chatty at DEBUG; keep our own namespace in control.
    logging.getLogger("hid").setLevel(logging.WARNING)
    return root
