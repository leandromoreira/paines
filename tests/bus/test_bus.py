from paines.bus.bus import CPUBus

def test_memory_simple_write_and_read() -> None:
    cpu_bus = CPUBus()
    cpu_bus.write(0x200, 0xA2)
    assert cpu_bus.read(0x200) == 0xA2

def test_memory_mirrored_write_and_read() -> None:
    cpu_bus = CPUBus()
    cpu_bus.write(0x0800, 0xA2)
    assert cpu_bus.read(0x0000) == 0xA2
