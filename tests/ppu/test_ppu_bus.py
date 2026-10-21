from paines.bus.ppu import PPUBus


def test_palette_ram_reads_and_writes_all_32_entries() -> None:
    bus = PPUBus()

    bus.write(0x3F00, 0x2A)
    bus.write(0x3F1F, 0x15)

    assert bus.read(0x3F00) == 0x2A
    assert bus.read(0x3F1F) == 0x15


def test_palette_ram_mirrors_every_32_bytes() -> None:
    bus = PPUBus()

    bus.write(0x3F05, 0x12)

    assert bus.read(0x3F25) == 0x12
    assert bus.read(0x3F45) == 0x12
    assert bus.read(0x3FFF) == bus.read(0x3F1F)


def test_sprite_universal_background_entries_alias_background_entries() -> None:
    bus = PPUBus()

    for background, sprite in (
        (0x3F00, 0x3F10),
        (0x3F04, 0x3F14),
        (0x3F08, 0x3F18),
        (0x3F0C, 0x3F1C),
    ):
        bus.write(background, 0x25)
        assert bus.read(sprite) == 0x25
        bus.write(sprite, 0x16)
        assert bus.read(background) == 0x16


def test_palette_writes_store_six_bit_color_values() -> None:
    bus = PPUBus()

    bus.write(0x3F02, 0xFF)

    assert bus.read(0x3F02) == 0x3F
