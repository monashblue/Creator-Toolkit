"""Pola worker Qt: menjalankan fungsi pekerjaan di QThread dan melaporkan lewat sinyal."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

from core.logger import get_logger
from core.tasks import CancelToken, OperationCancelled, TaskContext, UserMessageError

log = get_logger("worker")

TaskFunction = Callable[[TaskContext], Any]


class TaskWorker(QObject):
    """Dijalankan di thread terpisah. Selalu memancarkan finished di akhir."""

    progress = Signal(int, str)
    item_done = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(self, function: TaskFunction, token: CancelToken) -> None:
        super().__init__()
        self._function = function
        self.token = token

    @Slot()
    def run(self) -> None:
        context = TaskContext(
            token=self.token,
            on_progress=lambda percent, message: self.progress.emit(percent, message),
            on_item=lambda payload: self.item_done.emit(payload),
        )
        try:
            result = self._function(context)
        except OperationCancelled:
            self.cancelled.emit()
        except UserMessageError as exc:
            log.warning("Pekerjaan gagal: %s", exc)
            self.failed.emit(str(exc))
        except MemoryError:
            log.exception("Memori habis saat menjalankan pekerjaan.")
            self.failed.emit("Memori komputer tidak cukup. Tutup aplikasi lain atau gunakan gambar yang lebih kecil.")
        except Exception:
            log.exception("Kesalahan tak terduga pada pekerjaan latar belakang.")
            self.failed.emit("Terjadi kesalahan tak terduga. Rincian teknis tersimpan di berkas log.")
        else:
            self.succeeded.emit(result)
        finally:
            self.finished.emit()


class TaskRunner(QObject):
    """Mengelola satu pekerjaan latar belakang pada satu waktu, termasuk pembersihan thread."""

    progress = Signal(int, str)
    item_done = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: TaskWorker | None = None
        self._token: CancelToken | None = None

    def is_running(self) -> bool:
        return self._thread is not None

    def start(self, function: TaskFunction) -> bool:
        if self._thread is not None:
            return False
        token = CancelToken()
        thread = QThread()
        worker = TaskWorker(function, token)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.item_done.connect(self._on_item)
        worker.succeeded.connect(self._on_succeeded)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._on_thread_finished)

        self._thread, self._worker, self._token = thread, worker, token
        thread.start()
        return True

    def cancel(self) -> None:
        if self._token is not None:
            self._token.cancel()

    def shutdown(self, timeout_ms: int = 30000) -> None:
        """Membatalkan pekerjaan dan menunggu thread selesai. Dipakai saat aplikasi ditutup.

        Satu inferensi yang sedang berjalan tidak dapat diputus, jadi batas tunggu dibuat longgar agar
        QThread tidak dihancurkan saat masih berjalan.
        """
        self.cancel()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(timeout_ms)

    @Slot(int, str)
    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.emit(percent, message)

    @Slot(object)
    def _on_item(self, payload: Any) -> None:
        self.item_done.emit(payload)

    @Slot(object)
    def _on_succeeded(self, result: Any) -> None:
        self.succeeded.emit(result)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.failed.emit(message)

    @Slot()
    def _on_cancelled(self) -> None:
        self.cancelled.emit()

    @Slot()
    def _on_thread_finished(self) -> None:
        thread, worker = self._thread, self._worker
        self._thread = self._worker = self._token = None
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            thread.deleteLater()
        self.finished.emit()
