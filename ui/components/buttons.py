"""Tombol dengan hierarki visual yang konsisten."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget

VARIANTS = ("primary", "secondary", "ghost")


class AppButton(QPushButton):
    """Tombol dengan varian primary, secondary, atau ghost. Gaya diatur di berkas .qss."""

    def __init__(self, text: str, variant: str = "secondary", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        if variant not in VARIANTS:
            raise ValueError(f"Varian tombol tidak dikenal: {variant}")
        self.setProperty("variant", variant)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
