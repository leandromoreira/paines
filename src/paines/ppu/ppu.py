from paines.types import U8, U16, U1, U2, U15, U3
from paines.bus.ppu import PPUBus, ppu_bus_builder


class PPU:
    def __init__(self, bus: PPUBus | None = None) -> None:
        self.v_blank_status: U1 = 0
        self.v_blank_enabled: U1 = 0
        self.leader: U1 = 0
        self.spr_size: U1 = 0
        self.bg_pattern_table: U1 = 0
        self.spr_pattern_table: U1 = 0
        self.vram_increment: U1 = 0
        self.base_nametable: U2 = 0
        self.emphasize_blue: U1 = 0
        self.emphasize_green: U1 = 0
        self.emphasize_red: U1 = 0
        self.spr_enabled: U1 = 0
        self.bg_enabled: U1 = 0
        self.show_spr_leftmost: U1 = 0
        self.show_bg_leftmost: U1 = 0
        self.grayscale: U1 = 0
        self.write_toggle: U1 = 0
        self.spr_zero_hit: U1 = 0
        self.spr_overflow: U1 = 0
        self.oam_address: U8 = 0x00
        self.oam_memory = bytearray(0x100)

        # https://www.nesdev.org/wiki/PPU_scrolling
        # yyy NN YYYYY XXXXX
        # ||| || ||||| +++++-- Coarse X scroll (0-31 tiles)
        # ||| || +++++-------- Coarse Y scroll (0-31 tiles)
        # ||| ++-------------- Nametable select (0-3)
        # +++----------------- Fine Y scroll (0-7 pixels)
        self.scroll_v: U15 = 0
        self.scroll_t: U15 = 0
        self.scroll_x: U3 = 0

        self.read_buffer: U8 = 0x0
        self.bus = bus if bus is not None else ppu_bus_builder()

    def write_oam(self, value: U8) -> None:
        self.oam_memory[self.oam_address] = value
        self.oam_address = (self.oam_address + 1) & 0xFF

    def read_oam(self) -> U8:
        return self.oam_memory[self.oam_address]

    def write_vram(self, address: U16, value: U8) -> None:
        self.bus.write(address, value)

    def read_vram(self, address: U16) -> U8:
        return self.bus.read(address)


def ppu_builder(bus: PPUBus | None = None) -> PPU:
    return PPU(bus=bus)
