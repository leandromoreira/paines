from paines.cartridge.cartridge import Cartridge, cartridge_builder
from paines.ram.memory import RAM, ram_builder
from paines.types import U16, U8

# https://problemkaputt.de/everynes.htm#memorymaps

# CPU Memory Map (16bit bus width, 0-FFFFh)
# ✅ 0000h-07FFh   Internal 2K Work RAM (mirrored to 800h-1FFFh)
#    2000h-2007h   Internal PPU Registers (mirrored to 2008h-3FFFh)
#    4000h-4017h   Internal APU Registers
# ✅ 4018h-5FFFh   Cartridge Expansion Area almost 8K
# ✅ 6000h-7FFFh   Cartridge SRAM Area 8K
# ✅ 8000h-FFFFh   Cartridge PRG-ROM Area 32K

# PPU Memory Map (14bit bus width, 0-3FFFh)
#    0000h-0FFFh   Pattern Table 0 (4K) (256 Tiles)
#    1000h-1FFFh   Pattern Table 1 (4K) (256 Tiles)
#    2000h-23FFh   Name Table 0 and Attribute Table 0 (1K) (32x30 BG Map)
#    2400h-27FFh   Name Table 1 and Attribute Table 1 (1K) (32x30 BG Map)
#    2800h-2BFFh   Name Table 2 and Attribute Table 2 (1K) (32x30 BG Map)
#    2C00h-2FFFh   Name Table 3 and Attribute Table 3 (1K) (32x30 BG Map)
#    3000h-3EFFh   Mirror of 2000h-2EFFh
#    3F00h-3F1Fh   Background and Sprite Palettes (25 entries used)
#    3F20h-3FFFh   Mirrors of 3F00h-3F1Fh

class CPUBus:
    def __init__(self, ram: RAM | None = None, cartridge: Cartridge | None = None) -> None:
        self.ram = ram or ram_builder() # 0x0000 - 0x1FFF WRAM
        self.open_bus :U8 = 0
        self.cartridge = cartridge or cartridge_builder() # 0x4018 - 0xFFFF - Cartridge

    def read(self, address: U16) -> U8:
        if address <= 0x1FFF:
           self.open_bus = self.ram.read(address)
           return self.open_bus

        if address >= 0x4018 and address <= 0xFFFF:
            self.open_bus = self.cartridge.read(address, self.open_bus)
            return self.open_bus

        return self.open_bus

    def write(self, address: U16, value: U8) -> None:
        self.open_bus = value

        if address <= 0x1FFF:
            self.ram.write(address, value)
            return

        if address >= 0x4018 and address <= 0xFFFF:
            # TODO: to implement
            self.cartridge.write(address, value)
            return

        return

def cpu_bus_builder() -> CPUBus:
    return CPUBus()