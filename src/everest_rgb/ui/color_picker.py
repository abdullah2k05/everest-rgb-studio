"""Color picker: swatch, HEX, RGB and HSV editing, copy/paste."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme

Color = tuple[int, int, int]


class _ChannelSlider(QWidget):
    """Label + slider + value readout for one color channel."""

    changed = Signal(int)

    def __init__(self, name: str, maximum: int = 255, parent: QWidget | None = None):
        super().__init__(parent)
        self._maximum = maximum
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(name)
        label.setFixedWidth(58)
        label.setProperty("class", "dim")
        label.setStyleSheet(f"color: {theme.FG_DIM};")

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, maximum)
        self.value_label = QLabel("0")
        self.value_label.setFixedWidth(34)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.value_label.setStyleSheet(f"color: {theme.FG_DIM};")

        self.slider.valueChanged.connect(self._on_change)
        layout.addWidget(label)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.value_label)

    def _on_change(self, value: int) -> None:
        self.value_label.setText(str(value))
        self.changed.emit(value)

    def value(self) -> int:
        return self.slider.value()

    def set_value(self, value: int) -> None:
        value = max(0, min(self._maximum, int(value)))
        if self.slider.value() != value:
            self.slider.blockSignals(True)
            self.slider.setValue(value)
            self.slider.blockSignals(False)
        self.value_label.setText(str(value))


class ColorPicker(QWidget):
    """Emits ``colorChanged((r, g, b))`` for every edit."""

    colorChanged = Signal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._color: Color = (255, 255, 255)
        self._guard = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # -- swatch + hex -------------------------------------------------
        top = QHBoxLayout()
        top.setSpacing(10)

        self.swatch = QFrame()
        self.swatch.setFixedSize(54, 34)
        self.swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swatch.setStyleSheet(
            f"background: {theme.ACCENT}; border: 1px solid {theme.BORDER}; border-radius: 6px;"
        )
        self.swatch.mousePressEvent = self._pick_dialog

        self.hex_input = QLineEdit("#FFFFFF")
        self.hex_input.setMaxLength(7)
        self.hex_input.setFixedWidth(92)
        self.hex_input.setInputMask(">\\#HHHHHH;" )
        self.hex_input.setPlaceholderText("#RRGGBB")
        self.hex_input.editingFinished.connect(self._hex_edited)

        copy_btn = QPushButton("Copy")
        copy_btn.setObjectName("tool")
        copy_btn.setToolTip("Copy color to clipboard (Ctrl+C)")
        copy_btn.clicked.connect(self._copy)

        paste_btn = QPushButton("Paste")
        paste_btn.setObjectName("tool")
        paste_btn.setToolTip("Paste color from clipboard (Ctrl+V)")
        paste_btn.clicked.connect(self._paste)

        top.addWidget(self.swatch)
        top.addWidget(self.hex_input)
        top.addStretch(1)
        top.addWidget(copy_btn)
        top.addWidget(paste_btn)
        root.addLayout(top)

        # -- RGB / HSV tabs ------------------------------------------------
        self.tabs = QTabWidget()
        rgb_page = QWidget()
        rgb_layout = QVBoxLayout(rgb_page)
        rgb_layout.setContentsMargins(4, 8, 4, 4)
        self.r = _ChannelSlider("Red")
        self.g = _ChannelSlider("Green")
        self.b = _ChannelSlider("Blue")
        for slider in (self.r, self.g, self.b):
            rgb_layout.addWidget(slider)
            slider.changed.connect(self._from_rgb)
        rgb_layout.addStretch(1)

        hsv_page = QWidget()
        hsv_layout = QVBoxLayout(hsv_page)
        hsv_layout.setContentsMargins(4, 8, 4, 4)
        self.h = _ChannelSlider("Hue", 359)
        self.s = _ChannelSlider("Saturation")
        self.v = _ChannelSlider("Value")
        for slider in (self.h, self.s, self.v):
            hsv_layout.addWidget(slider)
            slider.changed.connect(self._from_hsv)
        hsv_layout.addStretch(1)

        self.tabs.addTab(rgb_page, "RGB")
        self.tabs.addTab(hsv_page, "HSV")
        root.addWidget(self.tabs)

        self.set_color((255, 255, 255))

    # -- public API --------------------------------------------------------

    def color(self) -> Color:
        return self._color

    def set_color(self, color: Color, *, emit: bool = False) -> None:
        color = (
            max(0, min(255, int(color[0]))),
            max(0, min(255, int(color[1]))),
            max(0, min(255, int(color[2]))),
        )
        self._color = color
        self._guard = True
        try:
            r, g, b = color
            self.r.set_value(r)
            self.g.set_value(g)
            self.b.set_value(b)
            qc = QColor(r, g, b)
            self.h.set_value(qc.hue() if qc.hue() >= 0 else 0)
            self.s.set_value(round(qc.saturationF() * 100))
            self.v.set_value(round(qc.valueF() * 100))
            self.hex_input.setText(f"#{r:02X}{g:02X}{b:02X}")
            self.swatch.setStyleSheet(
                f"background: #{r:02X}{g:02X}{b:02X}; "
                f"border: 1px solid {theme.BORDER}; border-radius: 6px;"
            )
        finally:
            self._guard = False
        if emit:
            self.colorChanged.emit(color)

    # -- edit paths --------------------------------------------------------

    def _emit(self) -> None:
        if self._guard:
            return
        self.colorChanged.emit(self._color)

    def _from_rgb(self) -> None:
        if self._guard:
            return
        color = (self.r.value(), self.g.value(), self.b.value())
        self._color = color
        self._guard = True
        try:
            qc = QColor(*color)
            self.h.set_value(qc.hue() if qc.hue() >= 0 else 0)
            self.s.set_value(round(qc.saturationF() * 100))
            self.v.set_value(round(qc.valueF() * 100))
            self.hex_input.setText(f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}")
            self.swatch.setStyleSheet(
                f"background: #{color[0]:02X}{color[1]:02X}{color[2]:02X}; "
                f"border: 1px solid {theme.BORDER}; border-radius: 6px;"
            )
        finally:
            self._guard = False
        self._emit()

    def _from_hsv(self) -> None:
        if self._guard:
            return
        qc = QColor.fromHsvF(
            (self.h.value() % 360) / 360.0,
            self.s.value() / 100.0,
            self.v.value() / 100.0,
        )
        color = (qc.red(), qc.green(), qc.blue())
        self._color = color
        self._guard = True
        try:
            self.r.set_value(color[0])
            self.g.set_value(color[1])
            self.b.set_value(color[2])
            self.hex_input.setText(f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}")
            self.swatch.setStyleSheet(
                f"background: #{color[0]:02X}{color[1]:02X}{color[2]:02X}; "
                f"border: 1px solid {theme.BORDER}; border-radius: 6px;"
            )
        finally:
            self._guard = False
        self._emit()

    def _hex_edited(self) -> None:
        text = self.hex_input.text().strip()
        if not text:
            self.hex_input.setText(f"#{self._color[0]:02X}{self._color[1]:02X}{self._color[2]:02X}")
            return
        if not text.startswith("#"):
            text = "#" + text
        try:
            qc = QColor(text)
        except Exception:
            qc = QColor()
        if not qc.isValid():
            self.hex_input.setText(
                f"#{self._color[0]:02X}{self._color[1]:02X}{self._color[2]:02X}"
            )
            return
        self.set_color((qc.red(), qc.green(), qc.blue()))
        self._emit()

    def _pick_dialog(self, _event=None) -> None:
        initial = QColor(*self._color)
        chosen = QColorDialog.getColor(initial, self, "Choose color")
        if chosen.isValid():
            self.set_color((chosen.red(), chosen.green(), chosen.blue()))
            self._emit()

    def _copy(self) -> None:
        text = f"#{self._color[0]:02X}{self._color[1]:02X}{self._color[2]:02X}"
        QGuiApplication.clipboard().setText(text)

    def _paste(self) -> None:
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            return
        if not text.startswith("#"):
            text = "#" + text
        qc = QColor(text)
        if qc.isValid():
            self.set_color((qc.red(), qc.green(), qc.blue()))
            self._emit()
