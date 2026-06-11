import unittest
from paines.ram.memory import RAM
from paines.bus.bus import CPUBus
from paines.cpu.cpu import CPU6502
from paines.types import U16, U8

START_PC :U16 = 0x0FFF

class Test6502Instructions(unittest.TestCase):
    def setUp(self) -> None:
        self.ram = RAM()
        self.bus = CPUBus(ram=self.ram)
        self.cpu = CPU6502(bus=self.bus, debug=True)
        self.cpu.pc = START_PC

    def write_bytes(self, start_addr: U16, bytes_list: list[U8]) -> None:
        for i, b in enumerate(bytes_list):
            self.bus.write(start_addr + i, b)

    def test_lda_immediate(self) -> None:
        self.write_bytes(START_PC, [0xA9, 0x42])
        self.write_bytes(START_PC+2, [0xA9, 0x00])
        self.write_bytes(START_PC+4, [0xA9, 0x80])

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
        self.assertEqual(4 , cycles)

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
        self.assertEqual(4 , cycles)

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
        self.cpu.y = 0x20
        self.write_bytes(START_PC, [0xB1, 0xEA])
        self.write_bytes(0xEA, [0xB1, 0x02])
        self.write_bytes(0x02D1, [0xCD])

        cycles = self.cpu.execute()

        self.assertEqual(self.cpu.a, 0xCD)
        self.assertEqual(5, cycles)