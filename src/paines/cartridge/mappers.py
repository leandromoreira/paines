from __future__ import annotations

from typing import TYPE_CHECKING

from paines.types import U16, U8

if TYPE_CHECKING:
    from paines.cartridge.cartridge import Cartridge

# Nametable mirroring modes understood by PPUBus.
HORIZONTAL = 0
VERTICAL = 1
SINGLE_SCREEN_LOWER = 2
SINGLE_SCREEN_UPPER = 3


class Mapper:
    """Decides which cartridge banks are visible; the cartridge owns the data."""

    uses_prg_ram = False

    def __init__(self, cartridge: Cartridge) -> None:
        self.cartridge = cartridge
        self.reset()

    def reset(self) -> None:
        cartridge = self.cartridge
        cartridge.map_prg(0, 0)
        cartridge.map_prg(1, 1)
        cartridge.map_chr(0, 0)
        cartridge.map_chr(1, 1)

    def write(self, address: U16, value: U8) -> None:
        """Handle a CPU write to $8000-$FFFF."""

    def clock_scanline(self) -> None:
        """Called once per rendered scanline (stands in for the PPU A12 rising edge)."""


class NROM(Mapper):
    # https://www.nesdev.org/wiki/NROM
    def write(self, address: U16, value: U8) -> None:
        # NROM has no registers; the write is kept so a ROM image can be patched in tests.
        self.cartridge.patch_prg(address, value)


class MMC1(Mapper):
    # https://www.nesdev.org/wiki/MMC1
    uses_prg_ram = True
    # control register bits 0-1 -> mirroring mode
    _MIRRORING = (SINGLE_SCREEN_LOWER, SINGLE_SCREEN_UPPER, VERTICAL, HORIZONTAL)

    def reset(self) -> None:
        self.shift = 0x10  # a set bit 4 marks an empty 5-bit shift register
        self.control = 0x0C
        self.chr_bank_0 = 0
        self.chr_bank_1 = 0
        self.prg_bank = 0
        self._apply()

    def write(self, address: U16, value: U8) -> None:
        if value & 0x80:
            self.shift = 0x10
            self.control |= 0x0C
            self._apply()
            return

        complete = self.shift & 1
        self.shift = (self.shift >> 1) | ((value & 1) << 4)
        if not complete:
            return

        register = (address >> 13) & 0b11
        if register == 0:
            self.control = self.shift
        elif register == 1:
            self.chr_bank_0 = self.shift
        elif register == 2:
            self.chr_bank_1 = self.shift
        else:
            self.prg_bank = self.shift & 0x0F
        self.shift = 0x10
        self._apply()

    def _apply(self) -> None:
        cartridge = self.cartridge
        cartridge.nametable_mirroring = self._MIRRORING[self.control & 0b11]

        # SUROM (512 KB) boards use CHR bit 4 to pick which 256 KB half of PRG is visible.
        surom = cartridge.prg_banks > 16
        outer = self.chr_bank_0 & 0x10 if surom else 0
        last = outer | 0x0F if surom else cartridge.prg_banks - 1
        first = outer
        prg_bank = outer | self.prg_bank

        prg_mode = (self.control >> 2) & 0b11
        if prg_mode <= 1:
            cartridge.map_prg(0, prg_bank & ~1)
            cartridge.map_prg(1, prg_bank | 1)
        elif prg_mode == 2:
            cartridge.map_prg(0, first)
            cartridge.map_prg(1, prg_bank)
        else:
            cartridge.map_prg(0, prg_bank)
            cartridge.map_prg(1, last)

        if self.control & 0x10:
            cartridge.map_chr(0, self.chr_bank_0)
            cartridge.map_chr(1, self.chr_bank_1)
        else:
            cartridge.map_chr(0, self.chr_bank_0 & ~1)
            cartridge.map_chr(1, self.chr_bank_0 | 1)


class UxROM(Mapper):
    # https://www.nesdev.org/wiki/UxROM
    def reset(self) -> None:
        super().reset()
        self.cartridge.map_prg(1, self.cartridge.prg_banks - 1)

    def write(self, address: U16, value: U8) -> None:
        self.cartridge.map_prg(0, value)


class CNROM(Mapper):
    # https://www.nesdev.org/wiki/INES_Mapper_003
    def write(self, address: U16, value: U8) -> None:
        bank = (value & 0xFF) * 2
        self.cartridge.map_chr(0, bank)
        self.cartridge.map_chr(1, bank + 1)


class MMC3(Mapper):
    # https://www.nesdev.org/wiki/MMC3
    uses_prg_ram = True

    def reset(self) -> None:
        self.bank_select = 0
        self.registers = [0, 2, 4, 5, 6, 7, 0, 1]
        self.irq_latch = 0
        self.irq_counter = 0
        self.irq_reload = False
        self.irq_enabled = False
        self.cartridge.irq_pending = False
        self._apply()

    def write(self, address: U16, value: U8) -> None:
        even = not address & 1
        region = (address >> 13) & 0b11
        if region == 0:  # $8000-$9FFF
            if even:
                self.bank_select = value
            else:
                self.registers[self.bank_select & 7] = value
            self._apply()
        elif region == 1:  # $A000-$BFFF
            if even:
                self.cartridge.nametable_mirroring = (
                    HORIZONTAL if value & 1 else VERTICAL
                )
            # odd: PRG-RAM protect, ignored so games with battery RAM keep working
        elif region == 2:  # $C000-$DFFF
            if even:
                self.irq_latch = value
            else:
                self.irq_counter = 0
                self.irq_reload = True
        else:  # $E000-$FFFF
            self.irq_enabled = not even
            if even:
                self.cartridge.irq_pending = False

    def clock_scanline(self) -> None:
        if self.irq_counter == 0 or self.irq_reload:
            self.irq_counter = self.irq_latch
            self.irq_reload = False
        else:
            self.irq_counter -= 1
        if self.irq_counter == 0 and self.irq_enabled:
            self.cartridge.irq_pending = True

    def _apply(self) -> None:
        cartridge = self.cartridge
        registers = self.registers
        last = max(len(cartridge.prg) // 0x2000, 1) - 1

        if self.bank_select & 0x40:
            cartridge.map_prg_8k(0, last - 1)
            cartridge.map_prg_8k(2, registers[6] & 0x3F)
        else:
            cartridge.map_prg_8k(0, registers[6] & 0x3F)
            cartridge.map_prg_8k(2, last - 1)
        cartridge.map_prg_8k(1, registers[7] & 0x3F)
        cartridge.map_prg_8k(3, last)

        # R0/R1 are 2 KB banks (low bit ignored); R2-R5 are 1 KB banks.
        r0, r1 = registers[0] & ~1, registers[1] & ~1
        layout = [
            r0,
            r0 | 1,
            r1,
            r1 | 1,
            registers[2],
            registers[3],
            registers[4],
            registers[5],
        ]
        if self.bank_select & 0x80:
            layout = layout[4:] + layout[:4]
        for slot, bank in enumerate(layout):
            cartridge.map_chr_1k(slot, bank)


MAPPERS: dict[int, type[Mapper]] = {0: NROM, 1: MMC1, 2: UxROM, 3: CNROM, 4: MMC3}


def is_supported(mapper_id: int) -> bool:
    return mapper_id in MAPPERS
