import json
import tempfile
import unittest
from pathlib import Path

from core.config_manager import MODULE_OUTPUT_KEYS, ConfigManager, default_config, set_default_output_directory


class ConfigManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "sub folder" / "config.json"

    def test_defaults_when_file_missing(self) -> None:
        manager = ConfigManager(self.path)
        data = manager.load()
        self.assertEqual(data["theme"], "light")
        self.assertEqual(data["language"], "id")

    def test_persistence_roundtrip(self) -> None:
        manager = ConfigManager(self.path)
        manager.load()
        manager.set("theme", "dark")
        manager.set("notifications.on_complete", False)
        manager.set("last_used_directory", "C:/Pengguna/Ünïcode Folder")

        other = ConfigManager(self.path)
        other.load()
        self.assertEqual(other.get("theme"), "dark")
        self.assertFalse(other.get("notifications.on_complete"))
        self.assertTrue(other.get("notifications.enabled"))
        self.assertEqual(other.get("last_used_directory"), "C:/Pengguna/Ünïcode Folder")

    def test_corrupt_file_is_backed_up(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{ ini bukan json", encoding="utf-8")
        manager = ConfigManager(self.path)
        data = manager.load()
        self.assertEqual(data["theme"], default_config()["theme"])
        backups = list(self.path.parent.glob("config.json.corrupt-*"))
        self.assertEqual(len(backups), 1)

    def test_invalid_theme_falls_back(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"theme": "neon"}), encoding="utf-8")
        manager = ConfigManager(self.path)
        manager.load()
        self.assertEqual(manager.get("theme"), "light")

    def test_new_default_keys_are_filled(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        manager = ConfigManager(self.path)
        manager.load()
        self.assertEqual(manager.get("window.width"), 1200)

    def test_reset(self) -> None:
        manager = ConfigManager(self.path)
        manager.load()
        manager.set("theme", "dark")
        manager.reset()
        self.assertEqual(manager.get("theme"), "light")

    def test_wrong_types_fall_back_to_defaults(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps(
                {
                    "notifications": "ya",
                    "window": 5,
                    "output_directory": 123,
                    "recent_projects_limit": True,
                    "custom_key": "dipertahankan",
                }
            ),
            encoding="utf-8",
        )
        manager = ConfigManager(self.path)
        manager.load()
        defaults = default_config()
        self.assertEqual(manager.get("notifications"), defaults["notifications"])
        self.assertEqual(manager.get("window.width"), 1200)
        self.assertEqual(manager.get("output_directory"), defaults["output_directory"])
        self.assertEqual(manager.get("recent_projects_limit"), 50)
        self.assertEqual(manager.get("custom_key"), "dipertahankan")

    def test_set_parent_key_with_wrong_type_is_repaired(self) -> None:
        manager = ConfigManager(self.path)
        manager.load()
        manager.set("notifications", True)
        self.assertTrue(manager.get("notifications.enabled"))
        reloaded = ConfigManager(self.path)
        reloaded.load()
        self.assertTrue(reloaded.get("notifications.on_error"))

    def test_failed_save_leaves_no_temp_file(self) -> None:
        manager = ConfigManager(self.path)
        manager.load()
        manager.data["tidak_bisa_diserialisasi"] = object()
        with self.assertRaises(TypeError):
            manager.save()
        self.assertFalse(self.path.with_name("config.json.tmp").exists())

    def test_new_default_folder_clears_module_folders(self) -> None:
        manager = ConfigManager(self.path)
        manager.load()
        manager.set("qr.output_directory", "D:/lama-qr")
        manager.set("background_remover.output_directory", "D:/lama-bg")
        set_default_output_directory(manager, "E:/folder baru ñ")

        reloaded = ConfigManager(self.path)
        reloaded.load()
        self.assertEqual(reloaded.get("output_directory"), "E:/folder baru ñ")
        for key in MODULE_OUTPUT_KEYS:
            self.assertEqual(reloaded.get(key), "")
            # cara halaman modul menentukan folder awalnya
            self.assertEqual(reloaded.get(key) or reloaded.get("output_directory"), "E:/folder baru ñ")

    def test_new_default_folder_failure_raises_oserror(self) -> None:
        from unittest import mock

        manager = ConfigManager(self.path)
        manager.load()
        with mock.patch("os.replace", side_effect=PermissionError("terkunci")):
            with self.assertRaises(OSError):
                set_default_output_directory(manager, "E:/x")
        self.assertFalse(self.path.with_name("config.json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
