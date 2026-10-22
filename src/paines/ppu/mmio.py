from paines.ppu.ppu import PPU, ppu_builder
from paines.types import U8, U16, U15


class PPUMMIO:
    def __init__(self, ppu: PPU | None = None) -> None:
        self.ppu = ppu or ppu_builder()
        self.open_bus: U8 = 0x0

    def write(self, address: U16, value: U8) -> None:
        address = 0x2000 + (address % 8)
        self.open_bus = value

        if address == 0x2000:
            self.ppu.v_blank_enabled = value >> 7
            self.ppu.leader = value >> 6 & 0b1
            self.ppu.spr_size = value >> 5 & 0b1
            self.ppu.bg_pattern_table = value >> 4 & 0b1
            self.ppu.spr_pattern_table = value >> 3 & 0b1
            self.ppu.vram_increment = value >> 2 & 0b1
            self.ppu.base_nametable = value & 0b11
            self.ppu.scroll_t = (self.ppu.scroll_t & ~0x0C00) | (
                self.ppu.base_nametable << 10
            )
            self.ppu._update_nmi_line()
        elif address == 0x2001:
            self.ppu.emphasize_blue = value >> 7
            self.ppu.emphasize_green = value >> 6 & 0b1
            self.ppu.emphasize_red = value >> 5 & 0b1
            self.ppu.spr_enabled = value >> 4 & 0b1
            self.ppu.bg_enabled = value >> 3 & 0b1
            self.ppu.show_spr_leftmost = value >> 2 & 0b1
            self.ppu.show_bg_leftmost = value >> 1 & 0b1
            self.ppu.grayscale = value & 0b1
        elif address == 0x2003:
            self.ppu.oam_address = value
        elif address == 0x2004:
            self.ppu.write_oam(value)
        elif address == 0x2005:
            if self.ppu.write_toggle == 0:
                self.ppu.write_toggle = 1
                coarse_x: U8 = value >> 3
                self.ppu.scroll_t = (self.ppu.scroll_t & ~0b11111) | coarse_x
                self.ppu.scroll_x = value & 0b111
            else:
                self.ppu.write_toggle = 0
                fine_y = value & 0b111
                coarse_y = value >> 3
                self.ppu.scroll_t &= ~0b111001111100000
                self.ppu.scroll_t |= (fine_y << 12) | (coarse_y << 5)
                self.ppu.scroll_t &= 0b111111111111111
        elif address == 0x2006:
            if self.ppu.write_toggle == 0:
                self.ppu.write_toggle = 1
                self.ppu.scroll_t = (self.ppu.scroll_t & 0x00FF) | ((value & 0x3F) << 8)
            else:
                self.ppu.write_toggle = 0
                self.ppu.scroll_t = (self.ppu.scroll_t & 0x7F00) | value
                self.ppu.scroll_v = self.ppu.scroll_t
        elif address == 0x2007:
            self._write_vram_data(value)

    def read(self, address: U16) -> U8:
        address = 0x2000 + (address % 8)

        if address == 0x2002:
            self.ppu.write_toggle = 0
            value: U8 = (
                (self.ppu.v_blank_status << 7)
                | (self.ppu.spr_zero_hit << 6)
                | (self.ppu.spr_overflow << 5)
                | (self.open_bus & 0b11111)
            )
            self.ppu.v_blank_status = 0
            self.ppu._update_nmi_line()
            self.open_bus = value
            return value
        elif address == 0x2004:
            self.open_bus = self.ppu.read_oam()
            return self.open_bus
        elif address == 0x2007:
            vram_address = self.ppu.scroll_v & 0x3FFF
            fetched = self.ppu.read_vram(vram_address)

            if vram_address >= 0x3F00:
                value_to_return = fetched
                self.ppu.read_buffer = self.ppu.read_vram(vram_address - 0x1000)
            else:
                value_to_return = self.ppu.read_buffer
                self.ppu.read_buffer = fetched

            self.ppu.scroll_v = (self.ppu.scroll_v + (32 if self.ppu.vram_increment else 1)) & 0x7FFF
            self.open_bus = value_to_return
            return self.open_bus

        return self.open_bus

    def _write_vram_data(self, value: U8) -> None:
        self.ppu.write_vram(self.ppu.scroll_v & 0x3FFF, value)
        increment = 32 if self.ppu.vram_increment else 1
        self.ppu.scroll_v = (self.ppu.scroll_v + increment) & 0x7FFF


def ppu_mmio_builder(ppu: PPU | None = None) -> PPUMMIO:
    return PPUMMIO(ppu=ppu)
