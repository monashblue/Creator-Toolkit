"""Riwayat pemrosesan berbasis SQLite.

Hanya menyimpan nama alat, jalur berkas, status, dan waktu. Tidak menyimpan data gambar,
isi QR, kata sandi, atau data biner apa pun.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from core.logger import get_logger
from core.tasks import UserMessageError

log = get_logger("database")

SCHEMA_VERSION = 1
MAX_ROWS = 2000
MAX_TEXT = 4096
STATUS_SUCCESS = "berhasil"
STATUS_FAILED = "gagal"
VALID_STATUSES = (STATUS_SUCCESS, STATUS_FAILED)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name   TEXT NOT NULL,
    input_file  TEXT,
    output_file TEXT,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL
)
"""


class HistoryError(UserMessageError):
    """Kesalahan riwayat dengan pesan Indonesia yang aman ditampilkan."""


@dataclass(frozen=True)
class NewEntry:
    tool_name: str
    input_file: str | None
    output_file: str | None
    status: str


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    tool_name: str
    input_file: str | None
    output_file: str | None
    status: str
    created_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validate(entry: NewEntry) -> None:
    if not isinstance(entry.tool_name, str) or not entry.tool_name.strip() or len(entry.tool_name) > 200:
        raise ValueError("tool_name harus berupa teks tidak kosong (maksimal 200 karakter).")
    if entry.status not in VALID_STATUSES:
        raise ValueError(f"status harus salah satu dari {VALID_STATUSES}.")
    for name in ("input_file", "output_file"):
        value = getattr(entry, name)
        if value is not None and (not isinstance(value, str) or len(value) > MAX_TEXT):
            raise ValueError(f"{name} harus berupa teks (maksimal {MAX_TEXT} karakter) atau None.")


class HistoryDatabase:
    """Akses riwayat yang aman antar thread (satu koneksi dengan kunci)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------ membuka dan menutup

    def open(self) -> None:
        """Membuka database. Berkas rusak dicadangkan lalu dibuat ulang."""
        with self._lock:
            if self._conn is not None:
                return
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._conn = self._initialize()
            except HistoryError:
                raise
            except sqlite3.OperationalError as exc:
                log.error("Riwayat tidak dapat dibuka: %s", exc)
                raise HistoryError(
                    "Riwayat tidak dapat dibuka. Periksa izin folder data aplikasi. Fitur lain tetap berfungsi."
                ) from exc
            except sqlite3.DatabaseError as exc:
                log.warning("Berkas riwayat rusak (%s), dicadangkan dan dibuat ulang.", exc)
                self._recover()
            except OSError as exc:
                log.error("Folder riwayat tidak dapat dibuat: %s", exc)
                raise HistoryError("Folder untuk menyimpan riwayat tidak dapat dibuat.") from exc

    def _initialize(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=5.0, check_same_thread=False)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise HistoryError("Riwayat dibuat oleh versi aplikasi yang lebih baru dan tidak dapat dibaca.")
            with conn:
                conn.execute(_CREATE_TABLE)
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            return conn
        except BaseException:
            conn.close()
            raise

    def _recover(self) -> None:
        try:
            backup = self.path.with_name(f"{self.path.name}.corrupt-{int(time.time())}")
            self.path.replace(backup)
            log.info("Riwayat rusak dicadangkan ke %s", backup)
            self._conn = self._initialize()
        except (OSError, sqlite3.Error) as exc:
            log.error("Gagal memulihkan riwayat: %s", exc)
            raise HistoryError("Riwayat rusak dan tidak dapat dipulihkan. Fitur lain tetap berfungsi.") from exc

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None

    # ------------------------------------------------------------ operasi

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise HistoryError("Riwayat belum dibuka.")
        return self._conn

    def add_many(self, entries: Iterable[NewEntry], created_at: datetime | None = None) -> int:
        """Menambahkan beberapa catatan dalam satu transaksi, lalu memangkas yang terlama. Mengembalikan jumlahnya."""
        batch = list(entries)
        for entry in batch:
            _validate(entry)
        if not batch:
            return 0
        stamp = (created_at or _now()).astimezone(timezone.utc).isoformat(timespec="seconds")
        rows = [(e.tool_name, e.input_file, e.output_file, e.status, stamp) for e in batch]
        with self._lock:
            conn = self._connection()
            try:
                with conn:
                    conn.executemany(
                        "INSERT INTO history (tool_name, input_file, output_file, status, created_at) VALUES (?, ?, ?, ?, ?)",
                        rows,
                    )
                    conn.execute(
                        "DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT ?)",
                        (MAX_ROWS,),
                    )
            except sqlite3.Error as exc:
                log.error("Gagal menulis riwayat: %s", exc)
                raise HistoryError("Riwayat tidak dapat disimpan.") from exc
        return len(rows)

    def add(self, entry: NewEntry, created_at: datetime | None = None) -> None:
        self.add_many([entry], created_at)

    def recent(
        self, limit: int = 50, tool_name: str | None = None, status: str | None = None
    ) -> list[HistoryEntry]:
        """Catatan terbaru lebih dulu."""
        clauses, params = [], []
        if tool_name is not None:
            clauses.append("tool_name = ?")
            params.append(tool_name)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, int(limit)))
        with self._lock:
            conn = self._connection()
            try:
                rows = conn.execute(
                    f"SELECT id, tool_name, input_file, output_file, status, created_at FROM history {where} "
                    "ORDER BY id DESC LIMIT ?",
                    params,
                ).fetchall()
            except sqlite3.Error as exc:
                log.error("Gagal membaca riwayat: %s", exc)
                raise HistoryError("Riwayat tidak dapat dibaca.") from exc
        return [
            HistoryEntry(row[0], row[1], row[2], row[3], row[4], datetime.fromisoformat(row[5])) for row in rows
        ]

    def count(self) -> int:
        with self._lock:
            conn = self._connection()
            try:
                return int(conn.execute("SELECT COUNT(*) FROM history").fetchone()[0])
            except sqlite3.Error as exc:
                raise HistoryError("Riwayat tidak dapat dibaca.") from exc
