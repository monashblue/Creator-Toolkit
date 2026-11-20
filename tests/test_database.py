import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import database as db
from core.database import HistoryDatabase, HistoryError, NewEntry


def entry(n: int = 0, status: str = db.STATUS_SUCCESS, tool: str = "QR Code Generator") -> NewEntry:
    return NewEntry(tool, None if n % 2 else f"C:/Masukan {n}.png", f"C:/Hasil/keluaran {n}.png", status)


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "data pengguna ñ" / "history.db"
        self.db = HistoryDatabase(self.path)
        self.db.open()
        self.addCleanup(self.db.close)

    def test_schema_matches_specification(self) -> None:
        self.db.close()
        conn = sqlite3.connect(self.path)
        try:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(history)")]
            self.assertEqual(columns, ["id", "tool_name", "input_file", "output_file", "status", "created_at"])
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
            types = {row[1]: row[2] for row in conn.execute("PRAGMA table_info(history)")}
            self.assertNotIn("BLOB", types.values())
        finally:
            conn.close()

    def test_add_and_recent_newest_first(self) -> None:
        for n in range(5):
            self.db.add(entry(n))
        rows = self.db.recent(3)
        self.assertEqual([r.output_file for r in rows], [f"C:/Hasil/keluaran {n}.png" for n in (4, 3, 2)])
        self.assertEqual(self.db.count(), 5)
        self.assertEqual(rows[0].input_file, "C:/Masukan 4.png")  # n genap punya input
        self.assertIsNone(rows[1].input_file)  # n ganjil tanpa input

    def test_none_paths_and_failed_status(self) -> None:
        self.db.add(NewEntry("Background Remover", "D:/a.jpg", None, db.STATUS_FAILED))
        row = self.db.recent(1)[0]
        self.assertEqual((row.input_file, row.output_file, row.status), ("D:/a.jpg", None, "gagal"))

    def test_filters(self) -> None:
        self.db.add(entry(0, tool="QR Code Generator"))
        self.db.add(entry(2, tool="Background Remover"))
        self.db.add(entry(4, status=db.STATUS_FAILED, tool="Background Remover"))
        self.assertEqual(len(self.db.recent(10, tool_name="Background Remover")), 2)
        self.assertEqual(len(self.db.recent(10, status=db.STATUS_FAILED)), 1)
        self.assertEqual(len(self.db.recent(10, tool_name="QR Code Generator", status=db.STATUS_FAILED)), 0)

    def test_timestamps_roundtrip_in_utc(self) -> None:
        moment = datetime(2026, 11, 19, 7, 5, tzinfo=timezone(timedelta(hours=7)))
        self.db.add(entry(0), created_at=moment)
        stored = self.db.recent(1)[0].created_at
        self.assertEqual(stored, moment)
        self.assertEqual(stored.utcoffset(), timedelta(0))

    def test_unicode_quotes_and_injection_are_stored_literally(self) -> None:
        nasty = "'); DROP TABLE history;-- Folder Ñandú 日本語 😀"
        self.db.add(NewEntry("Alat", nasty, f"C:/{nasty}.png", db.STATUS_SUCCESS))
        row = self.db.recent(1)[0]
        self.assertEqual(row.input_file, nasty)
        self.assertEqual(self.db.count(), 1)

    def test_validation_rejects_bad_entries(self) -> None:
        bad = [
            NewEntry("", None, None, db.STATUS_SUCCESS),
            NewEntry("Alat", None, None, "sukses"),
            NewEntry("Alat", "x" * (db.MAX_TEXT + 1), None, db.STATUS_SUCCESS),
            NewEntry("Alat", 123, None, db.STATUS_SUCCESS),  # type: ignore[arg-type]
        ]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.db.add(item)
        self.assertEqual(self.db.count(), 0)

    def test_batch_is_atomic(self) -> None:
        with self.assertRaises(ValueError):
            self.db.add_many([entry(0), NewEntry("Alat", None, None, "salah")])
        self.assertEqual(self.db.count(), 0)
        self.assertEqual(self.db.add_many([]), 0)

    def test_old_rows_are_pruned(self) -> None:
        original = db.MAX_ROWS
        db.MAX_ROWS = 10
        try:
            for n in range(25):
                self.db.add(entry(n))
        finally:
            db.MAX_ROWS = original
        self.assertEqual(self.db.count(), 10)
        self.assertEqual(self.db.recent(1)[0].output_file, "C:/Hasil/keluaran 24.png")

    def test_persistence_across_reopen(self) -> None:
        self.db.add(entry(1))
        self.db.close()
        again = HistoryDatabase(self.path)
        again.open()
        self.addCleanup(again.close)
        self.assertEqual(again.count(), 1)

    def test_concurrent_writers_do_not_lose_rows(self) -> None:
        errors = []

        def work(k: int) -> None:
            try:
                for n in range(40):
                    self.db.add(entry(k * 100 + n))
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=work, args=(k,)) for k in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        self.assertEqual(errors, [])
        self.assertEqual(self.db.count(), 320)

    def test_corrupt_file_is_backed_up_and_recreated(self) -> None:
        self.db.close()
        self.path.write_bytes(b"ini jelas bukan database sqlite " * 50)
        fresh = HistoryDatabase(self.path)
        fresh.open()
        self.addCleanup(fresh.close)
        fresh.add(entry(0))
        self.assertEqual(fresh.count(), 1)
        self.assertEqual(len(list(self.path.parent.glob("history.db.corrupt-*"))), 1)

    def test_unopenable_location_raises_friendly_error(self) -> None:
        blocker = Path(self._tmp.name) / "berkas.txt"
        blocker.write_text("x", encoding="utf-8")
        for bad in (HistoryDatabase(blocker / "history.db"), HistoryDatabase(Path(self._tmp.name))):
            with self.subTest(path=str(bad.path)), self.assertRaises(HistoryError) as ctx:
                bad.open()
            self.assertNotIn("Traceback", str(ctx.exception))
            self.assertTrue(str(ctx.exception))

    def test_newer_schema_version_is_refused(self) -> None:
        self.db.close()
        conn = sqlite3.connect(self.path)
        conn.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION + 5}")
        conn.commit()
        conn.close()
        with self.assertRaises(HistoryError):
            HistoryDatabase(self.path).open()
        self.assertEqual(list(self.path.parent.glob("history.db.corrupt-*")), [])  # tidak dianggap rusak

    def test_operations_after_close_raise_history_error(self) -> None:
        self.db.close()
        self.db.close()  # idempoten
        with self.assertRaises(HistoryError):
            self.db.count()
        with self.assertRaises(HistoryError):
            self.db.add(entry(0))


if __name__ == "__main__":
    unittest.main()
