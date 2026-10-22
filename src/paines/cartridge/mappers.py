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


MAPPERS: dict[int, type[Mapper]] = {0: NROM, 1: MMC1, 2: UxROM, 3: CNROM}


def is_supported(mapper_id: int) -> bool:
    return mapper_id in MAPPERS
