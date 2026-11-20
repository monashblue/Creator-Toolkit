import tempfile
import unittest
from pathlib import Path

from app.constants import ensure_directories, get_app_paths


class PathsTests(unittest.TestCase):
    def test_override_and_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = get_app_paths(Path(tmp) / "data pengguna")
            ensure_directories(paths)
            for directory in (paths.models_dir, paths.cache_dir, paths.logs_dir):
                self.assertTrue(directory.is_dir())
            self.assertEqual(paths.config_file.name, "config.json")
            self.assertEqual(paths.history_db.name, "history.db")
            self.assertNotEqual(paths.local_dir, paths.roaming_dir)


if __name__ == "__main__":
    unittest.main()
