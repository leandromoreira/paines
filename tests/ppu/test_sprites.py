from paines.ppu.ppu import PPU


def set_sprite(
    ppu: PPU, index: int, y: int, tile: int, attributes: int, x: int
) -> None:
    offset = index * 4
    ppu.oam_memory[offset : offset + 4] = bytes((y, tile, attributes, x))


def hide_sprites(ppu: PPU) -> None:
    for index in range(64):
        set_sprite(ppu, index, 239, 0, 0, 0)


def test_renderer_draws_opaque_sprite_pixels_with_sprite_palette() -> None:
    ppu = PPU()
    ppu.spr_enabled = 1
    ppu.show_spr_leftmost = 1
    set_sprite(ppu, 0, 9, 1, 0, 12)
    ppu.write_vram(0x0010, 0b10000000)
    ppu.write_vram(0x3F11, 0x21)

    frame = ppu.render_background()

    assert frame[10 * 256 + 12] == 0x21
    assert frame[10 * 256 + 13] == 0


def test_renderer_applies_horizontal_and_vertical_sprite_flips() -> None:
    ppu = PPU()
    ppu.spr_enabled = 1
    ppu.show_spr_leftmost = 1
    set_sprite(ppu, 0, 9, 1, 0xC0, 12)
    ppu.write_vram(0x0010, 0b10000000)
    ppu.write_vram(0x0017, 0b00000001)
    ppu.write_vram(0x3F11, 0x21)

    frame = ppu.render_background()

    assert frame[10 * 256 + 12] == 0x21
    assert frame[17 * 256 + 19] == 0x21


def test_lower_oam_index_wins_sprite_overlap() -> None:
    ppu = PPU()
    ppu.spr_enabled = 1
    ppu.show_spr_leftmost = 1
    set_sprite(ppu, 0, 9, 1, 0, 12)
    set_sprite(ppu, 1, 9, 2, 1, 12)
    ppu.write_vram(0x0010, 0xFF)
    ppu.write_vram(0x0020, 0xFF)
    ppu.write_vram(0x3F11, 0x21)
    ppu.write_vram(0x3F15, 0x31)

    frame = ppu.render_background()

    assert frame[10 * 256 + 12] == 0x21


def test_behind_background_sprite_preserves_opaque_background() -> None:
    ppu = PPU()
    ppu.bg_enabled = 1
    ppu.spr_enabled = 1
    ppu.show_bg_leftmost = 1
    ppu.show_spr_leftmost = 1
    set_sprite(ppu, 0, 9, 1, 0x20, 0)
    ppu.write_vram(0x2020, 2)
    ppu.write_vram(0x0022, 0x80)
    ppu.write_vram(0x0010, 0x80)
    ppu.write_vram(0x3F01, 0x16)
    ppu.write_vram(0x3F11, 0x2A)

    frame = ppu.render_background()

    assert frame[10 * 256] == 0x16


def test_transparent_sprite_pixel_reveals_background() -> None:
    ppu = PPU()
    ppu.bg_enabled = 1
    ppu.spr_enabled = 1
    ppu.show_bg_leftmost = 1
    ppu.show_spr_leftmost = 1
    set_sprite(ppu, 0, 9, 1, 0, 0)
    ppu.write_vram(0x2020, 2)
    ppu.write_vram(0x0010, 0x80)
    ppu.write_vram(0x0022, 0xFF)
    ppu.write_vram(0x3F01, 0x16)
    ppu.write_vram(0x3F11, 0x2A)

    frame = ppu.render_background()

    assert frame[10 * 256] == 0x2A
    assert frame[10 * 256 + 1] == 0x16


def test_sprite_zero_hit_is_set_on_opaque_background_overlap() -> None:
    ppu = PPU()
    ppu.bg_enabled = 1
    ppu.spr_enabled = 1
    ppu.show_bg_leftmost = 1
    ppu.show_spr_leftmost = 1
    set_sprite(ppu, 0, 9, 1, 0, 20)
    ppu.write_vram(0x2022, 2)
    ppu.write_vram(0x0010, 0x80)
    ppu.write_vram(0x0022, 0xFF)

    ppu.render_background()

    assert ppu.spr_zero_hit == 1


def test_8_by_16_sprite_uses_tile_bit_for_pattern_table() -> None:
    ppu = PPU()
    ppu.spr_enabled = 1
    ppu.spr_size = 1
    ppu.show_spr_leftmost = 1
    set_sprite(ppu, 0, 9, 1, 0, 12)
    ppu.write_vram(0x1000, 0x80)
    ppu.write_vram(0x3F11, 0x21)

    frame = ppu.render_background()

    assert frame[10 * 256 + 12] == 0x21


def test_sprite_overflow_is_set_when_ninth_sprite_intersects_a_scanline() -> None:
    ppu = PPU()
    ppu.spr_enabled = 1
    hide_sprites(ppu)
    for index in range(9):
        set_sprite(ppu, index, 9, 0, 0, index * 8)

    ppu.render_background()

    assert ppu.spr_overflow == 1


def test_sprite_overflow_is_not_set_for_eight_sprites() -> None:
    ppu = PPU()
    ppu.spr_enabled = 1
    hide_sprites(ppu)
    for index in range(8):
        set_sprite(ppu, index, 9, 0, 0, index * 8)

    ppu.render_background()

    assert ppu.spr_overflow == 0


def test_sprite_y_coordinate_wraps_at_255() -> None:
    ppu = PPU()
    ppu.spr_enabled = 1
    ppu.show_spr_leftmost = 1
    set_sprite(ppu, 0, 255, 1, 0, 12)
    ppu.write_vram(0x0010, 0x80)
    ppu.write_vram(0x3F11, 0x21)

    frame = ppu.render_background()

    assert frame[12] == 0x21
