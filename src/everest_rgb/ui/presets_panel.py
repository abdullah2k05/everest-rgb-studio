"""Presets page: save / load / import / export lighting configurations."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..models.preset import Preset
from . import theme
from .app_controller import AppController


class PresetsPanel(QWidget):
    def __init__(self, controller: AppController, parent: QWidget | None = None):
        super().__init__(parent)
        self.controller = controller

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        header = QHBoxLayout()
        heading = QLabel("Presets")
        heading.setObjectName("heading")
        header.addWidget(heading)
        header.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("subheading")
        header.addWidget(self.count_label)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(14)

        self.listw = QListWidget()
        self.listw.itemDoubleClicked.connect(lambda _item: self._load())
        body.addWidget(self.listw, 1)

        side = QVBoxLayout()
        side.setSpacing(8)
        side.setContentsMargins(0, 0, 0, 0)

        name_label = QLabel("Preset name")
        name_label.setStyleSheet(f"color: {theme.FG_DIM};")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Coding")
        side.addWidget(name_label)
        side.addWidget(self.name_edit)

        self.load_btn = QPushButton("Load")
        self.load_btn.setObjectName("primary")
        self.load_btn.clicked.connect(self._load)

        self.save_btn = QPushButton("Save current as…")
        self.save_btn.clicked.connect(self._save_as)

        self.duplicate_btn = QPushButton("Duplicate")
        self.duplicate_btn.clicked.connect(self._duplicate)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.clicked.connect(self._delete)

        self.import_btn = QPushButton("Import…")
        self.import_btn.clicked.connect(self._import)

        self.export_btn = QPushButton("Export…")
        self.export_btn.clicked.connect(self._export)

        for button in (
            self.load_btn,
            self.save_btn,
            self.duplicate_btn,
            self.delete_btn,
            self.import_btn,
            self.export_btn,
        ):
            side.addWidget(button)
        side.addStretch(1)
        body.addLayout(side)
        root.addLayout(body)

        hint = QLabel(
            "Built-in presets are read-only; saving one creates your own copy. "
            "Double-click to load."
        )
        hint.setObjectName("subheading")
        root.addWidget(hint)

        controller.presetsChanged.connect(self.refresh)
        self.refresh()

    # -- helpers -----------------------------------------------------------

    def refresh(self) -> None:
        selected_name = self._selected_preset().name if self._selected_preset() else None
        self.listw.clear()
        presets = self.controller.list_presets()
        for preset in presets:
            origin = "built-in" if preset.builtin else "user"
            item = QListWidgetItem(f"{preset.name}   ·   {origin}")
            item.setData(Qt.ItemDataRole.UserRole, preset.name)
            item.setToolTip(f"{preset.summary}\n{preset.description}".strip())
            self.listw.addItem(item)
            if selected_name and preset.name == selected_name:
                self.listw.setCurrentItem(item)
        self.count_label.setText(f"{len(presets)} presets")

    def _selected_preset(self) -> Preset | None:
        item = self.listw.currentItem()
        if item is None:
            return None
        name = item.data(Qt.ItemDataRole.UserRole)
        return self.controller.store.load(name)

    # -- actions -----------------------------------------------------------

    def _load(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            self.controller.message.emit("Select a preset first", "warn")
            return
        self.controller.load_preset(preset)

    def _save_as(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.controller.message.emit("Enter a preset name first", "warn")
            return
        if self.controller.store.load(name) is not None:
            answer = QMessageBox.question(
                self,
                "Overwrite preset",
                f"Preset '{name}' exists. Overwrite it?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.controller.save_preset(name)
        self.name_edit.clear()
        self.refresh()

    def _duplicate(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            return
        self.controller.duplicate_preset(preset)
        self.refresh()

    def _delete(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            return
        if preset.builtin:
            self.controller.message.emit(
                "Built-in presets cannot be deleted (duplicate instead)", "warn"
            )
            return
        answer = QMessageBox.question(
            self, "Delete preset", f"Delete preset '{preset.name}'?"
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.delete_preset(preset)
            self.refresh()

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import preset", str(Path.home()), "Preset files (*.json)"
        )
        if not path:
            return
        try:
            self.controller.import_preset(Path(path))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Import failed", str(exc))
        self.refresh()

    def _export(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            self.controller.message.emit("Select a preset to export", "warn")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export preset",
            str(Path.home() / f"{preset.name.replace(' ', '_')}.json"),
            "Preset files (*.json)",
        )
        if not path:
            return
        try:
            self.controller.export_preset(preset, Path(path))
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
