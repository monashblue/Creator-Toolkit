"""Sistem logging teknis. Log ditulis ke folder data lokal pengguna."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

ROOT_LOGGER_NAME = "creatortoolkit"
LOG_FILE_NAME = "creatortoolkit.log"
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 3
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

_log_file_path: Path | None = None


def setup_logging(log_dir: Path, level: int = logging.INFO, console: bool = True) -> Path:
    """Menyiapkan logging. Aman dipanggil berulang kali.

    Mengembalikan jalur berkas log aktif.
    """
    global _log_file_path
    shutdown_logging()

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILE_NAME

    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(_FORMAT)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Pada aplikasi windowed hasil PyInstaller, sys.stderr dapat bernilai None.
    if console and sys.stderr is not None:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    _log_file_path = log_file
    return log_file


def shutdown_logging() -> None:
    """Menutup dan melepas semua handler agar berkas log tidak terkunci."""
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(logger.handlers):
        handler.flush()
        handler.close()
        logger.removeHandler(handler)


def get_logger(name: str | None = None) -> logging.Logger:
    """Mengambil logger turunan dari logger utama aplikasi."""
    if not name:
        return logging.getLogger(ROOT_LOGGER_NAME)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")


def get_log_file_path() -> Path | None:
    """Jalur berkas log aktif, atau None bila logging belum disiapkan."""
    return _log_file_path


def install_excepthook() -> None:
    """Mencatat error yang tidak tertangani ke log tanpa menampilkan stack trace."""
    logger = get_logger("excepthook")

    def _hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical("Error tidak tertangani", exc_info=(exc_type, exc_value, exc_tb))
        if sys.stderr is not None:
            location = _log_file_path if _log_file_path else "folder log aplikasi"
            print(
                "Terjadi kesalahan tak terduga. Rincian teknis tersimpan di: "
                f"{location}",
                file=sys.stderr,
            )

    sys.excepthook = _hook
