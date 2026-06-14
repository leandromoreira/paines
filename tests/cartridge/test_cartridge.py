import unittest
from pathlib import Path

from paines.cartridge.cartridge import Cartridge
from paines.types import U8

TEST_DIR = Path(__file__).parent
open_bus_simulated :U8 = 0xFE

class TestNesCartridge(unittest.TestCase):

    def test_loading(self) -> None:
        zelda = Cartridge()
        zelda.load(f"{TEST_DIR}/zelda/Zelda.nes")

        self.assertEqual(zelda.magic_id, b"NES\x1A")
        self.assertEqual(zelda.prg_size, 0x1)
        self.assertEqual(zelda.chr_size, 0x1)

        self.assertEqual(len(zelda.prg), 16384)
        low = zelda.read(0xFFFC, open_bus_simulated)
        high = zelda.read(0xFFFD, open_bus_simulated)
        self.assertEqual(high << 8 | low, 0xC037)

        # Reset_Routine  SUBROUTINE
        #    cld         ;Clear decimal flag
        #    sei         ;Disable interrupts
        # from ./zelda/Zelda.asm
        first_instruction = zelda.read(0xC037, open_bus_simulated)
        self.assertEqual(hex(0xD8), hex(first_instruction))
        second_instruction = zelda.read(0xC037+1, open_bus_simulated)
        self.assertEqual(hex(0x78), hex(second_instruction))

    def test_open_bus(self) -> None:
        zelda = Cartridge()
        zelda.load(f"{TEST_DIR}/zelda/Zelda.nes")

        self.assertEqual(zelda.magic_id, b"NES\x1A")
        self.assertEqual(zelda.prg_size, 0x1)
        self.assertEqual(zelda.chr_size, 0x1)

        self.assertEqual(len(zelda.prg), 16384)
        low = zelda.read(0xFFFC, open_bus_simulated)
        high = zelda.read(0xFFFD, open_bus_simulated)
        self.assertEqual(high << 8 | low, 0xC037)

        # simulating latest read
        open_bus = zelda.read(0x6100, high)
        self.assertEqual(open_bus, high)