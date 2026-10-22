from paines.types import U8, U16, U1, U2, U15, U3
from paines.bus.ppu import PPUBus, ppu_bus_builder

FRAME_WIDTH = 256
FRAME_HEIGHT = 240
PPU_DOTS_PER_SCANLINE = 341
PPU_SCANLINES_PER_FRAME = 262
PPU_DOTS_PER_FRAME = PPU_DOTS_PER_SCANLINE * PPU_SCANLINES_PER_FRAME
VBLANK_START = 241 * PPU_DOTS_PER_SCANLINE + 1
VBLANK_END = 261 * PPU_DOTS_PER_SCANLINE + 1


class PPU:
    def __init__(self, bus: PPUBus | None = None) -> None:
        self.v_blank_status: U1 = 0
        self.v_blank_enabled: U1 = 0
        self.nmi_pending: bool = False
        self._nmi_line: bool = False
        self.scanline = 261
        self.dot = 0
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
        self.frame_buffer = bytearray(FRAME_WIDTH * FRAME_HEIGHT)
        self.frame_ready = False

    def write_oam(self, value: U8) -> None:
        self.oam_memory[self.oam_address] = value
        self.oam_address = (self.oam_address + 1) & 0xFF

    def read_oam(self) -> U8:
        return self.oam_memory[self.oam_address]

    def write_vram(self, address: U16, value: U8) -> None:
        self.bus.write(address, value)

    def read_vram(self, address: U16) -> U8:
        return self.bus.read(address)

    def advance_cpu_cycles(self, cycles: int) -> None:
        self.advance_dots(cycles * 3)

    def advance_dots(self, dots: int) -> None:
        position = self.scanline * PPU_DOTS_PER_SCANLINE + self.dot
        remaining = dots

        while remaining > 0:
            distances = [
                (event - position) % PPU_DOTS_PER_FRAME or PPU_DOTS_PER_FRAME
                for event in (VBLANK_START, VBLANK_END)
            ]
            distance = min(distances)
            if distance > remaining:
                break

            position = (position + distance) % PPU_DOTS_PER_FRAME
            remaining -= distance
            if position == VBLANK_START:
                self.frame_ready = True
                self.render_background()
            self.v_blank_status = int(position == VBLANK_START)
            self._update_nmi_line()

        position = (position + remaining) % PPU_DOTS_PER_FRAME
        self.scanline, self.dot = divmod(position, PPU_DOTS_PER_SCANLINE)

    def _update_nmi_line(self) -> None:
        nmi_line = bool(self.v_blank_status and self.v_blank_enabled)
        if nmi_line and not self._nmi_line:
            self.nmi_pending = True
        self._nmi_line = nmi_line

    def take_nmi(self) -> bool:
        pending = self.nmi_pending
        self.nmi_pending = False
        return pending

    def take_frame(self) -> bytearray | None:
        if not self.frame_ready:
            return None
        self.frame_ready = False
        return self.frame_buffer

    def render_background(self) -> bytearray:
        universal_color = self.read_vram(0x3F00)

        if not self.bg_enabled:
            self.frame_buffer[:] = bytes([universal_color]) * len(self.frame_buffer)
            return self.frame_buffer

        pattern_table_address: U16 = self.bg_pattern_table * 0x1000
        coarse_x = self.scroll_t & 0x1F
        coarse_y = (self.scroll_t >> 5) & 0x1F
        nametable = (self.scroll_t >> 10) & 0x03
        fine_y = (self.scroll_t >> 12) & 0x07
        fine_x = self.scroll_x

        for screen_y in range(FRAME_HEIGHT):
            world_y = (coarse_y * 8 + fine_y + screen_y) % (2 * FRAME_HEIGHT)
            tile_y, pixel_y = divmod(world_y, 8)
            nametable_y, local_tile_y = divmod(tile_y, 30)
            nametable_row = (nametable >> 1) ^ nametable_y
            nametable_row &= 1
            world_x = coarse_x * 8 + fine_x
            screen_x = 0

            while screen_x < FRAME_WIDTH:
                world_x %= 2 * FRAME_WIDTH
                tile_x, pixel_x = divmod(world_x, 8)
                nametable_x, local_tile_x = divmod(tile_x, 32)
                nametable_column = (nametable & 1) ^ nametable_x
                nametable_column &= 1
                table_index = nametable_row * 2 + nametable_column
                table_address = 0x2000 + table_index * 0x400
                tile_address = table_address + local_tile_y * 32 + local_tile_x
                tile_index = self.read_vram(tile_address)
                attribute_address = (
                    table_address
                    + 0x3C0
                    + (local_tile_y // 4) * 8
                    + (local_tile_x // 4)
                )
                attribute = self.read_vram(attribute_address)
                palette_shift = (
                    ((local_tile_y % 4) // 2) * 4
                    + ((local_tile_x % 4) // 2) * 2
                )
                palette = (attribute >> palette_shift) & 0b11
                pattern_address = (
                    pattern_table_address + tile_index * 16 + pixel_y
                )
                low_plane = self.read_vram(pattern_address)
                high_plane = self.read_vram(pattern_address + 8)
                palette_address = 0x3F00 + palette * 4
                palette_colors = (
                    universal_color,
                    self.read_vram(palette_address + 1),
                    self.read_vram(palette_address + 2),
                    self.read_vram(palette_address + 3),
                )

                tile_span = min(8 - pixel_x, FRAME_WIDTH - screen_x)
                for offset in range(tile_span):
                    bit = 7 - (pixel_x + offset)
                    pixel = ((low_plane >> bit) & 1) | (
                        ((high_plane >> bit) & 1) << 1
                    )
                    if pixel == 0 or (
                        screen_x + offset < 8 and not self.show_bg_leftmost
                    ):
                        color = universal_color
                    else:
                        color = palette_colors[pixel]
                    self.frame_buffer[
                        screen_y * FRAME_WIDTH + screen_x + offset
                    ] = color

                screen_x += tile_span
                world_x += tile_span

        return self.frame_buffer


def ppu_builder(bus: PPUBus | None = None) -> PPU:
    return PPU(bus=bus)
