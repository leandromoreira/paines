from pathlib import Path

from paines.bus.bus import CPUBus
from paines.cartridge.cartridge import Cartridge
from paines.cartridge.mappers import is_supported


def make_rom(
    tmp_path: Path, mapper: int, prg_banks: int, chr_banks: int, flags_6: int = 0
) -> Cartridge:
    header = bytearray(16)
    header[:4] = b"NES\x1a"
    header[4] = prg_banks
    header[5] = chr_banks
    header[6] = (mapper & 0x0F) << 4 | flags_6
    header[7] = mapper & 0xF0
    prg = b"".join(bytes([bank]) * 0x4000 for bank in range(prg_banks))
    # each 4 KB CHR page is filled with its own page number
    chr_rom = b"".join(bytes([page]) * 0x1000 for page in range(chr_banks * 2))
    path = tmp_path / "rom.nes"
    path.write_bytes(bytes(header) + prg + chr_rom)
    cartridge = Cartridge()
    cartridge.load(str(path))
    return cartridge


def serial_write(cartridge: Cartridge, address: int, value: int) -> None:
    for bit in range(5):
        cartridge.write(address, (value >> bit) & 1)


def test_supported_mappers() -> None:
    assert all(is_supported(mapper) for mapper in (0, 1, 2, 3, 4))
    assert not is_supported(5)


def test_nrom_16k_mirrors_and_32k_does_not(tmp_path: Path) -> None:
    sixteen = make_rom(tmp_path, 0, 1, 1)
    assert sixteen.read(0x8000, 0) == sixteen.read(0xC000, 0) == 0
    thirty_two = make_rom(tmp_path, 0, 2, 1)
    assert (thirty_two.read(0x8000, 0), thirty_two.read(0xC000, 0)) == (0, 1)


def test_nrom_ignores_register_writes_but_allows_patching(tmp_path: Path) -> None:
    cartridge = make_rom(tmp_path, 0, 2, 1)
    cartridge.write(0xFFFA, 0x42)
    assert cartridge.read(0xFFFA, 0) == 0x42
    assert cartridge.read(0x8000, 0) == 0


def test_uxrom_switches_low_bank_and_fixes_last(tmp_path: Path) -> None:
    cartridge = make_rom(tmp_path, 2, 8, 0)
    assert cartridge.read(0x8000, 0) == 0
    assert cartridge.read(0xC000, 0) == 7

    cartridge.write(0x8000, 5)

    assert cartridge.read(0x8000, 0) == 5
    assert cartridge.read(0xBFFF, 0) == 5
    assert cartridge.read(0xC000, 0) == 7


def test_uxrom_uses_chr_ram(tmp_path: Path) -> None:
    cartridge = make_rom(tmp_path, 2, 2, 0)
    cartridge.write_chr(0x0123, 0x9A)
    assert cartridge.read_chr(0x0123) == 0x9A


def test_cnrom_switches_8k_chr_banks(tmp_path: Path) -> None:
    cartridge = make_rom(tmp_path, 3, 2, 4)
    assert (cartridge.read_chr(0x0000), cartridge.read_chr(0x1000)) == (0, 1)

    cartridge.write(0x8000, 2)
    assert (cartridge.read_chr(0x0000), cartridge.read_chr(0x1FFF)) == (4, 5)

    cartridge.write(0x8000, 3)
    assert (cartridge.read_chr(0x0000), cartridge.read_chr(0x1000)) == (6, 7)
    assert cartridge.read(0x8000, 0) == 0
    assert cartridge.read(0xC000, 0) == 1


def test_mmc1_powers_on_with_last_bank_fixed(tmp_path: Path) -> None:
    cartridge = make_rom(tmp_path, 1, 8, 2)
    assert cartridge.read(0x8000, 0) == 0
    assert cartridge.read(0xC000, 0) == 7


def test_mmc1_needs_five_writes_to_commit_a_register(tmp_path: Path) -> None:
    cartridge = make_rom(tmp_path, 1, 8, 2)
    for _ in range(4):
        cartridge.write(0xE000, 1)
    assert cartridge.read(0x8000, 0) == 0

    cartridge.write(0xE000, 1)  # 5th write: bank 0b11111 & 0xF = 15 -> 7 (wraps)
    assert cartridge.read(0x8000, 0) == 15 % 8


def test_mmc1_reset_bit_clears_shift_register_and_locks_prg_mode(tmp_path: Path) -> None:
    cartridge = make_rom(tmp_path, 1, 8, 2)
    serial_write(cartridge, 0x8000, 0b00000)  # 32 KB mode
    cartridge.write(0xE000, 1)
    cartridge.write(0xE000, 1)
    cartridge.write(0x8000, 0x80)  # reset: drops the two pending bits, control |= 0x0C

    serial_write(cartridge, 0xE000, 3)

    assert cartridge.read(0x8000, 0) == 3
    assert cartridge.read(0xC000, 0) == 7


def test_mmc1_prg_modes(tmp_path: Path) -> None:
    cartridge = make_rom(tmp_path, 1, 8, 2)

    serial_write(cartridge, 0x8000, 0b00000)  # 32 KB mode ignores the low bit
    serial_write(cartridge, 0xE000, 5)
    assert (cartridge.read(0x8000, 0), cartridge.read(0xC000, 0)) == (4, 5)

    serial_write(cartridge, 0x8000, 0b01000)  # first bank fixed, $C000 switchable
    serial_write(cartridge, 0xE000, 6)
    assert (cartridge.read(0x8000, 0), cartridge.read(0xC000, 0)) == (0, 6)

    serial_write(cartridge, 0x8000, 0b01100)  # $8000 switchable, last bank fixed
    serial_write(cartridge, 0xE000, 2)
    assert (cartridge.read(0x8000, 0), cartridge.read(0xC000, 0)) == (2, 7)


def test_mmc1_chr_modes(tmp_path: Path) -> None:
    cartridge = make_rom(tmp_path, 1, 2, 4)  # 8 CHR pages

    serial_write(cartridge, 0x8000, 0b01100)  # 8 KB CHR mode
    serial_write(cartridge, 0xA000, 5)  # low bit ignored: pages 4 and 5
    assert (cartridge.read_chr(0x0000), cartridge.read_chr(0x1000)) == (4, 5)

    serial_write(cartridge, 0x8000, 0b11100)  # two 4 KB banks
    serial_write(cartridge, 0xA000, 6)
    serial_write(cartridge, 0xC000, 1)
    assert (cartridge.read_chr(0x0000), cartridge.read_chr(0x1000)) == (6, 1)


def test_mmc1_controls_mirroring(tmp_path: Path) -> None:
    cartridge = make_rom(tmp_path, 1, 2, 1)
    bus = CPUBus(cartridge=cartridge)
    ppu_bus = bus.ppu_mmio.ppu.bus

    for control, expected in ((2, 1), (3, 0), (0, 2), (1, 3)):
        serial_write(cartridge, 0x8000, 0b01100 | control)
        assert cartridge.nametable_mirroring == expected

    serial_write(cartridge, 0x8000, 0b01100)  # single screen, lower bank
    ppu_bus.write(0x2000, 0x11)
    assert ppu_bus.read(0x2C00) == 0x11
    assert ppu_bus.read(0x2400) == 0x11

    serial_write(cartridge, 0x8000, 0b01101)  # single screen, upper bank
    assert ppu_bus.read(0x2000) == 0


def test_mmc1_prg_ram_is_readable_and_writable(tmp_path: Path) -> None:
    cartridge = make_rom(tmp_path, 1, 2, 1)
    cartridge.write(0x6000, 0xAB)
    assert cartridge.read(0x6000, 0) == 0xAB
    assert cartridge.read(0x7FFF, 0) == 0


def test_prg_ram_is_open_bus_without_mapper_support(tmp_path: Path) -> None:
    cartridge = make_rom(tmp_path, 0, 1, 1)
    cartridge.write(0x6000, 0xAB)
    assert cartridge.read(0x6000, 0xFE) == 0xFE


def test_trainer_is_skipped(tmp_path: Path) -> None:
    header = bytearray(16)
    header[:4] = b"NES\x1a"
    header[4] = 1
    header[6] = 0b100
    path = tmp_path / "trainer.nes"
    path.write_bytes(bytes(header) + b"\xee" * 512 + b"\x07" * 0x4000)
    cartridge = Cartridge()
    cartridge.load(str(path))
    assert cartridge.read(0x8000, 0) == 7


def test_mmc1_surom_selects_256k_half_with_chr_bit_4(tmp_path: Path) -> None:
    cartridge = make_rom(tmp_path, 1, 32, 0)
    assert (cartridge.read(0x8000, 0), cartridge.read(0xC000, 0)) == (0, 15)

    serial_write(cartridge, 0xA000, 0x10)

    assert (cartridge.read(0x8000, 0), cartridge.read(0xC000, 0)) == (16, 31)
    serial_write(cartridge, 0xE000, 3)
    assert cartridge.read(0x8000, 0) == 19


def make_mmc3(tmp_path: Path, prg_pages: int = 16, chr_pages: int = 64) -> Cartridge:
    """prg_pages are 8 KB, chr_pages are 1 KB; every page holds its own index."""
    header = bytearray(16)
    header[:4] = b"NES\x1a"
    header[4] = prg_pages // 2
    header[5] = chr_pages // 8
    header[6] = 0x40  # mapper 4
    prg = b"".join(bytes([page]) * 0x2000 for page in range(prg_pages))
    chr_rom = b"".join(bytes([page]) * 0x400 for page in range(chr_pages))
    path = tmp_path / "mmc3.nes"
    path.write_bytes(bytes(header) + prg + chr_rom)
    cartridge = Cartridge()
    cartridge.load(str(path))
    return cartridge


def select(cartridge: Cartridge, register: int, value: int, flags: int = 0) -> None:
    cartridge.write(0x8000, register | flags)
    cartridge.write(0x8001, value)


def prg_pages(cartridge: Cartridge) -> tuple[int, ...]:
    return tuple(cartridge.read(0x8000 + 0x2000 * slot, 0) for slot in range(4))


def chr_pages(cartridge: Cartridge) -> tuple[int, ...]:
    return tuple(cartridge.read_chr(0x400 * slot) for slot in range(8))


def test_mmc3_powers_on_with_last_two_pages_fixed(tmp_path: Path) -> None:
    cartridge = make_mmc3(tmp_path)
    assert prg_pages(cartridge)[2:] == (14, 15)


def test_mmc3_prg_modes(tmp_path: Path) -> None:
    cartridge = make_mmc3(tmp_path)
    select(cartridge, 6, 3)
    select(cartridge, 7, 5)
    assert prg_pages(cartridge) == (3, 5, 14, 15)

    select(cartridge, 6, 3, flags=0x40)  # swap: R6 moves to $C000
    select(cartridge, 7, 5, flags=0x40)
    assert prg_pages(cartridge) == (14, 5, 3, 15)


def test_mmc3_chr_modes(tmp_path: Path) -> None:
    cartridge = make_mmc3(tmp_path)
    for register, value in enumerate((10, 20, 30, 31, 32, 33)):
        select(cartridge, register, value)
    # R0/R1 are 2 KB banks: the low bit is ignored
    assert chr_pages(cartridge) == (10, 11, 20, 21, 30, 31, 32, 33)

    select(cartridge, 0, 10, flags=0x80)  # inverted: 1 KB banks at $0000
    assert chr_pages(cartridge) == (30, 31, 32, 33, 10, 11, 20, 21)


def test_mmc3_mirroring_register(tmp_path: Path) -> None:
    cartridge = make_mmc3(tmp_path)
    cartridge.write(0xA000, 0)
    assert cartridge.nametable_mirroring == 1  # vertical
    cartridge.write(0xA000, 1)
    assert cartridge.nametable_mirroring == 0  # horizontal


def test_mmc3_prg_ram(tmp_path: Path) -> None:
    cartridge = make_mmc3(tmp_path)
    cartridge.write(0x6000, 0x5A)
    assert cartridge.read(0x6000, 0) == 0x5A


def clock(cartridge: Cartridge, scanlines: int) -> None:
    for _ in range(scanlines):
        cartridge.mapper.clock_scanline()


def test_mmc3_irq_fires_after_latch_plus_one_scanlines(tmp_path: Path) -> None:
    cartridge = make_mmc3(tmp_path)
    cartridge.write(0xC000, 3)  # latch
    cartridge.write(0xC001, 0)  # reload
    cartridge.write(0xE001, 0)  # enable

    clock(cartridge, 3)
    assert not cartridge.irq_pending
    clock(cartridge, 1)
    assert cartridge.irq_pending

    cartridge.write(0xE000, 0)  # disable + acknowledge
    assert not cartridge.irq_pending
    clock(cartridge, 8)
    assert not cartridge.irq_pending


def test_mmc3_irq_counter_reloads_automatically(tmp_path: Path) -> None:
    cartridge = make_mmc3(tmp_path)
    cartridge.write(0xC000, 2)
    cartridge.write(0xE001, 0)

    clock(cartridge, 1)  # counter was 0: reloads to 2
    clock(cartridge, 2)  # 1, 0 -> fires
    assert cartridge.irq_pending
    cartridge.irq_pending = False
    clock(cartridge, 1)  # reload
    clock(cartridge, 2)
    assert cartridge.irq_pending


def test_mmc3_irq_with_latch_zero_fires_every_scanline(tmp_path: Path) -> None:
    cartridge = make_mmc3(tmp_path)
    cartridge.write(0xC000, 0)
    cartridge.write(0xE001, 0)
    clock(cartridge, 1)
    assert cartridge.irq_pending
