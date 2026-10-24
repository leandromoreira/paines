"""Play a ROM in a browser using nothing but plain HTTP (no WebSockets).

    GET  /             the page
    GET  /palette      192 bytes, the 64 RGB colours
    GET  /frame?after=N  long poll: blocks until a frame newer than N exists, then returns
                         256x240 palette indices (X-Frame-Seq carries its number).
                         Add z=0 to disable gzip; 204 means "nothing new yet, ask again".
    POST /input        body is the controller bitmask as a decimal number
    GET  /stats        JSON counters
"""

import gzip
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from paines.ppu.frame import NES_PALETTE

INDEX_HTML = Path(__file__).parent / "web" / "index.html"
LONG_POLL_SECONDS = 1.0


class FramePublisher:
    """Holds the newest frame; HTTP threads wait on it, the emulator thread publishes to it."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self.seq = 0
        self._raw = b""
        self._gzipped: tuple[int, bytes] = (0, b"")

    def publish(self, frame: bytes) -> None:
        with self._condition:
            self.seq += 1
            self._raw = frame
            self._condition.notify_all()

    def wait_newer(self, after: int, timeout: float) -> tuple[int, bytes] | None:
        with self._condition:
            if self.seq <= after:
                self._condition.wait_for(lambda: self.seq > after, timeout)
            if self.seq <= after:
                return None
            return self.seq, self._raw

    def gzipped(self, seq: int, raw: bytes) -> bytes:
        # Compress once per frame, however many clients ask for it.
        with self._condition:
            cached_seq, data = self._gzipped
            if cached_seq == seq:
                return data
        data = gzip.compress(raw, compresslevel=1)
        with self._condition:
            if seq >= self._gzipped[0]:
                self._gzipped = (seq, data)
        return data


class Emulator(threading.Thread):
    """Runs frames at a fixed rate and publishes each one."""

    def __init__(self, cpu, publisher: FramePublisher, fps: float = 60.0) -> None:
        super().__init__(daemon=True)
        self.cpu = cpu
        self.publisher = publisher
        self.period = 1 / fps
        self.buttons = 0
        self.stop_event = threading.Event()
        self.frames = 0

    def run(self) -> None:
        # Deadlines are absolute (start + n * period), so a slow frame is paid back by sleeping
        # less on the next ones instead of drifting.
        deadline = time.perf_counter()
        while not self.stop_event.is_set():
            self.cpu.bus.controller_buttons[0] = self.buttons
            self.publisher.publish(bytes(self.cpu.run_frame()))
            self.frames += 1
            deadline += self.period
            delay = deadline - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                deadline = time.perf_counter()  # too far behind: give up catching up and resync


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive
    disable_nagle_algorithm = True
    server: "NesServer"

    def log_message(self, format: str, *args) -> None:
        pass

    def _send(self, status: int, body: bytes = b"", content_type: str = "application/octet-stream", **headers) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in headers.items():
            self.send_header(name.replace("_", "-"), str(value))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/":
            self._send(200, INDEX_HTML.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/palette":
            self._send(200, bytes(channel for color in NES_PALETTE for channel in color[:3]))
        elif url.path == "/frame":
            self._frame(int(query.get("after", ["0"])[0]), query.get("z", ["1"])[0] != "0")
        elif url.path == "/stats":
            emulator = self.server.emulator
            stats = {"seq": self.server.publisher.seq, "emulated_frames": emulator.frames}
            self._send(200, json.dumps(stats).encode(), "application/json")
        else:
            self._send(404)

    def _frame(self, after: int, compress: bool) -> None:
        newest = self.server.publisher.wait_newer(after, LONG_POLL_SECONDS)
        if newest is None:
            self._send(204)
            return
        seq, raw = newest
        if compress:
            self._send(200, self.server.publisher.gzipped(seq, raw), Content_Encoding="gzip", X_Frame_Seq=seq)
        else:
            self._send(200, raw, X_Frame_Seq=seq)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/input":
            self._send(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            self.server.emulator.buttons = int(self.rfile.read(length) or b"0") & 0xFF
        except ValueError:
            self._send(400)
            return
        self._send(204)


class NesServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], emulator: Emulator, publisher: FramePublisher) -> None:
        super().__init__(address, Handler)
        self.emulator = emulator
        self.publisher = publisher


def serve(cpu, host: str = "127.0.0.1", port: int = 8080, fps: float = 60.0) -> None:
    publisher = FramePublisher()
    emulator = Emulator(cpu, publisher, fps)
    server = NesServer((host, port), emulator, publisher)
    emulator.start()
    print(f"paines serving http://{host}:{server.server_address[1]}/  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        emulator.stop_event.set()
        server.server_close()
