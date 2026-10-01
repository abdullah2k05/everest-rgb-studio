"""Effects page: software effect designer (client-side animation)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..effects.standard import EFFECTS
from . import theme
from .app_controller import AppController
from .color_picker import ColorPicker


class EffectsPanel(QWidget):
    """Pick / tune a software effect; it streams to the keyboard live."""

    def __init__(self, controller: AppController, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller
        self._guard = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        heading = QLabel("Software effects")
        heading.setObjectName("heading")
        root.addWidget(heading)

        body = QHBoxLayout()
        body.setSpacing(16)

        # -- effect list ----------------------------------------------------
        left = QVBoxLayout()
        left.setSpacing(8)
        self.listw = QListWidget()
        self.listw.setFixedWidth(210)
        for effect in EFFECTS.values():
            item = QListWidgetItem(effect.label)
            item.setData(Qt.ItemDataRole.UserRole, effect.name)
            item.setToolTip(effect.description)
            self.listw.addItem(item)
        self.listw.currentItemChanged.connect(self._effect_selected)
        left.addWidget(self.listw)

        self.stop_btn = QPushButton("Stop effect (back to custom)")
        self.stop_btn.clicked.connect(self._stop)
        left.addWidget(self.stop_btn)
        body.addLayout(left)

        # -- designer -------------------------------------------------------
        right = QFrame()
        right.setStyleSheet(
            f"background: {theme.BG_PANEL}; border: 1px solid {theme.BORDER}; border-radius: 8px;"
        )
        form = QVBoxLayout(right)
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(10)

        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        name_row.addWidget(QLabel("Effect name"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name for this design")
        self.name_edit.editingFinished.connect(self._name_edited)
        name_row.addWidget(self.name_edit, 1)
        form.addLayout(name_row)

        self.description = QLabel("Choose an effect on the left.")
        self.description.setObjectName("subheading")
        self.description.setWordWrap(True)
        form.addWidget(self.description)

        self.picker = ColorPicker()
        self.picker.colorChanged.connect(self._color_changed)
        form.addWidget(self.picker)

        secondary_row = QHBoxLayout()
        secondary_row.setSpacing(10)
        sec_label = QLabel("Secondary")
        sec_label.setFixedWidth(86)
        sec_label.setStyleSheet(f"color: {theme.FG_DIM};")
        self.secondary_btn = QPushButton()
        self.secondary_btn.setFixedHeight(30)
        self.secondary_btn.clicked.connect(self._pick_secondary)
        self.color_mode_combo = QComboBox()
        self.color_mode_combo.addItem("Single", 0x00)
        self.color_mode_combo.addItem("Dual", 0x10)
        self.color_mode_combo.addItem("Rainbow", 0x02)
        self.color_mode_combo.currentIndexChanged.connect(self._color_mode_changed)
        secondary_row.addWidget(sec_label)
        secondary_row.addWidget(self.secondary_btn, 1)
        secondary_row.addWidget(self.color_mode_combo)
        form.addLayout(secondary_row)

        self.speed = self._make_slider(form, "Speed")
        self.brightness = self._make_slider(form, "Brightness")
        self.speed[0].sliderReleased.connect(
            lambda: self.controller.update(speed=self.speed[0].value())
        )
        self.brightness[0].sliderReleased.connect(
            lambda: self.controller.update(brightness=self.brightness[0].value())
        )

        pattern_row = QHBoxLayout()
        pattern_row.setSpacing(10)
        pattern_label = QLabel("Pattern")
        pattern_label.setFixedWidth(86)
        pattern_label.setStyleSheet(f"color: {theme.FG_DIM};")
        self.pattern_combo = QComboBox()
        for text, direction in (
            ("Horizontal", "left_to_right"),
            ("Horizontal reverse", "right_to_left"),
            ("Vertical", "top_to_bottom"),
            ("Vertical reverse", "bottom_to_top"),
            ("Clockwise", "cw"),
            ("Counter-clockwise", "ccw"),
        ):
            self.pattern_combo.addItem(text, direction)
        self.pattern_combo.currentIndexChanged.connect(self._pattern_changed)
        pattern_row.addWidget(pattern_label)
        pattern_row.addWidget(self.pattern_combo, 1)
        form.addLayout(pattern_row)

        form.addStretch(1)
        body.addWidget(right, 1)
        root.addLayout(body)
        root.addStretch(1)

        controller.stateChanged.connect(self.refresh)
        self.refresh()

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _make_slider(layout: QVBoxLayout, title: str) -> tuple[QSlider, QLabel]:
        row = QHBoxLayout()
        row.setSpacing(10)
        label = QLabel(title)
        label.setFixedWidth(86)
        label.setStyleSheet(f"color: {theme.FG_DIM};")
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        value = QLabel("0")
        value.setFixedWidth(44)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(label)
        row.addWidget(slider, 1)
        row.addWidget(value)
        layout.addLayout(row)
        slider.valueChanged.connect(lambda v, lbl=value: lbl.setText(f"{v}%"))
        return slider, value

    def refresh(self) -> None:
        if self._guard:
            return
        self._guard = True
        try:
            state = self.controller.state
            if state.mode == "software":
                for row in range(self.listw.count()):
                    item = self.listw.item(row)
                    if item.data(Qt.ItemDataRole.UserRole) == state.effect:
                        if self.listw.currentRow() != row:
                            self.listw.blockSignals(True)
                            self.listw.setCurrentRow(row)
                            self.listw.blockSignals(False)
                        break
            effect = EFFECTS.get(state.effect)
            self.description.setText(effect.description if effect else "")
            self.name_edit.setText(state.effect.replace("-", " ").title())
            self.picker.set_color(state.color1)
            self._set_secondary(state.color2)
            index = self.color_mode_combo.findData(state.color_mode)
            if index >= 0:
                self.color_mode_combo.blockSignals(True)
                self.color_mode_combo.setCurrentIndex(index)
                self.color_mode_combo.blockSignals(False)
            self.speed[0].blockSignals(True)
            self.speed[0].setValue(state.speed)
            self.speed[0].blockSignals(False)
            self.speed[1].setText(f"{state.speed}%")
            self.brightness[0].blockSignals(True)
            self.brightness[0].setValue(state.brightness)
            self.brightness[0].blockSignals(False)
            self.brightness[1].setText(f"{state.brightness}%")
            p = self.pattern_combo.findData(state.direction)
            if p >= 0:
                self.pattern_combo.blockSignals(True)
                self.pattern_combo.setCurrentIndex(p)
                self.pattern_combo.blockSignals(False)
            self.stop_btn.setEnabled(state.mode == "software")
        finally:
            self._guard = False

    def _set_secondary(self, color) -> None:
        self.secondary_btn.setStyleSheet(
            f"background: #{color[0]:02X}{color[1]:02X}{color[2]:02X}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 6px;"
        )

    # -- handlers ----------------------------------------------------------

    def _effect_selected(self, current, _previous=None) -> None:
        if self._guard or current is None:
            return
        name = current.data(Qt.ItemDataRole.UserRole)
        self.controller.update(mode="software", effect=name)

    def _color_changed(self, color) -> None:
        if self._guard:
            return
        self.controller.set_selected_color(color)
        self.controller.update(color1=tuple(color))

    def _pick_secondary(self) -> None:
        from PySide6.QtWidgets import QColorDialog

        state = self.controller.state
        chosen = QColorDialog.getColor(QColor(*state.color2), self, "Secondary color")
        if chosen.isValid():
            color = (chosen.red(), chosen.green(), chosen.blue())
            self.controller.update(color2=color)
            self._set_secondary(color)

    def _color_mode_changed(self) -> None:
        if self._guard:
            return
        self.controller.update(color_mode=self.color_mode_combo.currentData())

    def _pattern_changed(self) -> None:
        if self._guard:
            return
        self.controller.update(direction=self.pattern_combo.currentData())

    def _name_edited(self) -> None:
        # Effect naming happens through presets; keep the field as a label for
        # the design being edited.
        pass

    def _stop(self) -> None:
        self.controller.update(mode="custom", effect="static")

