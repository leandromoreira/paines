import struct
import zlib
from pathlib import Path

from paines.ppu.ppu import FRAME_HEIGHT, FRAME_WIDTH

NES_PALETTE: tuple[tuple[int, int, int], ...] = (
    (124, 124, 124), (0, 0, 252), (0, 0, 188), (68, 40, 188),
    (148, 0, 132), (168, 0, 32), (168, 16, 0), (136, 20, 0),
    (80, 48, 0), (0, 120, 0), (0, 104, 0), (0, 88, 0),
    (0, 64, 88), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (188, 188, 188), (0, 120, 248), (0, 88, 248), (104, 68, 252),
    (216, 0, 204), (228, 0, 88), (248, 56, 0), (228, 92, 16),
    (172, 124, 0), (0, 184, 0), (0, 168, 0), (0, 168, 68),
    (0, 136, 136), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (248, 248, 248), (60, 188, 252), (104, 136, 252), (152, 120, 248),
    (248, 120, 248), (248, 88, 152), (248, 120, 88), (252, 160, 68),
    (248, 184, 0), (184, 248, 24), (88, 216, 84), (88, 248, 152),
    (0, 232, 216), (120, 120, 120), (0, 0, 0), (0, 0, 0),
    (252, 252, 252), (164, 228, 252), (184, 184, 248), (216, 184, 248),
    (248, 184, 248), (248, 164, 192), (240, 208, 176), (252, 224, 168),
    (248, 216, 120), (216, 248, 120), (184, 248, 184), (184, 248, 216),
    (0, 252, 252), (248, 216, 248), (0, 0, 0), (0, 0, 0),
)


def _rgb_pixels(frame: bytes | bytearray) -> bytearray:
    expected_size = FRAME_WIDTH * FRAME_HEIGHT
    if len(frame) != expected_size:
        raise ValueError(f"Expected {expected_size} palette indices, got {len(frame)}")
    if any(color >= len(NES_PALETTE) for color in frame):
        raise ValueError("Frame contains a palette index outside the 64-color NES palette")

    rgb_pixels = bytearray()
    for color in frame:
        rgb_pixels.extend(NES_PALETTE[color])
    return rgb_pixels


def write_ppm(frame: bytes | bytearray, output: str | Path) -> None:
    header = f"P6\n{FRAME_WIDTH} {FRAME_HEIGHT}\n255\n".encode("ascii")
    Path(output).write_bytes(header + _rgb_pixels(frame))


def write_png(frame: bytes | bytearray, output: str | Path) -> None:
    """Writes the frame as an RGB PNG, which unlike PPM renders in browsers and READMEs."""
    rgb_pixels = _rgb_pixels(frame)
    stride = FRAME_WIDTH * 3
    scanlines = b"".join(
        b"\x00" + bytes(rgb_pixels[row * stride : (row + 1) * stride])
        for row in range(FRAME_HEIGHT)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", FRAME_WIDTH, FRAME_HEIGHT, 8, 2, 0, 0, 0)
    Path(output).write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(scanlines, 9))
        + chunk(b"IEND", b"")
    )
