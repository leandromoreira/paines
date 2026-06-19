import unittest
from pathlib import Path

from paines.ram.memory import RAM
from paines.bus.bus import CPUBus
from paines.cpu.cpu import CPU6502
from paines.cartridge.cartridge import Cartridge
from paines.types import U16, U8

START_PC: U16 = 0x0FFF
CARTRIDGE_PATH = f"{Path(__file__).parent.parent}/cartridge/"


class Test6502Instructions(unittest.TestCase):
    def setUp(self) -> None:
        self.ram = RAM()
        self.bus = CPUBus(ram=self.ram)
        self.cpu = CPU6502(bus=self.bus, debug=True)
        self.cpu.pc = START_PC

    def write_bytes(self, start_addr: U16, bytes_list: list[U8]) -> None:
        for i, b in enumerate(bytes_list):
            self.bus.write(start_addr + i, b)

    def test_reset(self) -> None:
        zelda = Cartridge()
        zelda.load(f"{CARTRIDGE_PATH}zelda/Zelda.NES")

        self.cpu.bus.cartridge = zelda
        cycles = self.cpu.reset()

        self.assertEqual(0xC037, self.cpu.pc)
        self.assertEqual(cycles, 7)
        self.assertEqual(self.cpu.s, 0xFD)

    def test_lda_immediate(self) -> None:
        self.write_bytes(START_PC, [0xA9, 0x42])
        self.write_bytes(START_PC + 2, [0xA9, 0x00])
        self.write_bytes(START_PC + 4, [0xA9, 0x80])

        self.cpu.execute()

        self.assertEqual(self.cpu.a, 0x42)
        self.assertEqual(self.cpu.p_zero, 0)
        self.assertEqual(self.cpu.p_sign, 0)

        self.cpu.execute()

        self.assertEqual(self.cpu.p_zero, 1)
        self.assertEqual(self.cpu.p_sign, 0)

        self.cpu.execute()

        self.assertEqual(self.cpu.p_zero, 0)
        self.assertEqual(self.cpu.p_sign, 1)

    def test_lda_zp(self) -> None:
        self.write_bytes(0xCA, [0xFE])
        self.write_bytes(START_PC, [0xA5, 0xCA])

        self.cpu.execute()

        self.assertEqual(self.cpu.a, 0xFE)

    def test_lda_zpx(self) -> None:
        self.cpu.x = 0x10
        self.write_bytes(0xDA, [0xCC])
        self.write_bytes(START_PC, [0xB5, 0xCA])

        self.cpu.execute()

        self.assertEqual(self.cpu.a, 0xCC)

    def test_lda_abs(self) -> None:
        self.write_bytes(START_PC, [0xAD, 0xCA, 0x0F])
        self.write_bytes(0x0FCA, [0xDD])

        self.cpu.execute()

        self.assertEqual(self.cpu.a, 0xDD)

    def test_lda_abs_x(self) -> None:
        self.cpu.x = 0x20
        self.write_bytes(START_PC, [0xBD, 0xCA, 0x0F])
        self.write_bytes(0x0FEA, [0xEE])

        cycles = self.cpu.execute()

        self.assertEqual(self.cpu.a, 0xEE)
        self.assertEqual(4, cycles)

    def test_lda_abs_x_cross(self) -> None:
        self.cpu.x = 0xBB
        self.write_bytes(START_PC, [0xBD, 0xCA, 0x0F])
        self.write_bytes(0x1085, [0xEE])

        cycles = self.cpu.execute()

        self.assertEqual(self.cpu.a, 0xEE)
        self.assertEqual(5, cycles)

    def test_lda_abs_y(self) -> None:
        self.cpu.y = 0x20
        self.write_bytes(START_PC, [0xB9, 0xCA, 0x0F])
        self.write_bytes(0x0FEA, [0xEE])

        cycles = self.cpu.execute()

        self.assertEqual(self.cpu.a, 0xEE)
        self.assertEqual(4, cycles)

    def test_lda_ind_x(self) -> None:
        self.cpu.x = 0x20
        self.write_bytes(START_PC, [0xA1, 0xEA])
        self.write_bytes(0x0A, [0xEE, 0x00])
        self.write_bytes(0x00EE, [0xAA])

        cycles = self.cpu.execute()

        self.assertEqual(self.cpu.a, 0xAA)
        self.assertEqual(6, cycles)

    def test_lda_ind_y(self) -> None:
        self.cpu.y = 0x20
        self.write_bytes(START_PC, [0xB1, 0xEA])
        self.write_bytes(0xEA, [0xB1, 0x02])
        self.write_bytes(0x02D1, [0xCD])

        cycles = self.cpu.execute()

        self.assertEqual(self.cpu.a, 0xCD)
        self.assertEqual(5, cycles)

    def test_lda_ind_y_cross(self) -> None:
        self.cpu.y = 0xFC
        self.write_bytes(START_PC, [0xB1, 0xEA])
        self.write_bytes(0xEA, [0xB1, 0x02])
        self.write_bytes(0x03AD, [0xCD])

        cycles = self.cpu.execute()

        self.assertEqual(self.cpu.a, 0xCD)
        self.assertEqual(6, cycles)

    def test_ldx_immediate(self) -> None:
        self.write_bytes(START_PC, [0xA2, 0x51])

        self.cpu.execute()

        self.assertEqual(self.cpu.x, 0x51)

    def test_ldx_zp(self) -> None:
        self.write_bytes(0x51, [0xF1])
        self.write_bytes(START_PC, [0xA6, 0x51])

        self.cpu.execute()

        self.assertEqual(self.cpu.x, 0xF1)

    def test_ldx_zp_y(self) -> None:
        self.cpu.y = 0x10
        self.write_bytes(0x51 + self.cpu.y, [0xF1])
        self.write_bytes(START_PC, [0xB6, 0x51])

        self.cpu.execute()

        self.assertEqual(self.cpu.x, 0xF1)

    def test_ldx_abs(self) -> None:
        self.write_bytes(START_PC, [0xAE, 0x51, 0x01])
        self.write_bytes(0x0151, [0xEA])

        self.cpu.execute()

        self.assertEqual(self.cpu.x, 0xEA)

    def test_ldx_abs_y(self) -> None:
        self.cpu.y = 0x10
        self.write_bytes(START_PC, [0xBE, 0x51, 0x01])
        self.write_bytes(0x0151 + self.cpu.y, [0xEA])

        self.cpu.execute()

        self.assertEqual(self.cpu.x, 0xEA)

    def test_ldy_immediate(self) -> None:
        self.write_bytes(START_PC, [0xA0, 0x69])

        self.cpu.execute()

        self.assertEqual(self.cpu.y, 0x69)

    def test_ldy_zp(self) -> None:
        self.write_bytes(START_PC, [0xA4, 0x03])
        self.write_bytes(0x03, [0xF1])

        self.cpu.execute()

        self.assertEqual(0xF1, self.cpu.y)

    def test_ldy_zp_x(self) -> None:
        self.cpu.x = 0xCA
        self.write_bytes(START_PC, [0xB4, 0x03])
        self.write_bytes(0x03 + self.cpu.x, [0xF1])

        self.cpu.execute()

        self.assertEqual(0xF1, self.cpu.y)

    def test_ldy_abs(self) -> None:
        self.write_bytes(START_PC, [0xAC, 0x03, 0x02])
        self.write_bytes(0x0203, [0xF1])

        self.cpu.execute()

        self.assertEqual(0xF1, self.cpu.y)

    def test_ldy_abs_ind(self) -> None:
        self.cpu.x = 0x2
        self.write_bytes(START_PC, [0xBC, 0x03, 0x02])
        self.write_bytes(0x0203 + self.cpu.x, [0xF1])

        self.cpu.execute()

        self.assertEqual(0xF1, self.cpu.y)

    def test_tay(self) -> None:
        self.write_bytes(START_PC, [0xA8])
        self.cpu.a = 0x69
        self.assertEqual(self.cpu.y, 0x00)

        self.cpu.execute()

        self.assertEqual(self.cpu.y, 0x69)

    def test_tax(self) -> None:
        self.write_bytes(START_PC, [0xAA])
        self.cpu.a = 0x69
        self.assertEqual(self.cpu.x, 0x00)

        self.cpu.execute()

        self.assertEqual(self.cpu.x, 0x69)

    def test_tsx(self) -> None:
        self.write_bytes(START_PC, [0xBA])
        self.cpu.s = 0x69
        self.assertEqual(self.cpu.x, 0x00)

        self.cpu.execute()

        self.assertEqual(self.cpu.x, 0x69)

    def test_tya(self) -> None:
        self.write_bytes(START_PC, [0x98])
        self.cpu.y = 0x69
        self.assertEqual(self.cpu.a, 0x00)

        self.cpu.execute()

        self.assertEqual(self.cpu.a, 0x69)

    def test_txa(self) -> None:
        self.write_bytes(START_PC, [0x8A])
        self.cpu.x = 0x69
        self.assertEqual(self.cpu.a, 0x00)

        self.cpu.execute()

        self.assertEqual(self.cpu.a, 0x69)

    def test_txs(self) -> None:
        self.write_bytes(START_PC, [0x9A])
        self.cpu.x = 0x69
        self.assertEqual(self.cpu.s, 0xFD)

        self.cpu.execute()

        self.assertEqual(self.cpu.s, 0x69)

    def test_sta_zp(self) -> None:
        self.cpu.a = 0xDF
        self.write_bytes(START_PC, [0x85, 0x10])

        self.cpu.execute()

        self.assertEqual(0xDF, self.cpu.bus.read(0x10))

    def test_sta_zp_x(self) -> None:
        self.cpu.a = 0xDF
        self.cpu.x = 0x10
        self.write_bytes(START_PC, [0x95, 0x10])

        self.cpu.execute()

        self.assertEqual(0xDF, self.cpu.bus.read(0x10 + self.cpu.x))

    def test_sta_abs(self) -> None:
        self.cpu.a = 0xDF
        self.write_bytes(START_PC, [0x8D, 0x10, 0x0F])

        self.cpu.execute()

        self.assertEqual(0xDF, self.cpu.bus.read(0x0F10))

    def test_sta_abs_x(self) -> None:
        self.cpu.a = 0xDF
        self.cpu.x = 0x05
        self.write_bytes(START_PC, [0x9D, 0x10, 0x0F])

        self.cpu.execute()

        self.assertEqual(0xDF, self.cpu.bus.read(0x0F10 + self.cpu.x))

    def test_sta_abs_y(self) -> None:
        self.cpu.a = 0xDF
        self.cpu.y = 0x05
        self.write_bytes(START_PC, [0x99, 0x10, 0x0F])

        self.cpu.execute()

        self.assertEqual(0xDF, self.cpu.bus.read(0x0F10 + self.cpu.y))

    def test_sta_ind_x(self) -> None:
        self.cpu.a = 0xDF
        self.cpu.x = 0x05
        self.write_bytes(START_PC, [0x81, 0x10])
        self.write_bytes(0x10 + 0x05, [0x0F, 0x0A])
        self.write_bytes(0x0A0F, [0xFA])

        self.cpu.execute()

        self.assertEqual(0xDF, self.cpu.bus.read(0x0A0F))

    def test_sta_ind_y(self) -> None:
        self.cpu.a = 0xFC
        self.cpu.y = 0x05
        self.write_bytes(START_PC, [0x91, 0x10])
        self.write_bytes(0x10, [0x0F, 0x0C])
        self.write_bytes(0x0C0F + self.cpu.y, [0xA2])

        self.cpu.execute()

        self.assertEqual(0xFC, self.cpu.bus.read(0x0C0F + self.cpu.y))

    def test_stx_zp(self) -> None:
        self.cpu.x = 0xFC
        self.write_bytes(START_PC, [0x86, 0x10])
        self.write_bytes(0x10, [0xEA])

        self.assertEqual(0xEA, self.cpu.bus.read(0x0010))

        self.cpu.execute()

        self.assertEqual(0xFC, self.cpu.bus.read(0x0010))

    def test_stx_zp_y(self) -> None:
        self.cpu.x = 0xFC
        self.cpu.y = 0x0A
        self.write_bytes(START_PC, [0x96, 0x10])
        self.write_bytes(0x10 + self.cpu.y, [0xEA])

        self.assertEqual(0xEA, self.cpu.bus.read(0x0010 + self.cpu.y))

        self.cpu.execute()

        self.assertEqual(0xFC, self.cpu.bus.read(0x0010 + self.cpu.y))

    def test_stx_abs(self) -> None:
        self.cpu.x = 0xFC
        self.write_bytes(START_PC, [0x8E, 0x10, 0x02])
        self.write_bytes(0x0210, [0xEA])

        self.assertEqual(0xEA, self.cpu.bus.read(0x0210))

        self.cpu.execute()

        self.assertEqual(0xFC, self.cpu.bus.read(0x0210))

    def test_sty_zp(self) -> None:
        self.cpu.y = 0xFC
        self.write_bytes(START_PC, [0x84, 0x10])
        self.write_bytes(0x10, [0xEA])

        self.assertEqual(0xEA, self.cpu.bus.read(0x0010))

        self.cpu.execute()

        self.assertEqual(0xFC, self.cpu.bus.read(0x0010))

    def test_sty_zp_x(self) -> None:
        self.cpu.y = 0xFC
        self.cpu.x = 0x0A
        self.write_bytes(START_PC, [0x94, 0x10])
        self.write_bytes(0x10 + self.cpu.x, [0xEA])

        self.assertEqual(0xEA, self.cpu.bus.read(0x0010 + self.cpu.x))

        self.cpu.execute()

        self.assertEqual(0xFC, self.cpu.bus.read(0x0010 + self.cpu.x))

    def test_sty_abs(self) -> None:
        self.cpu.y = 0xFC
        self.write_bytes(START_PC, [0x8C, 0x10, 0x02])
        self.write_bytes(0x0210, [0xEA])

        self.assertEqual(0xEA, self.cpu.bus.read(0x0210))

        self.cpu.execute()

        self.assertEqual(0xFC, self.cpu.bus.read(0x0210))

    def test_pha(self) -> None:
        self.cpu.a = 0xFC
        self.write_bytes(START_PC, [0x48])
        self.write_bytes(0x01FC, [0xEA])

        self.cpu.execute()

        self.assertEqual(self.cpu.a, self.cpu.bus.read(0x0100 | (self.cpu.s + 1)))

    def test_php(self) -> None:
        self.cpu.p = 0b1000100
        self.write_bytes(START_PC, [0x08])
        self.write_bytes(0x01FC, [0xEA])

        self.cpu.execute()

        self.assertEqual(self.cpu.p, self.cpu.bus.read(0x0100 | (self.cpu.s + 1)))

    def test_pla(self) -> None:
        self.cpu.s = 0xAB
        self.write_bytes(START_PC, [0x68])
        self.write_bytes(0x1AC, [0xDC])

        self.cpu.execute()

        self.assertEqual(self.cpu.a, 0xDC)

    def test_plp(self) -> None:
        self.cpu.p = 0xAB
        self.write_bytes(START_PC, [0x28])
        self.write_bytes(0x1FE, [0b10101010])

        self.cpu.execute()

        self.assertEqual(self.cpu.p_carry, 0x0)
        self.assertEqual(self.cpu.p_zero, 0x1)
        self.assertEqual(self.cpu.p_irq, 0x0)
        self.assertEqual(self.cpu.p_dcm, 0x1)
