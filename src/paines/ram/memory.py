from paines.types import U8, U16
# General RAM Map
# https://problemkaputt.de/everynes.htm#memorymaps
# 0x0000-0x07FF   Internal 2K Work RAM (mirrored to 0x800-0x1FFF)

# Detailed RAM Map
# https://www.nesdev.org/NESDoc.pdf
# 0x0000-0x00FF - Zero Page
# 0x0100-0x01FF - Stack
# 0x0200-0x07FF - RAM
# 0x0800-0x1FFF - Mirrors of 0x0000-0x07FF


class RAM:
    BYTE_MASK = 0xFF

    def __init__(self, size: U16 = 0x800, start_offset: U16 = 0x0000) -> None:
        self.cells: list[U8] = [0] * size
        self.start_offset = start_offset
        self.ram_mask: U16 = size - 1

    def write(self, address: U16, value: U8) -> None:
        self.cells[(address - self.start_offset) & self.ram_mask] = (
            value & RAM.BYTE_MASK
        )

    def read(self, address: U16) -> U8:
        return self.cells[(address - self.start_offset) & self.ram_mask]


def ram_builder() -> RAM:
    return RAM()
