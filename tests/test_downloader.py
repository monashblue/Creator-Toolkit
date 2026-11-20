import hashlib
import os
import socket
import tempfile
import unittest
from pathlib import Path

from core import model_manager as dl
from core.tasks import CancelToken, OperationCancelled
from tests.http_server import FileServer

PAYLOAD = os.urandom(1_200_000)
SHA = "sha256:" + hashlib.sha256(PAYLOAD).hexdigest()
HTTP = ("http",)


class DownloaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dest = Path(self._tmp.name) / "folder model ñ" / "model.onnx"
        self.part = self.dest.with_name("model.onnx.part")

    def fetch(self, server, **kwargs):
        return dl.download_file(server.url, self.dest, consent=True, allowed_schemes=HTTP, **kwargs)

    def test_success_with_checksum_and_progress(self) -> None:
        reports = []
        with FileServer(PAYLOAD) as server:
            result = self.fetch(server, checksum=SHA, progress=lambda d, t: reports.append((d, t)))
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)
        self.assertFalse(self.part.exists())
        self.assertTrue(result.verified)
        self.assertFalse(result.resumed)
        self.assertEqual(reports[-1], (len(PAYLOAD), len(PAYLOAD)))
        done = [d for d, _ in reports]
        self.assertEqual(done, sorted(done))

    def test_download_without_checksum_is_unverified(self) -> None:
        with FileServer(PAYLOAD) as server:
            result = self.fetch(server)
        self.assertFalse(result.verified)
        self.assertEqual(result.size, len(PAYLOAD))

    def test_consent_is_required_and_no_request_is_made(self) -> None:
        with FileServer(PAYLOAD) as server:
            with self.assertRaises(dl.ConsentRequiredError):
                dl.download_file(server.url, self.dest, consent=False, allowed_schemes=HTTP)
            self.assertEqual(server.requests, [])
        self.assertFalse(self.dest.exists())

    def test_plain_http_is_rejected_by_default(self) -> None:
        with FileServer(PAYLOAD) as server:
            with self.assertRaises(dl.DownloadError) as ctx:
                dl.download_file(server.url, self.dest, consent=True)
            self.assertIn("HTTPS", str(ctx.exception))
            self.assertEqual(server.requests, [])

    def test_checksum_mismatch_removes_file(self) -> None:
        wrong = "sha256:" + "0" * 64
        with FileServer(PAYLOAD) as server:
            with self.assertRaises(dl.DownloadError) as ctx:
                self.fetch(server, checksum=wrong)
        self.assertIn("checksum", str(ctx.exception))
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.part.exists())

    def test_invalid_checksum_format(self) -> None:
        with FileServer(PAYLOAD) as server:
            with self.assertRaises(dl.DownloadError):
                self.fetch(server, checksum="bukan-checksum")

    def test_interrupted_download_resumes(self) -> None:
        with FileServer(PAYLOAD, cut_at=500_000) as server:
            with self.assertRaises(dl.DownloadError) as ctx:
                self.fetch(server)
            self.assertRegex(str(ctx.exception).lower(), "terputus|tidak lengkap")
            self.assertTrue(self.part.exists())
            kept = self.part.stat().st_size
            self.assertEqual(kept, 500_000)
            self.assertFalse(self.dest.exists())

            result = self.fetch(server, checksum=SHA)
            self.assertEqual(server.requests[-1], f"bytes={kept}-")
        self.assertTrue(result.resumed)
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)

    def test_server_without_range_restarts_cleanly(self) -> None:
        with FileServer(PAYLOAD, support_range=False, cut_at=300_000) as server:
            with self.assertRaises(dl.DownloadError):
                self.fetch(server)
            result = self.fetch(server, checksum=SHA)
        self.assertFalse(result.resumed)
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)

    def test_complete_part_triggers_416_and_restart(self) -> None:
        self.part.parent.mkdir(parents=True)
        self.part.write_bytes(PAYLOAD)
        with FileServer(PAYLOAD) as server:
            result = self.fetch(server, checksum=SHA)
            self.assertEqual(len(server.requests), 2)
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)
        self.assertTrue(result.verified)

    def test_http_errors_have_clear_messages(self) -> None:
        expectations = {404: "404", 403: "menolak", 500: "bermasalah", 429: "membatasi"}
        for code, fragment in expectations.items():
            with self.subTest(code), FileServer(PAYLOAD, status=code) as server:
                with self.assertRaises(dl.DownloadError) as ctx:
                    self.fetch(server)
                self.assertIn(fragment, str(ctx.exception))
        self.assertFalse(self.dest.exists())

    def test_connection_refused_message(self) -> None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with self.assertRaises(dl.DownloadError) as ctx:
            dl.download_file(f"http://127.0.0.1:{port}/m.onnx", self.dest, consent=True, allowed_schemes=HTTP)
        self.assertRegex(str(ctx.exception), "server|Koneksi|koneksi")

    def test_cancellation_keeps_partial_file_for_resume(self) -> None:
        token = CancelToken()

        def on_progress(done, total):
            if done > 100_000:
                token.cancel()

        with FileServer(PAYLOAD, chunk_delay=0.01) as server:
            with self.assertRaises(OperationCancelled):
                self.fetch(server, progress=on_progress, token=token)
            self.assertFalse(self.dest.exists())
            self.assertTrue(self.part.exists())
            self.assertLess(self.part.stat().st_size, len(PAYLOAD))
            result = self.fetch(server, checksum=SHA)
        self.assertTrue(result.resumed)
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)

    def test_empty_response(self) -> None:
        with FileServer(b"") as server:
            with self.assertRaises(dl.DownloadError):
                self.fetch(server)
        self.assertFalse(self.dest.exists())

    def test_redirect_is_followed_and_resume_works_across_it(self) -> None:
        with FileServer(PAYLOAD, cut_at=400_000) as server:
            server.redirect_to = server.url.replace("model.onnx", "real.onnx")
            with self.assertRaises(dl.DownloadError):
                self.fetch(server)
            result = self.fetch(server, checksum=SHA)
        self.assertTrue(result.resumed)
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)

    def test_redirect_to_disallowed_scheme_is_blocked(self) -> None:
        with FileServer(PAYLOAD) as server:
            server.redirect_to = "ftp://127.0.0.1/model.onnx"
            with self.assertRaises(dl.DownloadError) as ctx:
                self.fetch(server)
        self.assertIn("tidak aman", str(ctx.exception))
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.part.exists())

    def test_ssl_and_timeout_messages(self) -> None:
        import ssl

        self.assertIn("aman", dl._network_error_message(ssl.SSLError("x")))
        self.assertIn("Waktu tunggu", dl._network_error_message(socket.timeout()))

    def test_existing_model_is_replaced_atomically(self) -> None:
        self.dest.parent.mkdir(parents=True)
        self.dest.write_bytes(b"rusak")
        with FileServer(PAYLOAD) as server:
            self.fetch(server, checksum=SHA)
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)


if __name__ == "__main__":
    unittest.main()
