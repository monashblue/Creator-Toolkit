"""Server HTTP lokal untuk menguji pengunduh: dukungan Range, koneksi terputus, dan kode status."""

from __future__ import annotations

import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:  # senyap
        pass

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._serve()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True  # klien membatalkan, wajar pada pengujian

    def _serve(self) -> None:
        state = self.server.state
        range_header = self.headers.get("Range")
        state.requests.append(range_header)
        if state.redirect_to and self.path == "/model.onnx":
            self.send_response(302)
            self.send_header("Location", state.redirect_to)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if state.status:
            self.send_error(state.status)
            return

        payload = state.payload
        start = 0
        if range_header and state.support_range:
            match = re.match(r"bytes=(\d+)-", range_header)
            start = int(match.group(1)) if match else 0
            if start >= len(payload):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{len(payload)}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(payload) - 1}/{len(payload)}")
        else:
            self.send_response(200)
        body = payload[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        cut = state.cut_at
        if cut is not None:
            state.cut_at = None  # hanya sekali
            self.wfile.write(body[:cut])
            self.wfile.flush()
            self.close_connection = True
            return
        for offset in range(0, len(body), 32 * 1024):
            self.wfile.write(body[offset : offset + 32 * 1024])
            if state.chunk_delay:
                time.sleep(state.chunk_delay)


class FileServer:
    def __init__(self, payload: bytes, *, support_range: bool = True, cut_at: int | None = None,
                 status: int | None = None, chunk_delay: float = 0.0) -> None:
        self.payload = payload
        self.support_range = support_range
        self.cut_at = cut_at
        self.status = status
        self.chunk_delay = chunk_delay
        self.redirect_to: str | None = None
        self.requests: list[str | None] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.state = self
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/model.onnx"

    def __enter__(self) -> "FileServer":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
