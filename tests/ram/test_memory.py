from paines.ram.memory import RAM


def test_memory_simple_write_and_read() -> None:
    mem = RAM(0x800, 0x0000)
    mem.write(0x200, 0xA2)
    assert mem.read(0x200) == 0xA2


def test_memory_mirrored_write_and_read() -> None:
    mem = RAM(0x800, 0x0000)
    mem.write(0x0800, 0xA2)
    assert mem.read(0x0000) == 0xA2


def test_memory_simple_write_and_read_under_a_byte() -> None:
    mem = RAM(0x800, 0x0000)
    mem.write(0x200, 0x0FA2)
    assert mem.read(0x200) == 0xA2
