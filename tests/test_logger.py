import logging
import tempfile
import unittest
from pathlib import Path

from core.logger import get_logger, get_log_file_path, setup_logging, shutdown_logging


class LoggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(shutdown_logging)

    def test_log_file_is_written(self) -> None:
        log_dir = Path(self._tmp.name) / "Folder Log"
        log_file = setup_logging(log_dir, level=logging.INFO, console=False)
        get_logger("uji").info("Pesan uji dengan karakter Indonesia: é ñ")
        shutdown_logging()
        self.assertTrue(log_file.exists())
        self.assertIn("Pesan uji", log_file.read_text(encoding="utf-8"))
        self.assertEqual(get_log_file_path(), log_file)

    def test_setup_is_idempotent(self) -> None:
        log_dir = Path(self._tmp.name)
        setup_logging(log_dir, console=False)
        setup_logging(log_dir, console=False)
        root = logging.getLogger("creatortoolkit")
        self.assertEqual(len(root.handlers), 1)


if __name__ == "__main__":
    unittest.main()
