import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.database import STATUS_FAILED, STATUS_SUCCESS, HistoryDatabase, HistoryEntry, NewEntry
from ui import recent_model as rm

WIB = timezone(timedelta(hours=7))


def make(output=None, input_file=None, status=STATUS_SUCCESS, when=None, entry_id=1) -> HistoryEntry:
    return HistoryEntry(entry_id, "Background Remover", input_file, output, status, when or datetime(2026, 11, 19, 7, 5, tzinfo=timezone.utc))


class TimeFormatTests(unittest.TestCase):
    NOW = datetime(2026, 11, 19, 12, 0, tzinfo=WIB)

    def test_today_yesterday_and_older(self) -> None:
        today = datetime(2026, 11, 19, 6, 30, tzinfo=WIB)
        self.assertEqual(rm.format_time(today, self.NOW, WIB), "Hari ini 06:30")
        self.assertEqual(rm.format_time(today - timedelta(days=1), self.NOW, WIB), "Kemarin 06:30")
        self.assertEqual(rm.format_time(today - timedelta(days=3), self.NOW, WIB), "16 Nov 2026 06:30")
        self.assertEqual(rm.format_time(datetime(2026, 5, 2, 23, 59, tzinfo=WIB), self.NOW, WIB), "2 Mei 2026 23:59")

    def test_conversion_to_local_time_can_change_the_day(self) -> None:
        late_utc = datetime(2026, 11, 18, 20, 0, tzinfo=timezone.utc)  # 03:00 WIB tanggal 19
        self.assertEqual(rm.format_time(late_utc, self.NOW, WIB), "Hari ini 03:00")

    def test_future_timestamps_fall_back_to_date(self) -> None:
        future = datetime(2026, 11, 25, 8, 0, tzinfo=WIB)
        self.assertEqual(rm.format_time(future, self.NOW, WIB), "25 Nov 2026 08:00")


class ShortenTests(unittest.TestCase):
    def test_short_text_untouched_and_long_keeps_both_ends(self) -> None:
        self.assertEqual(rm.shorten_middle("abc", 10), "abc")
        long_text = "awal-" + "x" * 100 + "-akhir.png"
        out = rm.shorten_middle(long_text, 30)
        self.assertEqual(len(out), 30)
        self.assertTrue(out.startswith("awal-"))
        self.assertTrue(out.endswith("-akhir.png"))
        self.assertIn("\u2026", out)
        self.assertEqual(rm.shorten_middle("x" * 20, 3), "x" * 20)


class DescribeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_existing_output_is_ok_and_openable(self) -> None:
        out = self.tmp / "Hasil ñ" / "foto-tanpa-latar.png"
        out.parent.mkdir()
        out.write_bytes(b"x")
        row = rm.describe(make(str(out), "D:/foto.jpg"))
        self.assertEqual((row.status_kind, row.status_text, row.title), (rm.KIND_OK, "Berhasil", "foto-tanpa-latar.png"))
        self.assertTrue(row.can_open)
        self.assertEqual(row.folder, out.parent)

    def test_missing_file_is_reported_gracefully(self) -> None:
        folder = self.tmp / "ada"
        folder.mkdir()
        row = rm.describe(make(str(folder / "hilang.png")))
        self.assertEqual(row.status_kind, rm.KIND_MISSING)
        self.assertEqual(row.status_text, "Berkas tidak ditemukan")
        self.assertTrue(row.can_open)  # foldernya masih ada

    def test_missing_folder_disables_open(self) -> None:
        row = rm.describe(make(str(self.tmp / "tidak-ada" / "x.png")))
        self.assertEqual(row.status_kind, rm.KIND_MISSING)
        self.assertFalse(row.can_open)

    def test_failed_entry_shows_input_and_never_claims_output(self) -> None:
        row = rm.describe(make(None, str(self.tmp / "rusak.jpg"), STATUS_FAILED))
        self.assertEqual((row.status_kind, row.title), (rm.KIND_FAILED, "rusak.jpg"))
        self.assertIn("rusak.jpg", row.detail)

    def test_entry_without_any_file(self) -> None:
        row = rm.describe(make(None, None))
        self.assertEqual(row.title, "(tanpa berkas)")
        self.assertFalse(row.can_open)
        self.assertIsNone(row.folder)

    def test_filesystem_errors_do_not_raise(self) -> None:
        def boom(path):
            raise OSError("jaringan putus")

        original = rm.os.path.exists
        rm.os.path.exists = boom
        try:
            row = rm.describe(make("Z:/jauh/x.png"))
        finally:
            rm.os.path.exists = original
        self.assertEqual(row.status_kind, rm.KIND_MISSING)
        self.assertFalse(row.can_open)


class LoadRowsTests(unittest.TestCase):
    def test_none_history_and_closed_history(self) -> None:
        self.assertIsNone(rm.load_rows(None, 5))
        with tempfile.TemporaryDirectory() as tmp:
            history = HistoryDatabase(Path(tmp) / "h.db")
            history.open()
            history.close()
            self.assertIsNone(rm.load_rows(history, 5))

    def test_rows_follow_limit_and_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history = HistoryDatabase(Path(tmp) / "h.db")
            history.open()
            self.addCleanup(history.close)
            for n in range(8):
                history.add(NewEntry("QR Code Generator", None, f"C:/x/{n}.png", STATUS_SUCCESS))
            rows = rm.load_rows(history, 5)
            self.assertEqual([r.title for r in rows], ["7.png", "6.png", "5.png", "4.png", "3.png"])


if __name__ == "__main__":
    unittest.main()
