"""Run every supported ROM in a directory and save a frame of each to frames/.

usage: uv run python capture_frames.py [ROM_DIR ...] [--frames N]
"""

import argparse
from os import devnull
from pathlib import Path

from paines.bus.bus import CPUBus
from paines.cartridge.cartridge import Cartridge
from paines.cartridge.mappers import is_supported
from paines.cpu.cpu import CPU6502
from paines.ppu.frame import write_png

OUTPUT_DIR = Path(__file__).parent / "frames"
DEFAULT_DIRS = [Path(__file__).parent / "tests" / "cartridge" / "zelda"]
START = 0x08


def capture(rom: Path, frames: int) -> Path | None:
    cartridge = Cartridge()
    cartridge.load(str(rom))
    if cartridge.magic_id != b"NES\x1a" or not is_supported(cartridge.mapper_id):
        print(f"skip  {rom.name} (mapper {cartridge.mapper_id})")
        return None

    cpu = CPU6502(bus=CPUBus(cartridge=cartridge), file_name=devnull)
    try:
        cpu.reset()
        frame = bytearray()
        for index in range(frames):
            # tap Start every 50 frames to get past title screens
            pressed = index > 60 and index % 50 in (5, 6, 7)
            cpu.bus.controller_buttons[0] = START if pressed else 0
            frame = cpu.run_frame()
    finally:
        cpu.debug_file.close()

    output = OUTPUT_DIR / f"{rom.stem.strip()}.png"
    write_png(frame, output)
    print(f"ok    {rom.name} (mapper {cartridge.mapper_id}) -> {output.name}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dirs", nargs="*", type=Path, default=DEFAULT_DIRS)
    parser.add_argument("--frames", type=int, default=420)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    roms = sorted(
        rom
        for directory in args.dirs
        for rom in directory.iterdir()
        if rom.suffix.lower() == ".nes"
    )
    for rom in roms:
        capture(rom, args.frames)


if __name__ == "__main__":
    main()
