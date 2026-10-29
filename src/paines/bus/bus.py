from paines.apu.apu import APU
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
        self.controller_buttons: list[U8] = [
            0,
            0,
        ]  # A,B,Select,Start,Up,Down,Left,Right = bits 0-7
        self._controller_shift: list[U8] = [0, 0]
        self._controller_strobe = False
        self.dma_stall_cycles = 0
        self.apu = APU(read_memory=self.read)

    def _oam_dma(self, page: U8) -> None:
        base = page << 8
        ppu = self.ppu_mmio.ppu
        ppu.flush()
        for i in range(256):
            ppu.oam_memory[(ppu.oam_address + i) & 0xFF] = self.read(base + i)
        self.dma_stall_cycles += 513

    def _read_controller(self, index: int) -> U8:
        if self._controller_strobe:
            return 0x40 | (self.controller_buttons[index] & 1)
        bit = self._controller_shift[index] & 1
        self._controller_shift[index] = (self._controller_shift[index] >> 1) | 0x80
        return 0x40 | bit

    def read(self, address: U16) -> U8:
        # RAM and PRG-ROM make up nearly every access, so they skip the method calls below.
        if address <= 0x1FFF:
            ram = self.ram
            value = self.open_bus = ram.cells[address & ram.ram_mask]
            return value

        if address >= 0x8000:
            cartridge = self.cartridge
            value = self.open_bus = cartridge.prg[
                cartridge.prg_offsets[(address >> 13) & 3] + (address & 0x1FFF)
            ]
            return value

        if address >= 0x2000 and address <= 0x3FFF:
            self.open_bus = self.ppu_mmio.read(address)
            return self.open_bus

        if address == 0x4015:
            self.open_bus = self.apu.read_status()
            return self.open_bus

        if address == 0x4016 or address == 0x4017:
            self.open_bus = self._read_controller(address - 0x4016)
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
            ram = self.ram
            ram.cells[address & ram.ram_mask] = value & 0xFF
            return

        if address >= 0x2000 and address <= 0x3FFF:
            self.ppu_mmio.write(address, value)
            return

        if address == 0x4014:
            self._oam_dma(value)
            return

        if 0x4000 <= address <= 0x4013 or address == 0x4015:
            self.apu.write(address, value)
            return

        if address == 0x4016:
            strobe = bool(value & 1)
            if self._controller_strobe and not strobe:
                self._controller_shift = list(self.controller_buttons)
            self._controller_strobe = strobe
            if strobe:
                self._controller_shift = list(self.controller_buttons)
            return

        if address == 0x4017:
            self.apu.write(address, value)
            return

        if address >= 0x4018 and address <= 0xFFFF:
            if address >= 0x8000:
                self.ppu_mmio.ppu.flush()  # mapper registers change what the PPU renders
            self.cartridge.write(address, value)
            return

        return


def cpu_bus_builder() -> CPUBus:
    return CPUBus()
