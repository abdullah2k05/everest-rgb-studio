"""Graphical entry point: everest-rgb-gui / everest-rgb gui."""

from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
from .utils.logging import setup_logging

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None, *, debug: bool | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="everest-rgb-gui", description="Everest RGB Studio graphical interface"
    )
    parser.add_argument("--version", action="version", version=f"everest-rgb {__version__}")
    parser.add_argument("--debug", action="store_true", help="verbose logging incl. HID packets")
    parser.add_argument("--minimized", action="store_true", help="start minimized")
    args = parser.parse_args(argv)

    if debug is None:
        debug = args.debug

    from .utils.config import Settings

    settings = Settings.load()
    if debug:
        settings.debug_logging = True
    setup_logging(debug=settings.debug_logging)

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 is required for the GUI.\n"
            "  pacman -S pyside6        (or: pip install PySide6)",
            file=sys.stderr,
        )
        return 1

    from .ui.app_controller import AppController
    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

    app = QApplication(sys.argv[:1])
    app.setApplicationName("Everest RGB Studio")
    app.setOrganizationName("everest-rgb-studio")
    app.setDesktopFileName("everest-rgb-studio")
    apply_theme(app)

    controller = AppController(settings, debug=settings.debug_logging)
    controller.start()

    window = MainWindow(controller)
    if settings.start_minimized or args.minimized:
        window.showMinimized()
    else:
        window.show()

    try:
        exit_code = app.exec()
    finally:
        controller.stop()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
