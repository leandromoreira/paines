from paines.types import U16, U8
# https://problemkaputt.de/everynes.htm#techdata
#   4018h-5FFFh   Cartridge Expansion Area almost 8K
#   6000h-7FFFh   Cartridge SRAM Area 8K
#   8000h-FFFFh   Cartridge PRG-ROM Area 32K
CPU_PRG_START :U16 = 0x8000
SRAM_START :U16 = 0x6000
SRAM_END :U16 = 0x7FFF
ONE_PRG_BANK :U16 = 0x4000
class Cartridge:
    # https://www.nesdev.org/wiki/INES#iNES_file_format
    def __init__(self) -> None:
        self.prg :list[U8] = []
        self.chr :list[U8] = []
        self.magic_id :bytes = b""
        self.prg_size :U8 = 0
        self.chr_size :U8 = 0
        self.flags_6 :U8 = 0
        self.has_battery_sram :bool = bool(self.flags_6 & 0x02)
        self.flags_7 :U8 = 0
        self.prg_ram_size :U8 = 0
        self.flags_9 :U8 = 0
        self.flags_10 :U8 = 0
        self.unused :bytes = b""
        self.prg_mask :U16 = 0xFFFF

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

            self.prg = list(rom.read(ONE_PRG_BANK * self.prg_size))
            self.sram = [0] * (SRAM_END - SRAM_START + 1)
            if self.prg_size == 1:
                self.prg_mask = (ONE_PRG_BANK * self.prg_size) - 1
            else:
                # TODO: come back to check for mappers
                self.prg_mask = (ONE_PRG_BANK * 2) - 1

    def read(self, address: U16, open_bus: U8) -> U8:
        if address >= 0x8000:
            return self.prg[(address - CPU_PRG_START) & self.prg_mask]
        if address >= 0x6000 and self.has_battery_sram:
            # TODO: to implement
            return self.sram[(address - SRAM_START) & SRAM_END]
        return open_bus

    def write(self, address: U16, value: U8) -> None:
        # TODO: to implement
        if address >= 0x8000:
            self.prg[(address - CPU_PRG_START) & self.prg_mask] = value
            return
        return



def cartridge_builder() -> Cartridge:
    return Cartridge()