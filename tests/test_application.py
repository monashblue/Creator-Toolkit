import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

import main as main_module
from app.application import bootstrap
from app.constants import APP_VERSION, get_app_paths
from core.logger import shutdown_logging


class BootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        original_hook = sys.excepthook
        self.addCleanup(setattr, sys, "excepthook", original_hook)
        self.addCleanup(shutdown_logging)

    def test_bootstrap_creates_directories_config_and_log(self) -> None:
        paths = get_app_paths(Path(self._tmp.name) / "data aplikasi")
        context = bootstrap(paths, console_log=False)
        shutdown_logging()
        self.assertTrue(paths.models_dir.is_dir())
        self.assertTrue(paths.cache_dir.is_dir())
        self.assertTrue(paths.config_file.is_file())
        log_file = paths.logs_dir / "creatortoolkit.log"
        self.assertIn("dimulai", log_file.read_text(encoding="utf-8"))
        self.assertEqual(context.config.get("theme"), "light")

    def test_bootstrap_keeps_existing_config(self) -> None:
        paths = get_app_paths(Path(self._tmp.name))
        first = bootstrap(paths, console_log=False)
        first.config.set("theme", "dark")
        second = bootstrap(paths, console_log=False)
        self.assertEqual(second.config.get("theme"), "dark")


class HistoryBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(shutdown_logging)
        self.tmp = Path(self._tmp.name)

    def test_history_is_opened_and_works(self) -> None:
        from core.database import STATUS_SUCCESS, NewEntry

        context = bootstrap(get_app_paths(self.tmp / "a"), console_log=False)
        self.assertIsNotNone(context.history)
        self.addCleanup(context.history.close)
        context.history.add(NewEntry("QR Code Generator", None, "C:/x.png", STATUS_SUCCESS))
        self.assertEqual(context.history.count(), 1)
        self.assertTrue(context.paths.history_db.is_file())

    def test_unusable_history_disables_it_without_crashing(self) -> None:
        from app.constants import ensure_directories

        paths = get_app_paths(self.tmp / "b")
        ensure_directories(paths)
        paths.history_db.mkdir()  # database tidak bisa dibuka karena jalurnya folder
        context = bootstrap(paths, console_log=False)
        self.assertIsNone(context.history)
        self.assertEqual(context.config.get("theme"), "light")  # bagian lain tetap normal


class StartupFailureTests(unittest.TestCase):
    def test_unwritable_data_folder_is_reported_not_raised(self) -> None:
        import os
        from unittest import mock

        from app import application

        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "bukan-folder"
            blocker.write_text("x", encoding="utf-8")
            messages = []
            with mock.patch.dict(os.environ, {"CREATORTOOLKIT_HOME": str(blocker)}):
                code = application.run(error_reporter=lambda title, message: messages.append((title, message)))
        self.assertEqual(code, 1)
        self.assertEqual(len(messages), 1)
        self.assertIn("folder data", messages[0][1])
        self.assertIn(str(blocker), messages[0][1])
        self.assertNotIn("Traceback", messages[0][1])


class MainEntryTests(unittest.TestCase):
    def test_version_option(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main_module.main(["--version"])
        self.assertEqual(code, 0)
        self.assertIn(APP_VERSION, buffer.getvalue())

    def test_check_option_lists_all_packages(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main_module.main(["--check"])
        self.assertEqual(code, 0)
        output = buffer.getvalue()
        for name in ("PySide6", "Pillow", "qrcode", "numpy", "onnxruntime"):
            self.assertIn(name, output)
        self.assertNotIn("rembg", output)


if __name__ == "__main__":
    unittest.main()
