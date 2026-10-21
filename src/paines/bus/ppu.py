from paines.cartridge.cartridge import Cartridge, cartridge_builder
from paines.ram.memory import RAM, ram_builder
from paines.types import U16, U8, U1

# PPU Memory Map (14bit bus width, 0-3FFFh)
#  ✅  0000h-0FFFh   Pattern Table 0 (4K) (256 Tiles)
#  ✅  1000h-1FFFh   Pattern Table 1 (4K) (256 Tiles)
#  ✅  2000h-23FFh   Name Table 0 and Attribute Table 0 (1K) (32x30 BG Map)
#  ✅  2400h-27FFh   Name Table 1 and Attribute Table 1 (1K) (32x30 BG Map)
#  ✅  2800h-2BFFh   Name Table 2 and Attribute Table 2 (1K) (32x30 BG Map)
#  ✅  2C00h-2FFFh   Name Table 3 and Attribute Table 3 (1K) (32x30 BG Map)
#  ✅  3000h-3EFFh   Mirror of 2000h-2EFFh
#    3F00h-3F1Fh   Background and Sprite Palettes (25 entries used)
#    3F20h-3FFFh   Mirrors of 3F00h-3F1Fh


class PPUBus:
    def __init__(
        self, ram: RAM | None = None, cartridge: Cartridge | None = None, palette_ram: RAM | None = None
    ) -> None:
        self.open_bus: U8 = 0
        self.cartridge = cartridge or cartridge_builder()
        self.ram = ram or ram_builder()
        self.palette_ram = palette_ram or RAM(size=32)

    def read(self, address: U16) -> U8:
        address = address & 0x3FFF

        if address <= 0x1FFF:
            self.open_bus = self.cartridge.read_chr(address)
            return self.open_bus

        if address <= 0x3EFF:
            address = 0x2000 + ((address - 0x2000) % 0x1000)
            return self.ram.read(self._resolve_nametable_mirroring(address))

        if address <= 0x3FFF:
            # TODO: palette
            return 0xFF

        return self.open_bus

    def _resolve_nametable_mirroring(self, address: U16) -> U16:
        nametable_addr: U16 = (address - 0x2000) % 0x1000
        nametable_index = nametable_addr // 0x400
        offset = nametable_addr % 0x400
        physical_bank: U1 = 0

        if self.cartridge.nametable_mirroring == 0:
            physical_bank = 0 if nametable_index in [0, 1] else 1
            return (physical_bank * 0x400) + offset
        else:
            physical_bank = 0 if nametable_index in [0, 2] else 1
            return (physical_bank * 0x400) + offset

    def write(self, address: U16, value: U8) -> None:
        address = address & 0x3FFF

        if address <= 0x1FFF:
            # TODO: maybe mappers?
            return

        if address <= 0x3EFF:
            address = 0x2000 + ((address - 0x2000) % 0x1000)
            self.ram.write(self._resolve_nametable_mirroring(address), value)
            return

        if address <= 0x3FFF:
            # TODO: palette
            return

        return


def ppu_bus_builder() -> PPUBus:
    return PPUBus()
