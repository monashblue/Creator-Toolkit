"""Pemilih warna dengan kotak contoh dan kode heksadesimal."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QFrame, QHBoxLayout, QLabel, QWidget

from ui.components.buttons import AppButton


class ColorPicker(QWidget):
    changed = Signal()

    def __init__(self, title: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._color = color
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self._swatch = QFrame()
        self._swatch.setFixedSize(28, 28)
        self._hex = QLabel()
        self._hex.setObjectName("CardText")
        self._button = AppButton("Pilih...", "secondary")
        self._button.setAccessibleName(f"Pilih {title.lower()}")
        self._button.clicked.connect(self._choose)
        layout.addWidget(self._swatch)
        layout.addWidget(self._hex, 1)
        layout.addWidget(self._button)
        self._apply()

    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = color
        self._apply()

    def set_picker_enabled(self, enabled: bool) -> None:
        self._button.setEnabled(enabled)

    def _apply(self) -> None:
        self._swatch.setStyleSheet(
            f"background-color: {self._color}; border: 1px solid #8A8FA3; border-radius: 6px;"
        )
        self._hex.setText(self._color)

    def _choose(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._color), self, self._title)
        if chosen.isValid():
            self.set_color(chosen.name().upper())
            self.changed.emit()
