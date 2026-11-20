"""Inisialisasi aplikasi. Pembuatan jendela Qt ditambahkan pada Milestone M1."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

from app.constants import (
    APP_NAME,
    APP_VERSION,
    AppPaths,
    ensure_directories,
    get_app_paths,
    resource_path,
)
from core.config_manager import ConfigManager
from core.database import HistoryDatabase, HistoryError
from core.logger import get_logger, install_excepthook, setup_logging


@dataclass
class AppContext:
    paths: AppPaths
    config: ConfigManager
    history: HistoryDatabase | None = None  # None bila riwayat tidak dapat dibuka


def bootstrap(paths: AppPaths | None = None, console_log: bool = True) -> AppContext:
    """Menyiapkan direktori data, logging, dan konfigurasi."""
    paths = paths or get_app_paths()
    ensure_directories(paths)
    setup_logging(paths.logs_dir, level=logging.INFO, console=console_log)
    install_excepthook()

    config = ConfigManager(paths.config_file)
    config.load()
    if not paths.config_file.exists():
        config.save()

    history: HistoryDatabase | None = HistoryDatabase(paths.history_db)
    try:
        history.open()
    except HistoryError as exc:
        get_logger("app").error("Riwayat dinonaktifkan: %s", exc)
        history = None

    get_logger("app").info("%s %s dimulai.", APP_NAME, APP_VERSION)
    return AppContext(paths=paths, config=config, history=history)


def _report(message: str) -> None:
    """Menampilkan pesan ke konsol bila tersedia (aplikasi windowed tidak punya stderr)."""
    if sys.stderr is not None:
        print(message, file=sys.stderr)


def _show_fatal(title: str, message: str) -> None:
    """Menampilkan error startup. Memakai dialog bila Qt tersedia, jika tidak ke konsol."""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
        QMessageBox.critical(None, title, message)
    except Exception:  # noqa: BLE001 - Qt mungkin tidak terpasang atau tidak dapat dimulai
        _report(message)


def run(error_reporter=_show_fatal) -> int:
    """Titik masuk aplikasi: menyiapkan fondasi lalu menampilkan jendela utama."""
    try:
        context = bootstrap()
    except OSError:
        location = get_app_paths().local_dir
        error_reporter(
            APP_NAME,
            "Aplikasi tidak dapat menyiapkan folder data pengguna.\n\n"
            f"Pastikan folder berikut dapat ditulis lalu jalankan ulang:\n{location}",
        )
        return 1
    log = get_logger("app")

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        log.error("PySide6 belum terpasang.")
        _report("PySide6 belum terpasang. Jalankan: pip install -r requirements.txt")
        return 1

    from ui.main_window import MainWindow
    from ui.theme import ThemeManager

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    theme = ThemeManager(app, resource_path("ui", "styles"))
    if not theme.apply(str(context.config.get("theme", "light"))):
        log.error("Tema awal gagal dimuat, aplikasi tetap berjalan dengan gaya bawaan.")

    window = MainWindow(context, theme)
    if context.history is not None:
        app.aboutToQuit.connect(context.history.close)
    window.show()
    exit_code = app.exec()
    log.info("Aplikasi ditutup dengan kode %s.", exit_code)
    return exit_code
