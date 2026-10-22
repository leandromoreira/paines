import pytest

from paines.ppu.frame import NES_PALETTE, write_ppm
from paines.ppu.ppu import FRAME_HEIGHT, FRAME_WIDTH


def test_write_ppm_outputs_rgb_pixels(tmp_path) -> None:
    frame = bytearray(FRAME_WIDTH * FRAME_HEIGHT)
    frame[0] = 1
    output = tmp_path / "frame.ppm"

    write_ppm(frame, output)

    data = output.read_bytes()
    header = f"P6\n{FRAME_WIDTH} {FRAME_HEIGHT}\n255\n".encode("ascii")
    assert data.startswith(header)
    assert data[len(header) : len(header) + 3] == bytes(NES_PALETTE[1])
    assert data[len(header) + 3 : len(header) + 6] == bytes(NES_PALETTE[0])
    assert len(data) == len(header) + FRAME_WIDTH * FRAME_HEIGHT * 3


def test_write_ppm_rejects_wrong_frame_size(tmp_path) -> None:
    with pytest.raises(ValueError, match="Expected"):
        write_ppm(bytearray(1), tmp_path / "invalid.ppm")


def test_write_ppm_rejects_palette_indices_out_of_range(tmp_path) -> None:
    frame = bytearray(FRAME_WIDTH * FRAME_HEIGHT)
    frame[-1] = 64

    with pytest.raises(ValueError, match="palette index"):
        write_ppm(frame, tmp_path / "invalid.ppm")


def test_dump_frame_command_runs_mapper_zero_rom(tmp_path, capsys) -> None:
    from paines import main

    rom_path = tmp_path / "loop.nes"
    output = tmp_path / "frame.ppm"
    header = bytearray(b"NES\x1a" + bytes(12))
    header[4] = 2
    prg = bytearray(0x8000)
    prg[0:3] = b"\x4c\x00\x80"
    prg[0x7FFC:0x7FFE] = b"\x00\x80"
    rom_path.write_bytes(header + prg)

    main(
        [
            "dump-frame",
            str(rom_path),
            "--output",
            str(output),
            "--skip-frames",
            "0",
        ]
    )

    assert output.read_bytes().startswith(b"P6\n256 240\n255\n")
    assert "Wrote" in capsys.readouterr().out
