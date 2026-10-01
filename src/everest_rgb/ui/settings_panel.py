"""Settings page: application behaviour options."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .app_controller import AppController


class SettingsPanel(QWidget):
    def __init__(self, controller: AppController, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        settings = controller.settings
        self._guard = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        heading = QLabel("Settings")
        heading.setObjectName("heading")
        root.addWidget(heading)

        connection = QGroupBox("Connection")
        conn_layout = QGridLayout(connection)
        self.auto_reconnect = QCheckBox("Reconnect automatically when the keyboard returns")
        self.auto_reconnect.setChecked(settings.auto_reconnect)
        self.auto_reconnect.toggled.connect(lambda v: self._set("auto_reconnect", v))

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("Reconnect interval"))
        self.interval = QDoubleSpinBox()
        self.interval.setRange(1.0, 60.0)
        self.interval.setSingleStep(0.5)
        self.interval.setSuffix(" s")
        self.interval.setValue(settings.reconnect_interval_s)
        self.interval.valueChanged.connect(lambda v: self._set("reconnect_interval_s", v))
        interval_row.addWidget(self.interval)
        interval_row.addStretch(1)

        self.remember = QCheckBox("Remember last lighting state")
        self.remember.setChecked(settings.remember_last_state)
        self.remember.toggled.connect(lambda v: self._set("remember_last_state", v))

        self.restore = QCheckBox("Restore that state after reconnecting")
        self.restore.setChecked(settings.restore_on_connect)
        self.restore.toggled.connect(lambda v: self._set("restore_on_connect", v))

        conn_layout.addWidget(self.auto_reconnect, 0, 0, 1, 2)
        conn_layout.addLayout(interval_row, 1, 0, 1, 2)
        conn_layout.addWidget(self.remember, 2, 0, 1, 2)
        conn_layout.addWidget(self.restore, 3, 0, 1, 2)
        root.addWidget(connection)

        behaviour = QGroupBox("Behaviour")
        beh_layout = QGridLayout(behaviour)

        self.debug = QCheckBox("Debug logging (HID packet trace → ~/.local/share/everest-rgb-studio/logs)")
        self.debug.setChecked(settings.debug_logging)
        self.debug.toggled.connect(lambda v: self._set("debug_logging", v))

        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel("Animation frame rate"))
        self.fps = QSpinBox()
        self.fps.setRange(5, 60)
        self.fps.setSuffix(" FPS")
        self.fps.setValue(settings.frame_rate)
        self.fps.valueChanged.connect(lambda v: self._set("frame_rate", v))
        fps_row.addWidget(self.fps)
        fps_row.addStretch(1)

        self.start_minimized = QCheckBox("Start minimized (applies on next start)")
        self.start_minimized.setChecked(settings.start_minimized)
        self.start_minimized.toggled.connect(lambda v: self._set("start_minimized", v))

        self.launch = QCheckBox("Launch on startup (needs desktop integration)")
        self.launch.setChecked(settings.launch_on_startup)
        self.launch.toggled.connect(lambda v: self._set("launch_on_startup", v))

        self.show_side = QCheckBox("Show side LED ring in the preview")
        self.show_side.setChecked(settings.show_side_ring)
        self.show_side.toggled.connect(lambda v: self._set("show_side_ring", v))

        beh_layout.addWidget(self.debug, 0, 0, 1, 2)
        beh_layout.addLayout(fps_row, 1, 0, 1, 2)
        beh_layout.addWidget(self.start_minimized, 2, 0, 1, 2)
        beh_layout.addWidget(self.launch, 3, 0, 1, 2)
        beh_layout.addWidget(self.show_side, 4, 0, 1, 2)
        root.addWidget(behaviour)

        actions = QHBoxLayout()
        save_btn = QPushButton("Save settings")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)
        actions.addWidget(save_btn)
        actions.addStretch(1)
        root.addLayout(actions)

        paths = QLabel(
            "Settings: ~/.config/everest-rgb-studio/settings.json\n"
            "State:   ~/.local/share/everest-rgb-studio/last_state.json\n"
            "Presets: ~/.local/share/everest-rgb-studio/presets/"
        )
        paths.setObjectName("subheading")
        root.addWidget(paths)
        root.addStretch(1)

    def _set(self, field: str, value) -> None:
        if self._guard:
            return
        setattr(self.controller.settings, field, value)

    def _save(self) -> None:
        self.controller.save_settings()
