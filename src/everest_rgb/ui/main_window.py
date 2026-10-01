"""Main window: sidebar navigation, keyboard preview, stacked control pages."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .app_controller import AppController
from .effects_panel import EffectsPanel
from .keyboard_widget import MODE_PAINT, MODE_SELECT, KeyboardWidget
from .lighting_panel import LightingPanel
from .presets_panel import PresetsPanel
from .settings_panel import SettingsPanel

log = logging.getLogger(__name__)

NAV = (
    ("Lighting", "lighting"),
    ("Effects", "effects"),
    ("Presets", "presets"),
    ("Settings", "settings"),
)


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController):
        super().__init__()
        self.controller = controller

        self.setWindowTitle("Everest RGB Studio")
        self.resize(1240, 860)
        self.setMinimumSize(1000, 680)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- sidebar --------------------------------------------------------
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(theme.SIDEBAR_WIDTH)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(12, 16, 12, 16)
        side_layout.setSpacing(4)

        logo = QLabel("EVEREST")
        logo.setStyleSheet(
            f"font-size: 15px; font-weight: 700; letter-spacing: 3px; color: {theme.FG};"
        )
        sub = QLabel("RGB Studio")
        sub.setStyleSheet(f"font-size: 11px; color: {theme.FG_DIM}; letter-spacing: 1px;")
        side_layout.addWidget(logo)
        side_layout.addWidget(sub)
        side_layout.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for label, key in NAV:
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            side_layout.addWidget(button)
        side_layout.addStretch(1)

        self.status_label = QLabel("○ Everest 60 Disconnected")
        self.status_label.setObjectName("statusDot")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {theme.FG_DIM}; font-size: 12px;")
        side_layout.addWidget(self.status_label)

        self.mode_label = QLabel("Mode: select")
        self.mode_label.setStyleSheet(f"color: {theme.FG_DIM}; font-size: 11px;")
        side_layout.addWidget(self.mode_label)

        root.addWidget(sidebar)

        # -- main column ----------------------------------------------------
        main_col = QVBoxLayout()
        main_col.setContentsMargins(16, 12, 16, 8)
        main_col.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        title = QLabel("Everest 60")
        title.setObjectName("heading")
        toolbar.addWidget(title)

        self.select_btn = QPushButton("Select")
        self.select_btn.setCheckable(True)
        self.select_btn.setChecked(True)
        self.paint_btn = QPushButton("Paint")
        self.paint_btn.setCheckable(True)
        self.paint_btn.setToolTip("Drag across keys to paint them")
        self.select_btn.clicked.connect(lambda: self._set_mode(MODE_SELECT))
        self.paint_btn.clicked.connect(lambda: self._set_mode(MODE_PAINT))
        toolbar.addSpacing(14)
        toolbar.addWidget(self.select_btn)
        toolbar.addWidget(self.paint_btn)

        self.paint_swatch = QFrame()
        self.paint_swatch.setFixedSize(26, 26)
        self.paint_swatch.setStyleSheet(
            f"background: #FFFFFF; border: 1px solid {theme.BORDER}; border-radius: 5px;"
        )
        self.paint_swatch.setToolTip("Current paint color")
        toolbar.addWidget(self.paint_swatch)

        toolbar.addStretch(1)
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setObjectName("tool")
        self.undo_btn.clicked.connect(self.controller.undo)
        self.redo_btn = QPushButton("Redo")
        self.redo_btn.setObjectName("tool")
        self.redo_btn.clicked.connect(self.controller.redo)
        toolbar.addWidget(self.undo_btn)
        toolbar.addWidget(self.redo_btn)
        main_col.addLayout(toolbar)

        # keyboard preview
        self.keyboard = KeyboardWidget()
        self.keyboard.setObjectName("keyboardWidget")
        self.keyboard.setMinimumHeight(270)
        self.keyboard.setMaximumHeight(420)
        self.keyboard.selectionChanged.connect(self._selection_changed)
        self.keyboard.sideSelectionChanged.connect(self._side_selection_changed)
        self.keyboard.keysPainted.connect(self.controller.paint_keys)
        main_col.addWidget(self.keyboard, 3)

        # pages
        self.stack = QStackedWidget()
        self.pages = {
            "lighting": LightingPanel(controller),
            "effects": EffectsPanel(controller),
            "presets": PresetsPanel(controller),
            "settings": SettingsPanel(controller),
        }
        for key, page in self.pages.items():
            self.stack.addWidget(page)
        main_col.addWidget(self.stack, 2)

        root.addLayout(main_col, 1)
        self.setCentralWidget(central)

        # -- status bar -----------------------------------------------------
        self.statusBar().showMessage("Ready")
        self.conn_detail = QLabel("")
        self.conn_detail.setObjectName("dim")
        self.statusBar().addPermanentWidget(self.conn_detail)

        # -- wiring ---------------------------------------------------------
        for key, button in self.nav_buttons.items():
            button.clicked.connect(lambda _=False, k=key: self._show_page(k))
        self.nav_buttons["lighting"].setChecked(True)

        self.controller.message.connect(self._on_message)
        self.controller.stateChanged.connect(self._state_changed)

        # preview refresh (engine renders in its own thread; we copy colors here)
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(40)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._preview_timer.start()

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(500)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

        self._install_shortcuts()
        self._refresh_status()
        self._state_changed()

    # -- navigation --------------------------------------------------------

    def _show_page(self, key: str) -> None:
        self.stack.setCurrentWidget(self.pages[key])

    # -- keyboard mode -----------------------------------------------------

    def _set_mode(self, mode: str) -> None:
        self.keyboard.set_mode(mode)
        self.select_btn.setChecked(mode == MODE_SELECT)
        self.paint_btn.setChecked(mode == MODE_PAINT)
        self.mode_label.setText(f"Mode: {mode}")

    def _selection_changed(self, _selection) -> None:
        self.pages["lighting"]._update_selection_label()
        self.pages["lighting"]._update_controls_for_mode(self.controller.state.mode)

    def _side_selection_changed(self, selected: bool) -> None:
        self.pages["lighting"]._update_selection_label()
        if selected:
            self.statusBar().showMessage("Side ring selected — use “Set side ring” to color it")

    # -- state / preview ---------------------------------------------------

    def _state_changed(self) -> None:
        color = self.controller.state.selected_color
        self.paint_swatch.setStyleSheet(
            f"background: #{color[0]:02X}{color[1]:02X}{color[2]:02X}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 5px;"
        )
        self.keyboard.set_paint_color(color)
        self.undo_btn.setEnabled(self.controller.can_undo())
        self.redo_btn.setEnabled(self.controller.can_redo())
        self.keyboard.set_show_side(self.controller.settings.show_side_ring)

    def _refresh_preview(self) -> None:
        keys, side = self.controller.snapshot_colors()
        self.keyboard.set_colors(keys, side)

    def _refresh_status(self) -> None:
        snapshot = self.controller.status()
        self.status_label.setText(snapshot.status_text)
        color = theme.SUCCESS if snapshot.connected else (
            theme.ACCENT if snapshot.connecting else theme.FG_DIM
        )
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")
        if snapshot.connected:
            detail = f"{snapshot.path}  ·  if {snapshot.interface}  ·  tx {snapshot.tx_count} rx {snapshot.rx_count}"
        elif snapshot.last_error:
            detail = snapshot.last_error
        else:
            detail = "keyboard not found"
        self.conn_detail.setText(detail)
        self.keyboard.set_connected(snapshot.connected)
        self.keyboard.set_show_side(self.controller.settings.show_side_ring)
        self.controller.notify_status(snapshot)

    def _on_message(self, text: str, level: str) -> None:
        self.statusBar().showMessage(text, 6000 if level == "info" else 12000)
        log.info("%s: %s", level, text)

    # -- shortcuts ---------------------------------------------------------

    def _install_shortcuts(self) -> None:
        def add(key: str, slot, name: str) -> None:
            action = QAction(name, self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(slot)
            self.addAction(action)

        add("Ctrl+Z", self.controller.undo, "Undo")
        add("Ctrl+Shift+Z", self.controller.redo, "Redo")
        add("Ctrl+Y", self.controller.redo, "Redo")
        add("Ctrl+A", self.keyboard.select_all, "Select all")
        add("Esc", self.keyboard.clear_selection, "Clear selection")
        add("Ctrl+S", self._quick_save, "Save preset")
        add("Ctrl+1", lambda: self._show_page("lighting"), "Lighting page")
        add("Ctrl+2", lambda: self._show_page("effects"), "Effects page")
        add("Ctrl+3", lambda: self._show_page("presets"), "Presets page")
        add("Ctrl+4", lambda: self._show_page("settings"), "Settings page")
        add("Ctrl+B", self._toggle_paint, "Toggle paint mode")

    def _toggle_paint(self) -> None:
        mode = MODE_PAINT if self.keyboard.mode == MODE_SELECT else MODE_SELECT
        self._set_mode(mode)

    def _quick_save(self) -> None:
        self._show_page("presets")
        self.pages["presets"].name_edit.setFocus()

    # -- lifecycle ---------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802
        self._preview_timer.stop()
        self._status_timer.stop()
        self.controller.stop()
        super().closeEvent(event)
