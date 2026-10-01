"""Interactive programmatic Everest 60 keyboard rendering.

Draws the real layout (no bitmap), supports selection, rubber-band selection,
row/all selection and drag painting. Colors come from the central lighting
state / live effect preview, so animations render here for free.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget

from ..models.keyboard import (
    KEY_GAP,
    KEYS,
    SIDE_LED_POSITIONS,
)
from . import theme

Color = tuple[int, int, int]

MODE_SELECT = "select"
MODE_PAINT = "paint"


class KeyboardWidget(QWidget):
    """Central keyboard preview / selection surface."""

    selectionChanged = Signal(object)        # list[int]
    sideSelectionChanged = Signal(bool)
    keysPainted = Signal(object)             # list[int] painted this gesture

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(760, 300)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._key_colors: list[Color] = [(0, 0, 0)] * len(KEYS)
        self._side_colors: list[Color] = [(0, 0, 0)] * len(SIDE_LED_POSITIONS)
        self._selected: set[int] = set()
        self._side_selected = False
        self._mode = MODE_SELECT
        self._paint_color: Color = (255, 255, 255)
        self._drag_origin: QPointF | None = None
        self._drag_current: QPointF | None = None
        self._dragging = False
        self._pressed_key: int | None = None
        self._painted_this_gesture: set[int] = set()
        self._hover_key: int | None = None
        self._last_anchor: int | None = None
        self._connected = True
        self._show_side = True

    # -- public API --------------------------------------------------------

    def set_colors(self, keys: list[Color], side: list[Color] | None = None) -> None:
        self._key_colors = list(keys)
        if side is not None:
            self._side_colors = list(side)
        self.update()

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        self.update()

    def set_show_side(self, show: bool) -> None:
        self._show_side = bool(show)
        self.update()

    def selection(self) -> list[int]:
        return sorted(self._selected)

    def set_selection(self, indices) -> None:
        new = {int(i) for i in indices if 0 <= int(i) < len(KEYS)}
        if new != self._selected:
            self._selected = new
            self._side_selected = False
            self.update()
            self.selectionChanged.emit(self.selection())

    def select_all(self) -> None:
        self.set_selection(range(len(KEYS)))

    def select_row(self, row: int) -> None:
        self.set_selection([k.index for k in KEYS if k.row == row])

    def clear_selection(self) -> None:
        if self._selected or self._side_selected:
            self._selected = set()
            self._side_selected = False
            self.update()
            self.selectionChanged.emit([])

    @property
    def side_selected(self) -> bool:
        return self._side_selected

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.setCursor(
            Qt.CursorShape.CrossCursor if mode == MODE_PAINT else Qt.CursorShape.ArrowCursor
        )

    @property
    def mode(self) -> str:
        return self._mode

    def set_paint_color(self, color: Color) -> None:
        self._paint_color = color

    def key_at(self, pos: QPointF) -> int | None:
        unit = self._to_unit(pos)
        if unit is None:
            return None
        ux, uy = unit
        for key in KEYS:
            if key.x <= ux <= key.x + key.w and key.y <= uy <= key.y + key.h:
                return key.index
        return None

    # -- coordinate mapping ------------------------------------------------

    def _content_rect(self):
        # board + padding for the side ring
        return (-1.3, -1.3, 15.0 + 2.6, 5.0 + 2.6)

    def _transform(self):
        x0, y0, w, h = self._content_rect()
        scale = min(self.width() / w, self.height() / h)
        offset_x = (self.width() - w * scale) / 2 - x0 * scale
        offset_y = (self.height() - h * scale) / 2 - y0 * scale
        return scale, offset_x, offset_y

    def _to_px(self, ux: float, uy: float) -> QPointF:
        scale, ox, oy = self._transform()
        return QPointF(ux * scale + ox, uy * scale + oy)

    def _to_unit(self, pos: QPointF) -> tuple[float, float] | None:
        scale, ox, oy = self._transform()
        if scale <= 0:
            return None
        return ((pos.x() - ox) / scale, (pos.y() - oy) / scale)

    # -- painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        scale, _, _ = self._transform()

        # -- side ring -----------------------------------------------------
        led_radius = max(2.5, 0.13 * scale)
        side_pen = QPen(QColor(theme.BORDER))
        side_leds = SIDE_LED_POSITIONS if self._show_side else ()
        for led in side_leds:
            color = self._side_colors[led.index]
            point = self._to_px(led.x, led.y)
            if self._side_selected:
                painter.setBrush(QBrush(QColor(*color)))
                painter.setPen(QPen(QColor(theme.SELECTED_BORDER), 1.4))
            else:
                painter.setBrush(QBrush(QColor(*color)))
                painter.setPen(side_pen)
            painter.drawEllipse(point, led_radius, led_radius)

        # -- rubber band ---------------------------------------------------
        if self._dragging and self._drag_origin is not None and self._drag_current is not None:
            band = QRectF(self._drag_origin, self._drag_current).normalized()
            painter.setPen(QPen(QColor(theme.ACCENT), 1.2))
            painter.setBrush(QColor(0, 168, 255, 32))
            painter.drawRoundedRect(band, 3, 3)

        # -- keys ----------------------------------------------------------
        font = QFont()
        font.setPixelSize(max(6, int(scale * 0.26)))
        font.setWeight(QFont.Weight.Medium)
        painter.setFont(font)

        gap = KEY_GAP * scale
        dimmed = not self._connected

        for key in KEYS:
            top_left = self._to_px(key.x, key.y)
            rect = QRectF(
                top_left.x() + gap / 2,
                top_left.y() + gap / 2,
                key.w * scale - gap,
                key.h * scale - gap,
            )
            color = self._key_colors[key.index]
            qc = QColor(*color)
            if dimmed:
                qc = QColor(int(qc.red() * 0.35), int(qc.green() * 0.35), int(qc.blue() * 0.35))

            # subtle top-light gradient for a physical keycap feel
            gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            lighter = qc.lighter(118)
            gradient.setColorAt(0.0, lighter)
            gradient.setColorAt(0.35, qc)
            gradient.setColorAt(1.0, qc.darker(115))
            painter.setBrush(QBrush(gradient))

            selected = key.index in self._selected
            if selected:
                painter.setPen(QPen(QColor(theme.SELECTED_BORDER), 2.0))
            elif key.index == self._hover_key and self._mode == MODE_SELECT:
                painter.setPen(QPen(QColor("#5A636E"), 1.4))
            else:
                painter.setPen(QPen(QColor(theme.KEY_BORDER), 1.0))
            painter.drawRoundedRect(rect, max(3.0, scale * 0.09), max(3.0, scale * 0.09))

            # label
            label_rect = rect.adjusted(2, 2, -2, -2)
            painter.setPen(QColor(theme.label_color(color)))
            painter.drawText(
                label_rect, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter, key.label
            )

        # -- frame border --------------------------------------------------
        painter.setPen(QPen(QColor(theme.BORDER), 1))
        board = QRectF(self._to_px(0, 0), self._to_px(15, 5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(board, 8, 8)

        painter.end()

    # -- mouse -------------------------------------------------------------

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            self._handle_context(event.position())
            return
        pos = event.position()
        key_index = self.key_at(pos)

        if key_index is None:
            if self._side_hit(pos):
                self._side_selected = True
                self._selected = set()
                self.update()
                self.sideSelectionChanged.emit(True)
                self.selectionChanged.emit([])
            else:
                # start rubber band
                self._drag_origin = pos
                self._drag_current = pos
                self._dragging = True
                self._pressed_key = None
            return

        self._pressed_key = key_index
        if self._mode == MODE_PAINT:
            self._painted_this_gesture = {key_index}
            self.keysPainted.emit([key_index])
        elif event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if key_index in self._selected:
                self._selected.discard(key_index)
            else:
                self._selected.add(key_index)
            self._side_selected = False
            self.update()
            self.selectionChanged.emit(self.selection())
        elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier and self._selected:
            self._add_rect_from_last(key_index)
        else:
            if self._selected != {key_index}:
                self._selected = {key_index}
                self._side_selected = False
                self.update()
                self.selectionChanged.emit(self.selection())
        self._last_anchor = key_index

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        self._hover_key = self.key_at(pos)

        if self._dragging:
            self._drag_current = pos
            self.update()
            return

        if self._pressed_key is not None and event.buttons() & Qt.MouseButton.LeftButton:
            key_index = self._hover_key
            if key_index is not None:
                if self._mode == MODE_PAINT:
                    if key_index not in self._painted_this_gesture:
                        self._painted_this_gesture.add(key_index)
                        self.keysPainted.emit([key_index])
                else:
                    # drag extends a rectangular selection from the anchor
                    anchor = getattr(self, "_last_anchor", self._pressed_key)
                    self._select_rect(anchor, key_index, emit=False)
        else:
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._dragging and self._drag_origin is not None:
            band = QRectF(self._drag_origin, event.position()).normalized()
            scale = self._transform()[0]
            picked = []
            for key in KEYS:
                top_left = self._to_px(key.x, key.y)
                rect = QRectF(top_left.x(), top_left.y(), key.w * scale, key.h * scale)
                if band.intersects(rect):
                    picked.append(key.index)
            if picked:
                modifiers = event.modifiers()
                if modifiers & Qt.KeyboardModifier.ControlModifier:
                    self._selected.update(picked)
                else:
                    self._selected = set(picked)
                self._side_selected = False
                self.selectionChanged.emit(self.selection())
        self._dragging = False
        self._drag_origin = None
        self._drag_current = None
        self._pressed_key = None
        self._painted_this_gesture = set()
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        key_index = self.key_at(event.position())
        if key_index is not None:
            row = KEYS[key_index].row
            self.select_row(row)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_key = None
        self.update()
        super().leaveEvent(event)

    # -- helpers -----------------------------------------------------------

    def _side_hit(self, pos: QPointF) -> bool:
        unit = self._to_unit(pos)
        if unit is None:
            return False
        ux, uy = unit
        for led in SIDE_LED_POSITIONS:
            if math.hypot(ux - led.x, uy - led.y) <= 0.28:
                return True
        return False

    def _select_rect(self, anchor: int, other: int, *, emit: bool = True) -> None:
        a, b = KEYS[anchor], KEYS[other]
        x0, x1 = sorted((a.x, b.x))
        y0, y1 = sorted((a.y, b.y))
        picked = {
            k.index
            for k in KEYS
            if k.x + k.w > x0 - 0.01 and k.x < x1 + 0.01
            and k.y + k.h > y0 - 0.01 and k.y < y1 + 0.01
        }
        if picked != self._selected:
            self._selected = picked
            self._side_selected = False
            self.update()
            if emit:
                self.selectionChanged.emit(self.selection())

    def _add_rect_from_last(self, key_index: int) -> None:
        anchor = self._last_anchor
        if anchor is None or anchor >= len(KEYS):
            anchor = key_index
        self._select_rect(anchor, key_index)

    def _handle_context(self, pos: QPointF) -> None:
        from PySide6.QtWidgets import QMenu

        key_index = self.key_at(pos)
        menu = QMenu(self)
        act_all = menu.addAction("Select all")
        act_clear = menu.addAction("Clear selection")
        menu.addSeparator()
        act_rows = [menu.addAction(f"Select row {row + 1}") for row in range(5)]
        menu.addSeparator()
        act_fill = menu.addAction("Fill selection with current color")

        chosen = menu.exec(self.mapToGlobal(pos.toPoint()))
        if chosen is None:
            return
        if chosen is act_all:
            self.select_all()
        elif chosen is act_clear:
            self.clear_selection()
        elif chosen is act_fill:
            if key_index is not None and key_index not in self._selected:
                self.set_selection([key_index])
            if self._selected:
                self.keysPainted.emit(self.selection())
        else:
            for row, action in enumerate(act_rows):
                if chosen is action:
                    self.select_row(row)
                    break
