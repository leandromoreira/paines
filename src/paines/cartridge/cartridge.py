from paines.cartridge.mappers import MAPPERS, NROM, Mapper
from paines.types import U16, U8, U4, U2

# https://problemkaputt.de/everynes.htm#techdata
#   4018h-5FFFh   Cartridge Expansion Area almost 8K
#   6000h-7FFFh   Cartridge SRAM Area 8K
#   8000h-FFFFh   Cartridge PRG-ROM Area 32K
CPU_PRG_START: U16 = 0x8000
SRAM_START: U16 = 0x6000
SRAM_END: U16 = 0x7FFF
SRAM_MASK: U16 = SRAM_END - SRAM_START
ONE_PRG_BANK: U16 = 0x4000
ONE_CHR_BANK: U16 = 0x2000
CHR_PAGE: U16 = 0x1000
PRG_PAGE_8K: U16 = 0x2000
CHR_PAGE_1K: U16 = 0x0400
TRAINER_SIZE = 512


class Cartridge:
    # https://www.nesdev.org/wiki/INES#iNES_file_format
    def __init__(self) -> None:
        self.prg: bytearray = bytearray()
        self.chr: bytearray = bytearray()
        self.magic_id: bytes = b""
        self.prg_size: U8 = 0
        self.chr_size: U8 = 0
        self.chr_is_ram: bool = True
        self.flags_6: U8 = 0
        self.has_battery_sram: bool = False
        self.nametable_mirroring: U2 = 0
        self.flags_7: U8 = 0
        self.mapper_id: U8 = 0
        self.prg_ram_size: U8 = 0
        self.flags_9: U8 = 0
        self.flags_10: U8 = 0
        self.unused: bytes = b""
        self.chr = bytearray(ONE_CHR_BANK)  # the 8 KB the PPU currently sees
        self.chr_rom = bytearray()
        self.sram = bytearray(SRAM_END - SRAM_START + 1)
        self.prg_banks = 1
        # Start of the 8 KB PRG page visible at $8000, $A000, $C000 and $E000.
        self.prg_offsets = [0, PRG_PAGE_8K, ONE_PRG_BANK, ONE_PRG_BANK + PRG_PAGE_8K]
        self.irq_pending = False
        self.mapper: Mapper = NROM(self)

    def load(self, file: str) -> None:
        with open(file, "rb") as rom:
            header = rom.read(16)
            self.magic_id = header[0:4]
            self.prg_size = header[4]
            self.chr_size = header[5]
            self.flags_6 = header[6]
            self.flags_7 = header[7]
            self.prg_ram_size = header[8]
            self.flags_9 = header[9]
            self.flags_10 = header[10]
            self.unused = header[11:16]

            self.has_battery_sram = bool(self.flags_6 & 0x02)
            self.nametable_mirroring = self.flags_6 & 0b1

            low_mapper_id: U4 = self.flags_6 >> 4
            high_mapper_id: U4 = self.flags_7 >> 4
            self.mapper_id = (high_mapper_id << 4) | low_mapper_id

            if self.flags_6 & 0b100:
                rom.seek(TRAINER_SIZE, 1)
            self.prg = bytearray(rom.read(ONE_PRG_BANK * self.prg_size))
            self.chr_is_ram = self.chr_size == 0
            chr_data = rom.read(ONE_CHR_BANK * self.chr_size)
            self.chr_rom = bytearray(chr_data)
            self.chr = (
                bytearray(chr_data[:ONE_CHR_BANK])
                if chr_data
                else bytearray(ONE_CHR_BANK)
            )
            self.sram = bytearray(SRAM_END - SRAM_START + 1)
            self.prg_banks = max(self.prg_size, 1)
            # Unsupported mappers fall back to NROM; the CLI rejects them before running.
            self.mapper = MAPPERS.get(self.mapper_id, NROM)(self)

    @property
    def has_prg_ram(self) -> bool:
        return self.has_battery_sram or self.mapper.uses_prg_ram

    def map_prg(self, slot: int, bank: int) -> None:
        """Show 16 KB PRG bank `bank` in CPU window `slot` (0: $8000, 1: $C000)."""
        start = (bank % self.prg_banks) * ONE_PRG_BANK
        self.prg_offsets[slot * 2] = start
        self.prg_offsets[slot * 2 + 1] = start + PRG_PAGE_8K

    def map_prg_8k(self, slot: int, bank: int) -> None:
        """Show 8 KB PRG page `bank` in CPU window `slot` (0: $8000, 1: $A000, 2: $C000, 3: $E000)."""
        pages = max(len(self.prg) // PRG_PAGE_8K, 1)
        self.prg_offsets[slot] = (bank % pages) * PRG_PAGE_8K

    def map_chr_1k(self, slot: int, bank: int) -> None:
        """Show 1 KB CHR-ROM page `bank` in PPU window `slot` (0-7, $0400 each)."""
        if self.chr_is_ram:
            return
        pages = max(len(self.chr_rom) // CHR_PAGE_1K, 1)
        source = (bank % pages) * CHR_PAGE_1K
        target = slot * CHR_PAGE_1K
        self.chr[target : target + CHR_PAGE_1K] = self.chr_rom[
            source : source + CHR_PAGE_1K
        ]

    def map_chr(self, slot: int, bank: int) -> None:
        """Show 4 KB CHR-ROM page `bank` in PPU window `slot` (0: $0000, 1: $1000)."""
        if self.chr_is_ram:
            return
        pages = max(len(self.chr_rom) // CHR_PAGE, 1)
        source = (bank % pages) * CHR_PAGE
        target = slot * CHR_PAGE
        self.chr[target : target + CHR_PAGE] = self.chr_rom[source : source + CHR_PAGE]

    def patch_prg(self, address: U16, value: U8) -> None:
        self.prg[self.prg_offsets[(address >> 13) & 3] + (address & 0x1FFF)] = value

    def read(self, address: U16, open_bus: U8) -> U8:
        if address >= 0x8000:
            return self.prg[self.prg_offsets[(address >> 13) & 3] + (address & 0x1FFF)]
        if address >= SRAM_START and self.has_prg_ram:
            return self.sram[(address - SRAM_START) & SRAM_MASK]
        return open_bus

    def write(self, address: U16, value: U8) -> None:
        if address >= 0x8000:
            self.mapper.write(address, value)
        elif address >= SRAM_START and self.has_prg_ram:
            self.sram[(address - SRAM_START) & SRAM_MASK] = value

    def read_chr(self, address: U16) -> U8:
        if address <= 0x1FFF:
            return self.chr[address]
        return 0x0

    def write_chr(self, address: U16, value: U8) -> None:
        if self.chr_is_ram and address <= 0x1FFF:
            self.chr[address] = value


def cartridge_builder() -> Cartridge:
    return Cartridge()
