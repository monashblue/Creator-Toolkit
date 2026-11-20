"""Konstanta aplikasi dan penentuan jalur data pengguna."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Creator Toolkit"
APP_DIR_NAME = "CreatorToolkit"
APP_TAGLINE = "Your Everyday Creative Companion"
APP_VERSION = "0.1.0"
APP_LICENSE = "MIT"
MIN_PYTHON = (3, 12)

# Variabel lingkungan untuk memindahkan seluruh data aplikasi (berguna untuk pengujian).
ENV_HOME_OVERRIDE = "CREATORTOOLKIT_HOME"


@dataclass(frozen=True)
class AppPaths:
    """Kumpulan jalur data yang dapat diubah oleh aplikasi."""

    local_dir: Path
    roaming_dir: Path

    @property
    def models_dir(self) -> Path:
        return self.local_dir / "models"

    @property
    def cache_dir(self) -> Path:
        return self.local_dir / "cache"

    @property
    def logs_dir(self) -> Path:
        return self.local_dir / "logs"

    @property
    def config_file(self) -> Path:
        return self.local_dir / "config.json"

    @property
    def history_db(self) -> Path:
        return self.roaming_dir / "history.db"

    def all_directories(self) -> list[Path]:
        return [
            self.local_dir,
            self.roaming_dir,
            self.models_dir,
            self.cache_dir,
            self.logs_dir,
        ]


def get_app_paths(base_override: Path | None = None) -> AppPaths:
    """Menentukan jalur data pengguna.

    Urutan prioritas:
    1. Parameter base_override.
    2. Variabel lingkungan CREATORTOOLKIT_HOME.
    3. Windows: %LOCALAPPDATA%/CreatorToolkit dan %APPDATA%/CreatorToolkit.
    4. Sistem lain (hanya untuk pengembangan): folder XDG atau home pengguna.
    """
    override = base_override
    if override is None and os.environ.get(ENV_HOME_OVERRIDE):
        override = Path(os.environ[ENV_HOME_OVERRIDE])
    if override is not None:
        override = Path(override)
        return AppPaths(local_dir=override / "local", roaming_dir=override / "roaming")

    home = Path.home()
    if sys.platform.startswith("win"):
        local_root = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        roaming_root = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
    else:
        local_root = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
        roaming_root = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return AppPaths(
        local_dir=local_root / APP_DIR_NAME,
        roaming_dir=roaming_root / APP_DIR_NAME,
    )


def ensure_directories(paths: AppPaths) -> None:
    """Membuat seluruh direktori data bila belum ada."""
    for directory in paths.all_directories():
        directory.mkdir(parents=True, exist_ok=True)


def resource_path(*parts: str) -> Path:
    """Jalur sumber daya aplikasi, baik saat dijalankan dari kode maupun dari hasil PyInstaller."""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root.joinpath(*parts)
