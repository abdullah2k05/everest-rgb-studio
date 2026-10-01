"""Lighting page: effect selection, colors, brightness, painting."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..hardware import protocol
from ..models.keyboard import KEYS
from . import theme
from .app_controller import AppController
from .color_picker import ColorPicker

HARDWARE_EFFECTS = [
    ("static", "Static"),
    ("wave", "Wave"),
    ("tornado", "Tornado"),
    ("breathing", "Breathing"),
    ("reactive", "Reactive"),
    ("matrix", "Matrix"),
    ("yeti", "Yeti"),
    ("off", "Off"),
]


def _slider_row(title: str, *, maximum: int = 100) -> tuple[QWidget, QSlider, QLabel]:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)

    label = QLabel(title)
    label.setFixedWidth(86)
    label.setStyleSheet(f"color: {theme.FG_DIM};")

    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, maximum)
    slider.setSingleStep(1)
    slider.setPageStep(10)

    value = QLabel("0")
    value.setFixedWidth(64)
    value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    value.setStyleSheet(f"color: {theme.FG};")

    layout.addWidget(label)
    layout.addWidget(slider, 1)
    layout.addWidget(value)
    return row, slider, value


class LightingPanel(QWidget):
    """Default page: everything needed for the common cases."""

    def __init__(self, controller: AppController, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self._guard = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        header = QHBoxLayout()
        heading = QLabel("Lighting")
        heading.setObjectName("heading")
        self.selection_label = QLabel("No keys selected")
        self.selection_label.setObjectName("subheading")
        header.addWidget(heading)
        header.addStretch(1)
        header.addWidget(self.selection_label)
        root.addLayout(header)

        # -- top: mode + effect + colors -----------------------------------
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)

        self.source_combo = QComboBox()
        self.source_combo.addItem("Hardware effect", "hardware")
        self.source_combo.addItem("Per-key custom", "custom")
        self.source_combo.addItem("Software effect", "software")
        self.source_combo.currentIndexChanged.connect(self._source_changed)

        self.effect_combo = QComboBox()
        self.effect_combo.currentIndexChanged.connect(self._effect_changed)

        grid.addWidget(QLabel("Mode"), 0, 0)
        grid.addWidget(self.source_combo, 0, 1)
        grid.addWidget(QLabel("Effect"), 1, 0)
        grid.addWidget(self.effect_combo, 1, 1)
        root.addLayout(grid)

        colors_row = QHBoxLayout()
        colors_row.setSpacing(16)

        primary_box = QFrame()
        primary_box.setStyleSheet(
            f"background: {theme.BG_PANEL}; border: 1px solid {theme.BORDER}; border-radius: 8px;"
        )
        primary_layout = QVBoxLayout(primary_box)
        primary_layout.setContentsMargins(12, 10, 12, 12)
        title = QLabel("Primary color")
        title.setStyleSheet(f"color: {theme.FG_DIM}; font-weight: 600;")
        primary_layout.addWidget(title)
        self.picker = ColorPicker()
        self.picker.colorChanged.connect(self._color_changed)
        primary_layout.addWidget(self.picker)
        colors_row.addWidget(primary_box, 1)

        right_box = QFrame()
        right_box.setStyleSheet(
            f"background: {theme.BG_PANEL}; border: 1px solid {theme.BORDER}; border-radius: 8px;"
        )
        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(12, 10, 12, 12)
        right_layout.setSpacing(10)

        secondary_row = QHBoxLayout()
        secondary_row.setSpacing(8)
        sec_label = QLabel("Secondary")
        sec_label.setFixedWidth(78)
        sec_label.setStyleSheet(f"color: {theme.FG_DIM};")
        self.secondary_btn = QPushButton()
        self.secondary_btn.setFixedHeight(30)
        self.secondary_btn.clicked.connect(self._pick_secondary)
        self.color_mode_combo = QComboBox()
        self.color_mode_combo.addItem("Single", protocol.COLOR_SINGLE)
        self.color_mode_combo.addItem("Dual", protocol.COLOR_DUAL)
        self.color_mode_combo.addItem("Rainbow", protocol.COLOR_RAINBOW)
        self.color_mode_combo.currentIndexChanged.connect(self._color_mode_changed)
        secondary_row.addWidget(sec_label)
        secondary_row.addWidget(self.secondary_btn, 1)
        secondary_row.addWidget(self.color_mode_combo)
        right_layout.addLayout(secondary_row)

        self.brightness_row, self.brightness, self.brightness_value = _slider_row("Brightness")
        self.speed_row, self.speed, self.speed_value = _slider_row("Speed")
        self.brightness.valueChanged.connect(self._brightness_changed)
        self.speed.valueChanged.connect(self._speed_changed)

        direction_row = QHBoxLayout()
        direction_row.setSpacing(10)
        dir_label = QLabel("Direction")
        dir_label.setFixedWidth(86)
        dir_label.setStyleSheet(f"color: {theme.FG_DIM};")
        self.direction_combo = QComboBox()
        for key, text in (
            ("left_to_right", "Left → Right"),
            ("right_to_left", "Right → Left"),
            ("top_to_bottom", "Top → Bottom"),
            ("bottom_to_top", "Bottom → Top"),
            ("cw", "Clockwise"),
            ("ccw", "Counter-clockwise"),
        ):
            self.direction_combo.addItem(text, key)
        self.direction_combo.currentIndexChanged.connect(self._direction_changed)
        direction_row.addWidget(dir_label)
        direction_row.addWidget(self.direction_combo, 1)

        right_layout.addWidget(self.brightness_row)
        right_layout.addWidget(self.speed_row)
        right_layout.addLayout(direction_row)
        colors_row.addWidget(right_box, 1)
        root.addLayout(colors_row)

        # -- steps hint -----------------------------------------------------
        self.steps_hint = QLabel("Brightness and speed snap to the keyboard's 25-step scale.")
        self.steps_hint.setObjectName("subheading")
        root.addWidget(self.steps_hint)

        # -- actions --------------------------------------------------------
        actions = QHBoxLayout()
        actions.setSpacing(8)

        self.paint_btn = QPushButton("Apply to selected keys")
        self.paint_btn.setObjectName("primary")
        self.paint_btn.clicked.connect(self._paint_selection)

        self.fill_all_btn = QPushButton("Fill all keys")
        self.fill_all_btn.clicked.connect(self._fill_all)

        self.fill_side_btn = QPushButton("Set side ring")
        self.fill_side_btn.clicked.connect(self._fill_side)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self._apply)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self._reset)

        for button in (
            self.paint_btn,
            self.fill_all_btn,
            self.fill_side_btn,
            self.apply_btn,
            self.reset_btn,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        root.addLayout(actions)
        root.addStretch(1)

        # debounce slider-driven applies
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(160)
        self._debounce.timeout.connect(self._apply)

        controller.stateChanged.connect(self.refresh)
        controller.message.connect(self._on_message)
        self.refresh()

    # -- external updates --------------------------------------------------

    def refresh(self) -> None:
        if self._guard:
            return
        self._guard = True
        try:
            state = self.controller.state
            index = self.source_combo.findData(state.mode)
            if index >= 0 and self.source_combo.currentIndex() != index:
                self.source_combo.blockSignals(True)
                self.source_combo.setCurrentIndex(index)
                self.source_combo.blockSignals(False)
            self._rebuild_effect_combo()
            effect_index = self.effect_combo.findData(state.effect)
            if effect_index >= 0:
                self.effect_combo.blockSignals(True)
                self.effect_combo.setCurrentIndex(effect_index)
                self.effect_combo.blockSignals(False)

            self.picker.set_color(state.color1)
            self._set_secondary_color(state.color2)
            cm = self.color_mode_combo.findData(state.color_mode)
            if cm >= 0:
                self.color_mode_combo.blockSignals(True)
                self.color_mode_combo.setCurrentIndex(cm)
                self.color_mode_combo.blockSignals(False)
            self._set_slider(self.brightness, self.brightness_value, state.brightness)
            self._set_slider(self.speed, self.speed_value, state.speed)
            d = self.direction_combo.findData(state.direction)
            if d >= 0:
                self.direction_combo.blockSignals(True)
                self.direction_combo.setCurrentIndex(d)
                self.direction_combo.blockSignals(False)

            self.brightness_value.setText(f"{state.brightness}%")
            self.speed_value.setText(f"{state.speed}%")
            self._update_controls_for_mode(state.mode)
            self._update_selection_label()
        finally:
            self._guard = False

    @staticmethod
    def _set_slider(slider: QSlider, label: QLabel, value: int) -> None:
        if slider.value() != value:
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
        label.setText(f"{value}%")

    def _rebuild_effect_combo(self) -> None:
        mode = self.controller.state.mode
        current = self.effect_combo.currentData()
        self.effect_combo.blockSignals(True)
        self.effect_combo.clear()
        if mode == "hardware":
            for name, label in HARDWARE_EFFECTS:
                self.effect_combo.addItem(label, name)
        elif mode == "software":
            from ..effects.standard import EFFECTS

            for name, effect in EFFECTS.items():
                self.effect_combo.addItem(effect.label, name)
        else:  # custom per-key
            self.effect_combo.addItem("Per-key colors", "static")
        index = self.effect_combo.findData(current)
        if index >= 0:
            self.effect_combo.setCurrentIndex(index)
        self.effect_combo.blockSignals(False)

    def _update_controls_for_mode(self, mode: str) -> None:
        hardware = mode == "hardware"
        self.effect_combo.setEnabled(mode != "custom")
        self.color_mode_combo.setEnabled(hardware)
        self.direction_combo.setEnabled(mode != "custom")
        # painting only makes sense with keys selected
        self.paint_btn.setEnabled(bool(self._selected_keys()))

    def _update_selection_label(self) -> None:
        selection = self._selected_keys()
        keyboard = self.window().findChild(QWidget, "keyboardWidget")
        side = getattr(keyboard, "side_selected", False)
        if side:
            self.selection_label.setText("Side ring selected")
            return
        if not selection:
            self.selection_label.setText("No keys selected")
            return
        names = [KEYS[i].name for i in selection[:6]]
        suffix = "…" if len(selection) > 6 else ""
        self.selection_label.setText(
            f"{len(selection)} key{'s' if len(selection) != 1 else ''} selected: "
            + " ".join(names) + suffix
        )

    def _selected_keys(self) -> list[int]:
        window = self.window()
        widget = window.findChild(QWidget, "keyboardWidget") if window else None
        if widget is None or not hasattr(widget, "selection"):
            return []
        return list(widget.selection())

    # -- control handlers --------------------------------------------------

    def _source_changed(self) -> None:
        if self._guard:
            return
        mode = self.source_combo.currentData()
        self.controller.update(mode=mode)
        self._rebuild_effect_combo()
        self._update_controls_for_mode(mode)

    def _effect_changed(self) -> None:
        if self._guard:
            return
        name = self.effect_combo.currentData()
        if name is None:
            return
        state = self.controller.state
        if state.mode == "custom" and name != "static":
            self.controller.update(mode="software", effect=name)
        else:
            self.controller.update(effect=name)

    def _color_changed(self, color) -> None:
        if self._guard:
            return
        self.controller.set_selected_color(color)
        if self.controller.state.mode == "hardware" and self.controller.state.effect == "static":
            self.controller.update(color1=tuple(color))

    def _pick_secondary(self) -> None:
        from PySide6.QtWidgets import QColorDialog

        state = self.controller.state
        current = QColorDialog.getColor(QColor(*state.color2), self, "Secondary color")
        if current.isValid():
            self.controller.update(
                color2=(current.red(), current.green(), current.blue())
            )
            self._set_secondary_color((current.red(), current.green(), current.blue()))

    def _set_secondary_color(self, color) -> None:
        self.secondary_btn.setStyleSheet(
            f"background: #{color[0]:02X}{color[1]:02X}{color[2]:02X}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 6px;"
        )

    def _color_mode_changed(self) -> None:
        if self._guard:
            return
        self.controller.update(color_mode=self.color_mode_combo.currentData())

    def _brightness_changed(self, value: int) -> None:
        if self._guard:
            return
        self.brightness_value.setText(f"{value}%")
        self.steps_hint.setText(
            f"Brightness {value}% → hardware step {protocol.quantize_step(value)}%"
        )
        self._debounce.start()

    def _speed_changed(self, value: int) -> None:
        if self._guard:
            return
        self.speed_value.setText(f"{value}%")
        self._debounce.start()

    def _direction_changed(self) -> None:
        if self._guard:
            return
        self.controller.update(direction=self.direction_combo.currentData())

    def _paint_selection(self) -> None:
        selection = self._selected_keys()
        if not selection:
            self.controller.message.emit("Select keys on the keyboard first", "warn")
            return
        self.controller.paint_keys(selection)

    def _fill_all(self) -> None:
        self.controller.fill_keys(self.controller.state.selected_color)

    def _fill_side(self) -> None:
        self.controller.fill_side(self.controller.state.selected_color)

    def _apply(self) -> None:
        self.controller.update(
            brightness=self.brightness.value(),
            speed=self.speed.value(),
        )

    def _reset(self) -> None:
        self.controller.state = type(self.controller.state)()
        self.controller.stateChanged.emit()
        self.controller.apply()

    def _on_message(self, text: str, level: str) -> None:
        if level == "warn":
            self.steps_hint.setText(text)
