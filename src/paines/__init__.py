import argparse
from collections.abc import Sequence
from os import devnull
from pathlib import Path

from paines.bus.bus import CPUBus
from paines.cartridge.cartridge import Cartridge
from paines.cpu.cpu import CPU6502
from paines.ppu.frame import write_ppm


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="paines")
    commands = parser.add_subparsers(dest="command", required=True)
    dump_frame = commands.add_parser(
        "dump-frame", help="run one mapper-0 ROM frame and write a PPM image"
    )
    dump_frame.add_argument("rom", type=Path)
    dump_frame.add_argument("-o", "--output", type=Path, default=Path("frame.ppm"))
    dump_frame.add_argument(
        "--skip-frames",
        type=int,
        default=4,
        help="number of startup frames to run before saving (default: 4)",
    )
    play_command = commands.add_parser("play", help="play a mapper-0 ROM in a window")
    play_command.add_argument("rom", type=Path)
    play_command.add_argument("--scale", type=int, default=3)
    args = parser.parse_args(argv)
    if args.command == "play":
        args.skip_frames = 0
    if args.skip_frames < 0:
        parser.error("--skip-frames must be non-negative")

    cartridge = Cartridge()
    try:
        cartridge.load(str(args.rom))
    except OSError as error:
        parser.error(f"cannot load ROM: {error}")

    if cartridge.magic_id != b"NES\x1a":
        parser.error(f"{args.rom} is not an iNES ROM")
    if cartridge.prg_size == 0:
        parser.error("ROM has no PRG-ROM")
    if cartridge.mapper_id != 0:
        parser.error(f"mapper {cartridge.mapper_id} is not supported by this command")

    bus = CPUBus(cartridge=cartridge)
    cpu = CPU6502(bus=bus, file_name=devnull)
    try:
        cpu.reset()
        if args.command == "play":
            from paines.frontend import play

            play(cpu, scale=args.scale)
            return
        for _ in range(args.skip_frames):
            cpu.run_frame()
        frame = cpu.run_frame()
        write_ppm(frame, args.output)
    finally:
        cpu.debug_file.close()

    print(f"Wrote {args.output}")
