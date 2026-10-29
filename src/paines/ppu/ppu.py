from bisect import bisect_right

from paines.types import U8, U16, U1, U2, U15, U3
from paines.bus.ppu import PPUBus, ppu_bus_builder

FRAME_WIDTH = 256
FRAME_HEIGHT = 240
PPU_DOTS_PER_SCANLINE = 341
PPU_SCANLINES_PER_FRAME = 262
PPU_DOTS_PER_FRAME = PPU_DOTS_PER_SCANLINE * PPU_SCANLINES_PER_FRAME
VBLANK_START = 241 * PPU_DOTS_PER_SCANLINE + 1
VBLANK_END = 261 * PPU_DOTS_PER_SCANLINE + 1
PRE_RENDER_SCROLL_COPY = 261 * PPU_DOTS_PER_SCANLINE + 280
LINE_RENDER_DOT = 256
# Sprite fetches raise PPU address line A12 around here; MMC3 counts those edges.
MAPPER_CLOCK_DOT = 260

# Positions in a frame where the PPU does something observable.
_EVENTS: tuple[tuple[int, int], ...] = tuple(
    sorted(
        [(y * PPU_DOTS_PER_SCANLINE + LINE_RENDER_DOT, y) for y in range(FRAME_HEIGHT)]
        + [
            (VBLANK_START, -1),
            (VBLANK_END, -2),
            (PRE_RENDER_SCROLL_COPY, -3),
        ]
        + [
            (y * PPU_DOTS_PER_SCANLINE + MAPPER_CLOCK_DOT, -4)
            for y in (*range(FRAME_HEIGHT), 261)
        ]
    )
)
_EVENT_POSITIONS = [position for position, _ in _EVENTS]

# Index = palette * 4 + pixel; non-zero pixel means opaque background.
_OPAQUE_TABLE = bytes((index & 3) != 0 for index in range(256))


class PPU:
    def __init__(self, bus: PPUBus | None = None) -> None:
        self.v_blank_status: U1 = 0
        self.v_blank_enabled: U1 = 0
        self.nmi_pending: bool = False
        self._nmi_line: bool = False
        self._scanline = 261
        self._dot = 0
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
        self._background_opaque = bytearray(FRAME_WIDTH * FRAME_HEIGHT)
        self.frame_ready = False
        self.dots_before_read = 0
        self.dots_already_advanced = 0
        # Dots the CPU has run that the PPU has not simulated yet. Nothing observable happens
        # until the next event, so they are batched and applied by flush().
        self.pending_dots = 0
        self.dots_to_event = 0
        self._tile_rows: dict[int, bytes] = {}
        self.advance_dots(0)

    @property
    def scanline(self) -> int:
        self.flush()
        return self._scanline

    @scanline.setter
    def scanline(self, value: int) -> None:
        self.flush()
        self._scanline = value
        self.advance_dots(0)

    @property
    def dot(self) -> int:
        self.flush()
        return self._dot

    @dot.setter
    def dot(self, value: int) -> None:
        self.flush()
        self._dot = value
        self.advance_dots(0)

    def write_oam(self, value: U8) -> None:
        self.oam_memory[self.oam_address] = value
        self.oam_address = (self.oam_address + 1) & 0xFF

    def read_oam(self) -> U8:
        return self.oam_memory[self.oam_address]

    def write_vram(self, address: U16, value: U8) -> None:
        self.bus.write(address, value)

    def read_vram(self, address: U16) -> U8:
        return self.bus.read(address)

    def catch_up_for_read(self) -> None:
        self.flush()
        dots = self.dots_before_read
        if dots:
            self.dots_before_read = 0
            self.dots_already_advanced += dots
            self.advance_dots(dots)

    def flush(self) -> None:
        """Brings the PPU up to date; call before anything reads or changes PPU state."""
        dots = self.pending_dots
        if dots:
            self.pending_dots = 0
            self.advance_dots(dots)

    def defer_dots(self, dots: int) -> None:
        self.pending_dots += dots
        if self.pending_dots >= self.dots_to_event:
            self.flush()

    def advance_cpu_cycles(self, cycles: int) -> None:
        self.flush()
        self.advance_dots(cycles * 3)

    def advance_dots(self, dots: int) -> None:
        position = self._scanline * PPU_DOTS_PER_SCANLINE + self._dot
        end = position + dots

        while True:
            frame_start = position - position % PPU_DOTS_PER_FRAME
            index = bisect_right(_EVENT_POSITIONS, position - frame_start)
            if index < len(_EVENTS):
                event_position = frame_start + _EVENT_POSITIONS[index]
            else:
                event_position = frame_start + PPU_DOTS_PER_FRAME + _EVENT_POSITIONS[0]
            if event_position > end:
                break

            position = event_position
            kind = _EVENTS[index % len(_EVENTS)][1]
            if kind >= 0:
                self._render_scanline(kind)
            elif kind == -1:
                self.frame_ready = True
                self.v_blank_status = 1
                self._update_nmi_line()
            elif kind == -4:
                if self.bg_enabled or self.spr_enabled:
                    self.bus.cartridge.mapper.clock_scanline()
            elif kind == -2:
                self.spr_zero_hit = 0
                self.spr_overflow = 0
                self.v_blank_status = 0
                self._update_nmi_line()
            elif self.bg_enabled or self.spr_enabled:
                self.scroll_v = (self.scroll_v & ~0x7BFF) | (self.scroll_t & 0x7BFF)

        self.dots_to_event = event_position - end
        self._scanline, self._dot = divmod(
            end % PPU_DOTS_PER_FRAME, PPU_DOTS_PER_SCANLINE
        )

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
        """Render a whole frame from the current scroll_t, ignoring timing."""
        saved_v = self.scroll_v
        self.scroll_v = self.scroll_t
        for y in range(FRAME_HEIGHT):
            self._render_scanline(y)
        self.scroll_v = saved_v
        return self.frame_buffer

    def _tile_row(self, palette: int, low: int, high: int) -> bytes:
        key = (palette << 16) | (low << 8) | high
        row = self._tile_rows.get(key)
        if row is None:
            palette_bits = palette << 2
            row = bytes(
                (((low >> bit) & 1) | (((high >> bit) & 1) << 1)) | palette_bits
                if ((low >> bit) | (high >> bit)) & 1
                else 0
                for bit in range(7, -1, -1)
            )
            self._tile_rows[key] = row
        return row

    def _render_scanline(self, y: int) -> None:
        color_mask = 0x30 if self.grayscale else 0x3F
        palette_cells = self.bus.palette_ram.cells
        universal_color = palette_cells[0] & color_mask
        line_start = y * FRAME_WIDTH
        line_end = line_start + FRAME_WIDTH

        if self.bg_enabled:
            self._render_background_line(y, color_mask, universal_color)
        else:
            self.frame_buffer[line_start:line_end] = (
                bytes([universal_color]) * FRAME_WIDTH
            )
            self._background_opaque[line_start:line_end] = bytes(FRAME_WIDTH)

        if self.spr_enabled:
            self._render_sprite_line(y, color_mask)

        if self.bg_enabled or self.spr_enabled:
            self._advance_scroll_y()
            self.scroll_v = (self.scroll_v & ~0x041F) | (self.scroll_t & 0x041F)

    def _advance_scroll_y(self) -> None:
        v = self.scroll_v
        if (v & 0x7000) != 0x7000:
            v += 0x1000
        else:
            v &= ~0x7000
            coarse_y = (v & 0x03E0) >> 5
            if coarse_y == 29:
                coarse_y = 0
                v ^= 0x0800
            elif coarse_y == 31:
                coarse_y = 0
            else:
                coarse_y += 1
            v = (v & ~0x03E0) | (coarse_y << 5)
        self.scroll_v = v

    def _render_background_line(
        self, y: int, color_mask: int, universal_color: int
    ) -> None:
        v = self.scroll_v
        coarse_x = v & 0x1F
        nametable = (v >> 10) & 0x03
        coarse_y = (v >> 5) & 0x1F
        fine_y = (v >> 12) & 0x07
        pattern_base = self.bg_pattern_table * 0x1000 + fine_y
        chr_data = self.bus.cartridge.chr
        nametable_cells = self.bus.ram.cells
        resolve = self.bus._resolve_nametable_mirroring
        attribute_row_shift = (coarse_y & 2) << 1

        rows: dict[int, tuple[bytearray, int, int]] = {}
        tiles: list[bytes] = []
        tile_row = self._tile_row
        for index in range(33):
            column = coarse_x + index
            table = nametable ^ ((column >> 5) & 1)
            column &= 0x1F
            row = rows.get(table)
            if row is None:
                table_address = 0x2000 + table * 0x400
                tile_base = resolve(table_address + coarse_y * 32)
                attribute_base = resolve(table_address + 0x3C0 + (coarse_y >> 2) * 8)
                row = rows[table] = (nametable_cells, tile_base, attribute_base)
            _, tile_base, attribute_base = row
            tile = nametable_cells[tile_base + column]
            attribute = nametable_cells[attribute_base + (column >> 2)]
            palette = (attribute >> (attribute_row_shift | (column & 2))) & 3
            address = pattern_base + tile * 16
            tiles.append(tile_row(palette, chr_data[address], chr_data[address + 8]))

        pixels = b"".join(tiles)[self.scroll_x : self.scroll_x + FRAME_WIDTH]
        palette_cells = self.bus.palette_ram.cells
        table_bytes = bytearray(256)
        table_bytes[0] = universal_color
        for palette in range(4):
            for pixel in range(1, 4):
                table_bytes[palette * 4 + pixel] = (
                    palette_cells[palette * 4 + pixel] & color_mask
                )

        line_start = y * FRAME_WIDTH
        line_end = line_start + FRAME_WIDTH
        self.frame_buffer[line_start:line_end] = pixels.translate(table_bytes)
        self._background_opaque[line_start:line_end] = pixels.translate(_OPAQUE_TABLE)
        if not self.show_bg_leftmost:
            self.frame_buffer[line_start : line_start + 8] = (
                bytes([universal_color]) * 8
            )
            self._background_opaque[line_start : line_start + 8] = bytes(8)

    def _render_sprite_line(self, y: int, color_mask: int) -> None:
        sprite_height = 16 if self.spr_size else 8
        oam = self.oam_memory
        visible: list[tuple[int, int]] = []
        for sprite_index in range(64):
            row = (y - (oam[sprite_index * 4] + 1)) & 0xFF
            if row < sprite_height:
                if len(visible) == 8:
                    self.spr_overflow = 1
                    break
                visible.append((sprite_index, row))

        if not visible:
            return

        palette_cells = self.bus.palette_ram.cells
        chr_data = self.bus.cartridge.chr
        line_start = y * FRAME_WIDTH
        opaque = self._background_opaque
        frame = self.frame_buffer
        occupied = bytearray(FRAME_WIDTH)

        for sprite_index, row in visible:
            base = sprite_index * 4
            tile = oam[base + 1]
            attributes = oam[base + 2]
            left = oam[base + 3]

            pattern_y = sprite_height - 1 - row if attributes & 0x80 else row
            if self.spr_size:
                pattern_table = (tile & 1) * 0x1000
                tile_index = (tile & 0xFE) + pattern_y // 8
                pattern_y %= 8
            else:
                pattern_table = self.spr_pattern_table * 0x1000
                tile_index = tile
            address = pattern_table + tile_index * 16 + pattern_y
            pixels = self._tile_row(0, chr_data[address], chr_data[address + 8])
            if attributes & 0x40:
                pixels = pixels[::-1]
            palette_base = 0x10 + (attributes & 0x03) * 4
            behind = attributes & 0x20

            for sprite_x in range(min(8, FRAME_WIDTH - left)):
                pixel = pixels[sprite_x]
                screen_x = left + sprite_x
                if pixel == 0 or (screen_x < 8 and not self.show_spr_leftmost):
                    continue

                frame_index = line_start + screen_x
                if (
                    sprite_index == 0
                    and screen_x < 255
                    and self.bg_enabled
                    and opaque[frame_index]
                ):
                    self.spr_zero_hit = 1

                if occupied[screen_x]:
                    continue
                occupied[screen_x] = 1
                if behind and opaque[frame_index]:
                    continue
                frame[frame_index] = palette_cells[palette_base + pixel] & color_mask


def ppu_builder(bus: PPUBus | None = None) -> PPU:
    return PPU(bus=bus)
