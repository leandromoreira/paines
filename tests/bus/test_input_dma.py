from paines.bus.bus import CPUBus


def test_oam_dma_copies_page_and_stalls() -> None:
    bus = CPUBus()
    for i in range(256):
        bus.write(0x0200 + i, i)
    bus.write(0x4014, 0x02)
    assert bytes(bus.ppu_mmio.ppu.oam_memory) == bytes(range(256))
    assert bus.dma_stall_cycles == 513


def test_controller_reads_buttons_serially() -> None:
    bus = CPUBus()
    bus.controller_buttons[0] = 0b10000101  # A, Select, Right
    bus.write(0x4016, 1)
    bus.write(0x4016, 0)
    bits = [bus.read(0x4016) & 1 for _ in range(10)]
    assert bits == [1, 0, 1, 0, 0, 0, 0, 1, 1, 1]


def test_controller_strobe_high_returns_a_button() -> None:
    bus = CPUBus()
    bus.controller_buttons[1] = 1
    bus.write(0x4016, 1)
    assert bus.read(0x4017) & 1 == 1
    assert bus.read(0x4017) & 1 == 1
