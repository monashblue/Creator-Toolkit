"""Dasar pekerjaan latar belakang tanpa Qt: pembatalan, laporan progres, dan error ramah pengguna."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable


class UserMessageError(Exception):
    """Dasar semua error yang pesannya aman dan ditujukan untuk ditampilkan kepada pengguna."""


class OperationCancelled(Exception):
    """Dilempar saat pekerjaan dibatalkan oleh pengguna."""


class CancelToken:
    """Penanda pembatalan yang aman dipakai lintas thread."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise OperationCancelled()


@dataclass
class TaskContext:
    """Konteks yang diterima fungsi pekerjaan: token pembatalan dan jalur pelaporan."""

    token: CancelToken = field(default_factory=CancelToken)
    on_progress: Callable[[int, str], None] | None = None
    on_item: Callable[[Any], None] | None = None

    def report(self, percent: float, message: str = "") -> None:
        if self.on_progress is not None:
            self.on_progress(max(0, min(100, int(percent))), message)

    def emit_item(self, payload: Any) -> None:
        if self.on_item is not None:
            self.on_item(payload)

    def check_cancel(self) -> None:
        self.token.raise_if_cancelled()
