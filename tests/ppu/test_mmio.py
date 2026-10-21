from paines.bus.bus import CPUBus


def test_vram_access_uses_the_cpu_bus_cartridge() -> None:
    bus = CPUBus()

    bus.write(0x2006, 0x00)
    bus.write(0x2006, 0x00)
    bus.write(0x200F, 0xA5)

    assert bus.cartridge.read_chr(0) == 0xA5
    assert bus.ppu_mmio.ppu.scroll_v == 1


def test_vram_data_reads_are_buffered_and_increment_address() -> None:
    bus = CPUBus()
    ppu = bus.ppu_mmio.ppu
    ppu.write_vram(0x2000, 0x5A)
    bus.write(0x2006, 0x20)
    bus.write(0x2006, 0x00)

    assert bus.read(0x2007) == 0
    assert bus.read(0x2007) == 0x5A
    assert ppu.scroll_v == 0x2002


def test_vram_data_writes_honor_the_increment_control() -> None:
    bus = CPUBus()
    ppu = bus.ppu_mmio.ppu
    bus.write(0x2000, 0x04)
    bus.write(0x2006, 0x20)
    bus.write(0x2006, 0x00)

    bus.write(0x2007, 0xA5)

    assert ppu.read_vram(0x2000) == 0xA5
    assert ppu.scroll_v == 0x2020
