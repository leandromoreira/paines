from paines.cartridge.cartridge import Cartridge, cartridge_builder
from paines.bus.ppu import ppu_bus_builder
from paines.ppu.mmio import PPUMMIO, ppu_mmio_builder
from paines.ppu.ppu import ppu_builder
from paines.ram.memory import RAM, ram_builder
from paines.types import U16, U8

# https://problemkaputt.de/everynes.htm#memorymaps

# CPU Memory Map (16bit bus width, 0-FFFFh)
# ✅ 0000h-07FFh   Internal 2K Work RAM (mirrored to 800h-1FFFh)
# ✅ 2000h-2007h   Internal PPU Registers (mirrored to 2008h-3FFFh)
#    4000h-4017h   Internal APU Registers
# ✅ 4018h-5FFFh   Cartridge Expansion Area almost 8K
# ✅ 6000h-7FFFh   Cartridge SRAM Area 8K
# ✅ 8000h-FFFFh   Cartridge PRG-ROM Area 32K


class CPUBus:
    def __init__(
        self,
        ram: RAM | None = None,
        cartridge: Cartridge | None = None,
        ppu_mmio: PPUMMIO | None = None,
    ) -> None:
        self.ram = ram or ram_builder()  # 0x0000 - 0x1FFF WRAM
        self.open_bus: U8 = 0
        self.cartridge = cartridge or cartridge_builder()  # 0x4018 - 0xFFFF - Cartridge
        if ppu_mmio is None:
            ppu = ppu_builder(bus=ppu_bus_builder(cartridge=self.cartridge))
            ppu_mmio = ppu_mmio_builder(ppu)
        self.ppu_mmio = ppu_mmio

    def read(self, address: U16) -> U8:
        if address <= 0x1FFF:
            self.open_bus = self.ram.read(address)
            return self.open_bus

        if address >= 0x2000 and address <= 0x3FFF:
            self.open_bus = self.ppu_mmio.read(address)
            return self.open_bus

        if address >= 0x4018 and address <= 0xFFFF:
            self.open_bus = self.cartridge.read(address, self.open_bus)
            return self.open_bus

        return self.open_bus

    def peek(self, address: U16) -> U8:
        dummy_open_bus: U8 = 0x00
        if address <= 0x1FFF:
            return self.ram.read(address)

        if address >= 0x4018 and address <= 0xFFFF:
            return self.cartridge.read(address, dummy_open_bus)

        return dummy_open_bus

    def write(self, address: U16, value: U8) -> None:
        self.open_bus = value

        if address <= 0x1FFF:
            self.ram.write(address, value)
            return

        if address >= 0x2000 and address <= 0x3FFF:
            self.ppu_mmio.write(address, value)
            return

        if address >= 0x4018 and address <= 0xFFFF:
            # TODO: to implement
            self.cartridge.write(address, value)
            return

        return


def cpu_bus_builder() -> CPUBus:
    return CPUBus()
