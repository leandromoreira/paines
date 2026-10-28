import gzip
import http.client
import threading

from paines.ppu.frame import NES_PALETTE
from paines.server import Emulator, FramePublisher, NesServer


class FakeBus:
    def __init__(self) -> None:
        self.controller_buttons = [0, 0]


class FakeCPU:
    def __init__(self) -> None:
        self.bus = FakeBus()
        self.count = 0

    def run_frame(self) -> bytearray:
        self.count += 1
        return bytearray([self.count % 64]) * (256 * 240)


def start():
    publisher = FramePublisher()
    cpu = FakeCPU()
    emulator = Emulator(cpu, publisher, fps=200)
    server = NesServer(("127.0.0.1", 0), emulator, publisher)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    emulator.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    return server, emulator, cpu, connection


def stop(server, emulator, connection) -> None:
    emulator.stop_event.set()
    connection.close()
    server.shutdown()
    server.server_close()


def test_frame_long_poll_returns_only_newer_frames() -> None:
    server, emulator, _, connection = start()
    try:
        seen = 0
        for _ in range(3):
            connection.request("GET", f"/frame?after={seen}&z=0")
            response = connection.getresponse()
            body = response.read()
            sequence = int(response.getheader("X-Frame-Seq"))
            assert response.status == 200
            assert len(body) == 256 * 240
            assert sequence > seen
            seen = sequence
    finally:
        stop(server, emulator, connection)


def test_frame_is_gzipped_by_default_and_roundtrips() -> None:
    server, emulator, _, connection = start()
    try:
        connection.request("GET", "/frame?after=0")
        response = connection.getresponse()
        body = response.read()
        assert response.getheader("Content-Encoding") == "gzip"
        assert len(body) < 1000
        assert len(gzip.decompress(body)) == 256 * 240
    finally:
        stop(server, emulator, connection)


def test_long_poll_times_out_with_204_when_nothing_new(monkeypatch) -> None:
    monkeypatch.setattr("paines.server.LONG_POLL_SECONDS", 0.05)
    server, emulator, _, connection = start()
    emulator.stop_event.set()
    try:
        connection.request("GET", "/frame?after=999999")
        response = connection.getresponse()
        response.read()
        assert response.status == 204
    finally:
        stop(server, emulator, connection)


def test_input_post_sets_controller_buttons_on_the_emulator() -> None:
    server, emulator, cpu, connection = start()
    try:
        connection.request("POST", "/input", body="136")
        response = connection.getresponse()
        response.read()
        assert response.status == 204
        connection.request("GET", "/frame?after=0&z=0")
        connection.getresponse().read()
        for _ in range(100):
            if cpu.bus.controller_buttons[0] == 136:
                break
            threading.Event().wait(0.01)
        assert cpu.bus.controller_buttons[0] == 136
    finally:
        stop(server, emulator, connection)


def test_bad_input_is_rejected_and_unknown_paths_404() -> None:
    server, emulator, _, connection = start()
    try:
        connection.request("POST", "/input", body="abc")
        response = connection.getresponse()
        response.read()
        assert response.status == 400
        connection.request("GET", "/nope")
        response = connection.getresponse()
        response.read()
        assert response.status == 404
    finally:
        stop(server, emulator, connection)


def test_palette_and_page_are_served() -> None:
    server, emulator, _, connection = start()
    try:
        connection.request("GET", "/palette")
        response = connection.getresponse()
        assert response.read() == bytes(c for color in NES_PALETTE for c in color[:3])
        connection.request("GET", "/")
        response = connection.getresponse()
        assert b"<canvas" in response.read()
    finally:
        stop(server, emulator, connection)
