"""Daftar berkas yang baru diproses."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.components.buttons import AppButton
from ui.recent_model import KIND_FAILED, KIND_MISSING, RowInfo

_STATUS_OBJECT_NAMES = {KIND_FAILED: "ErrorText", KIND_MISSING: "WarningText"}


class RecentList(QWidget):
    """Baris riwayat. Bila interactive, tiap baris punya tombol Buka folder (nonaktif bila folder hilang)."""

    open_requested = Signal(str)

    def __init__(self, interactive: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RecentListBody")
        self._interactive = interactive
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

    def set_rows(self, rows: list[RowInfo]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for row in rows:
            self._layout.addWidget(self._build_row(row))
        self._layout.addStretch(1)

    def _build_row(self, row: RowInfo) -> QWidget:
        frame = QFrame()
        frame.setObjectName("RecentRow")
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(row.title)
        title.setObjectName("CardTitle")
        title.setToolTip(row.path)
        detail = QLabel(f"{row.tool}  |  {row.detail}" if row.detail else row.tool)
        detail.setObjectName("Muted")
        detail.setToolTip(row.detail)
        text.addWidget(title)
        text.addWidget(detail)
        layout.addLayout(text, 1)

        meta = QVBoxLayout()
        meta.setSpacing(2)
        when = QLabel(row.when)
        when.setObjectName("Muted")
        when.setAlignment(Qt.AlignmentFlag.AlignRight)
        status = QLabel(row.status_text)
        status.setObjectName(_STATUS_OBJECT_NAMES.get(row.status_kind, "Muted"))
        status.setAlignment(Qt.AlignmentFlag.AlignRight)
        meta.addWidget(when)
        meta.addWidget(status)
        layout.addLayout(meta)

        if self._interactive:
            button = AppButton("Buka folder", "ghost")
            button.setEnabled(row.can_open)
            button.setToolTip(str(row.folder) if row.can_open else "Folder tidak ditemukan")
            if row.folder is not None:
                button.clicked.connect(lambda checked=False, folder=str(row.folder): self.open_requested.emit(folder))
            layout.addWidget(button)
        return frame
