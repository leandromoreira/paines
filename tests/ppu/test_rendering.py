from paines.ppu.ppu import FRAME_HEIGHT, FRAME_WIDTH, PPU
from paines.ppu.mmio import PPUMMIO


def test_background_renderer_decodes_pattern_planes_and_attribute_palette() -> None:
    ppu = PPU()
    ppu.bg_enabled = 1
    ppu.show_bg_leftmost = 1
    ppu.write_vram(0x2000, 1)
    ppu.write_vram(0x23C0, 0b11)
    ppu.write_vram(0x0010, 0b10000000)
    ppu.write_vram(0x0018, 0b01000000)
    ppu.write_vram(0x3F00, 0x0F)
    ppu.write_vram(0x3F0D, 0x21)
    ppu.write_vram(0x3F0E, 0x31)

    frame = ppu.render_background()

    assert len(frame) == FRAME_WIDTH * FRAME_HEIGHT
    assert frame[0] == 0x21
    assert frame[1] == 0x31
    assert frame[2] == 0x0F


def test_background_renderer_uses_selected_pattern_table() -> None:
    ppu = PPU()
    ppu.bg_enabled = 1
    ppu.show_bg_leftmost = 1
    ppu.bg_pattern_table = 1
    ppu.write_vram(0x2000, 1)
    ppu.write_vram(0x1010, 0b10000000)
    ppu.write_vram(0x3F01, 0x2A)

    frame = ppu.render_background()

    assert frame[0] == 0x2A


def test_background_renderer_fills_backdrop_when_disabled() -> None:
    ppu = PPU()
    ppu.write_vram(0x3F00, 0x2B)

    frame = ppu.render_background()

    assert frame[0] == 0x2B
    assert frame[-1] == 0x2B
    assert len(frame) == FRAME_WIDTH * FRAME_HEIGHT


def test_background_renderer_clips_leftmost_eight_pixels_when_disabled() -> None:
    ppu = PPU()
    ppu.bg_enabled = 1
    ppu.show_bg_leftmost = 0
    ppu.write_vram(0x2000, 1)
    ppu.write_vram(0x0010, 0xFF)
    ppu.write_vram(0x3F00, 0x0F)
    ppu.write_vram(0x3F01, 0x21)

    frame = ppu.render_background()

    assert frame[0] == 0x0F
    assert frame[7] == 0x0F


def test_background_renderer_applies_fine_horizontal_scroll() -> None:
    ppu = PPU()
    ppu.bg_enabled = 1
    ppu.show_bg_leftmost = 1
    ppu.write_vram(0x2000, 1)
    ppu.write_vram(0x2001, 2)
    ppu.write_vram(0x0010, 0b10000000)
    ppu.write_vram(0x0028, 0xFF)
    ppu.write_vram(0x3F00, 0x0F)
    ppu.write_vram(0x3F01, 0x21)
    ppu.write_vram(0x3F02, 0x31)
    ppu.scroll_x = 1

    frame = ppu.render_background()

    assert frame[0] == 0x0F
    assert frame[7] == 0x31


def test_background_renderer_applies_coarse_vertical_scroll() -> None:
    ppu = PPU()
    ppu.bg_enabled = 1
    ppu.show_bg_leftmost = 1
    ppu.write_vram(0x2000, 1)
    ppu.write_vram(0x2020, 2)
    ppu.write_vram(0x0010, 0xFF)
    ppu.write_vram(0x0028, 0xFF)
    ppu.write_vram(0x3F01, 0x21)
    ppu.write_vram(0x3F02, 0x31)
    ppu.scroll_t = 1 << 5

    frame = ppu.render_background()

    assert frame[0] == 0x31


def test_background_renderer_scrolls_across_nametable_boundary() -> None:
    ppu = PPU()
    ppu.bg_enabled = 1
    ppu.show_bg_leftmost = 1
    ppu.bus.cartridge.nametable_mirroring = 1
    ppu.write_vram(0x201F, 1)
    ppu.write_vram(0x2400, 2)
    ppu.write_vram(0x0010, 0xFF)
    ppu.write_vram(0x0028, 0xFF)
    ppu.write_vram(0x3F01, 0x21)
    ppu.write_vram(0x3F02, 0x31)
    ppu.scroll_t = 31
    ppu.scroll_x = 7

    frame = ppu.render_background()

    assert frame[0] == 0x21
    assert frame[1] == 0x31


def test_control_register_selects_renderer_nametable() -> None:
    ppu = PPU()
    ppu.bg_enabled = 1
    ppu.show_bg_leftmost = 1
    ppu.bus.cartridge.nametable_mirroring = 1
    ppu.write_vram(0x2400, 1)
    ppu.write_vram(0x0010, 0xFF)
    ppu.write_vram(0x3F01, 0x2A)

    mmio = PPUMMIO(ppu)
    mmio.write(0x2000, 1)

    frame = ppu.render_background()

    assert frame[0] == 0x2A
