"""Pengelola konfigurasi aplikasi berbasis JSON."""

from __future__ import annotations

import copy
import json
import os
import time
from pathlib import Path
from typing import Any

from core.logger import get_logger

log = get_logger("config")

CONFIG_VERSION = 1
VALID_THEMES = ("light", "dark")
VALID_LANGUAGES = ("id",)


def default_config() -> dict[str, Any]:
    home = Path.home()
    return {
        "config_version": CONFIG_VERSION,
        "language": "id",
        "theme": "light",
        "output_directory": str(home / "Pictures" / "CreatorToolkit"),
        "last_used_directory": str(home),
        "notifications": {
            "enabled": True,
            "on_complete": True,
            "on_error": True,
        },
        "recent_projects_limit": 50,
        "window": {"width": 1200, "height": 800},
    }


MODULE_OUTPUT_KEYS = ("qr.output_directory", "background_remover.output_directory")


def _type_matches(default: Any, value: Any) -> bool:
    """Memeriksa kecocokan tipe nilai dengan nilai bawaan. Bool tidak dianggap int."""
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(default, str):
        return isinstance(value, str)
    return isinstance(value, type(default))


def _sanitize_node(defaults: dict[str, Any], data: dict[str, Any], path: str = "") -> dict[str, Any]:
    """Memastikan setiap kunci bawaan ada dan bertipe benar.

    Nilai bertipe salah dikembalikan ke bawaan dan dicatat di log.
    Kunci tak dikenal tetap dipertahankan.
    """
    result: dict[str, Any] = dict(data)
    for key, default in defaults.items():
        label = f"{path}{key}"
        if key not in result:
            result[key] = copy.deepcopy(default)
        elif isinstance(default, dict):
            if isinstance(result[key], dict):
                result[key] = _sanitize_node(default, result[key], f"{label}.")
            else:
                log.warning("Nilai %s bertipe salah, dikembalikan ke bawaan.", label)
                result[key] = copy.deepcopy(default)
        elif not _type_matches(default, result[key]):
            log.warning("Nilai %s bertipe salah, dikembalikan ke bawaan.", label)
            result[key] = copy.deepcopy(default)
    return result


class ConfigManager:
    """Membaca dan menulis config.json secara aman."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._data: dict[str, Any] = default_config()

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    def load(self) -> dict[str, Any]:
        """Memuat konfigurasi. Berkas rusak dicadangkan lalu diganti nilai bawaan."""
        if not self.path.exists():
            log.info("Berkas konfigurasi belum ada, memakai nilai bawaan.")
            self._data = default_config()
            return self._data
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise ValueError("Isi konfigurasi bukan objek JSON.")
        except (OSError, ValueError) as exc:
            log.warning("Konfigurasi tidak dapat dibaca (%s). Memakai nilai bawaan.", exc)
            self._backup_corrupt_file()
            self._data = default_config()
            return self._data

        self._data = self._sanitize(loaded)
        return self._data

    def save(self) -> None:
        """Menyimpan konfigurasi secara atomik. Berkas sementara dihapus bila gagal."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.path)
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError as exc:
                    log.error("Gagal menghapus berkas sementara %s: %s", tmp_path, exc)

    def get(self, key: str, default: Any = None) -> Any:
        """Mengambil nilai. Kunci bertingkat ditulis dengan titik, misalnya notifications.enabled."""
        node: Any = self._data
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, key: str, value: Any, save: bool = True) -> None:
        """Mengubah nilai. Nilai bertipe salah untuk kunci bawaan dikembalikan ke bawaan."""
        parts = key.split(".")
        node = self._data
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, dict):
                child = {}
                node[part] = child
            node = child
        node[parts[-1]] = value
        self._data = self._sanitize(self._data)
        if save:
            self.save()

    def reset(self, save: bool = True) -> None:
        self._data = default_config()
        if save:
            self.save()

    def _sanitize(self, data: dict[str, Any]) -> dict[str, Any]:
        defaults = default_config()
        data = _sanitize_node(defaults, data)
        if data["theme"] not in VALID_THEMES:
            log.warning("Tema tidak valid, dikembalikan ke bawaan.")
            data["theme"] = defaults["theme"]
        if data["language"] not in VALID_LANGUAGES:
            data["language"] = defaults["language"]
        return data

    def _backup_corrupt_file(self) -> None:
        try:
            backup = self.path.with_name(f"{self.path.name}.corrupt-{int(time.time())}")
            os.replace(self.path, backup)
            log.info("Berkas rusak dicadangkan ke %s", backup)
        except OSError as exc:
            log.error("Gagal mencadangkan berkas rusak: %s", exc)


def set_default_output_directory(config: ConfigManager, directory: str) -> None:
    """Mengubah folder keluaran bawaan dan menghapus folder terakhir tiap modul.

    Dengan begitu semua modul kembali mengikuti folder bawaan yang baru. Disimpan sekali, dapat melempar OSError.
    """
    config.set("output_directory", directory, save=False)
    for key in MODULE_OUTPUT_KEYS:
        config.set(key, "", save=False)
    config.save()
