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

    def test_nmi_execution(self) -> None:
        zelda = Cartridge()
        zelda.load(f"{CARTRIDGE_PATH}zelda/Zelda.NES")

        self.cpu.bus.cartridge = zelda
        current_pc = 0x1234
        self.cpu.pc = current_pc
        self.cpu.s = 0xFF
        self.cpu.p_irq = 0x0
        self.cpu.p_sign = 0x1
        self.cpu.compose_p()

        self.cpu.bus.write(0xFFFA, 0x78)
        self.cpu.bus.write(0xFFFB, 0x56)

        cycles = self.cpu.nmi()

        self.assertEqual(0x5678, self.cpu.pc)
        self.assertEqual(7, cycles)
        self.assertEqual(0x1, self.cpu.p_irq)

        self.assertEqual(0xFC, self.cpu.s)

        self.assertEqual(0x12, self.cpu.bus.read(0x01FF))
        self.assertEqual(0x34, self.cpu.bus.read(0x01FE))

        pushed_status = self.cpu.bus.read(0x01FD)
        self.assertEqual(0, (pushed_status >> 4) & 1)
        self.assertEqual(1, (pushed_status >> 5) & 1)

    def test_irq_executed_when_allowed(self) -> None:
        zelda = Cartridge()
        zelda.load(f"{CARTRIDGE_PATH}zelda/Zelda.NES")

        self.cpu.bus.cartridge = zelda
        current_pc = 0xABCD
        self.cpu.pc = current_pc
        self.cpu.s = 0x80
        self.cpu.p_irq = 0x0
        self.cpu.compose_p()

        self.cpu.bus.write(0xFFFE, 0x34)
        self.cpu.bus.write(0xFFFF, 0x12)

        cycles = self.cpu.irq()

        self.assertEqual(0x1234, self.cpu.pc)
        self.assertEqual(7, cycles)
        self.assertEqual(0x1, self.cpu.p_irq)
        self.assertEqual(0x7D, self.cpu.s)

        self.assertEqual(0xAB, self.cpu.bus.read(0x0180))
        self.assertEqual(0xCD, self.cpu.bus.read(0x017F))

        pushed_status = self.cpu.bus.read(0x017E)
        self.assertEqual(0, (pushed_status >> 4) & 1)

    def test_irq_ignored_when_masked(self) -> None:
        zelda = Cartridge()
        zelda.load(f"{CARTRIDGE_PATH}zelda/Zelda.NES")

        self.cpu.bus.cartridge = zelda
        start_pc = 0x4444
        self.cpu.pc = start_pc
        self.cpu.s = 0xFF
        self.cpu.p_irq = 0x1

        self.cpu.bus.write(0x01FF, 0x00)
        self.cpu.bus.write(0x01FE, 0x00)

        cycles = self.cpu.irq()

        self.assertEqual(
            start_pc, self.cpu.pc, "PC should not change when IRQ is masked"
        )
        self.assertNotEqual(
            7, cycles, "Should not return 7 execution cycles if ignored"
        )
        self.assertEqual(
            0xFF, self.cpu.s, "Stack pointer should not move when IRQ is masked"
        )
        self.assertEqual(0x00, self.cpu.bus.read(0x01FF), "Stack shouldn't be touched")

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

    def test_php_forces_bits_high(self) -> None:
        self.cpu.p_sign = 1
        self.cpu.p_carry = 0
        self.cpu.p_zero = 0
        self.cpu.p_overflow = 0

        self.cpu.compose_p()

        self.write_bytes(START_PC, [0x08])

        initial_stack_pointer = self.cpu.s
        self.cpu.execute()

        written_stack_address = 0x0100 | ((initial_stack_pointer) & 0xFF)
        pushed_value = self.cpu.bus.read(written_stack_address)

        self.assertEqual(initial_stack_pointer - 1, self.cpu.s)

        expected_pushed_value = self.cpu.p | 0x30
        self.assertEqual(expected_pushed_value, pushed_value)

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
        self.assertEqual(self.cpu.p_brk, 0x0)
        self.assertEqual(self.cpu.p_unused, 0x1)
        self.assertEqual(self.cpu.p_overflow, 0x0)
        self.assertEqual(self.cpu.p_sign, 0x1)

    def test_adc(self) -> None:
        self.cpu.a = 0xAB
        self.cpu.p_carry = 0x0
        self.write_bytes(START_PC, [0x69, 0xA0])

        self.cpu.execute()

        self.assertEqual(0x4B, self.cpu.a)
        self.assertEqual(0x0, self.cpu.p_zero)
        self.assertEqual(0x1, self.cpu.p_carry)
        self.assertEqual(0x0, self.cpu.p_sign)
        self.assertEqual(0x1, self.cpu.p_overflow)

    def test_adc_normal_positive(self) -> None:
        self.cpu.a = 0x20
        self.cpu.p_carry = 0
        self.write_bytes(START_PC, [0x69, 0x10])
        self.cpu.execute()

        self.assertEqual(0x30, self.cpu.a)
        self.assertEqual(0, self.cpu.p_carry)
        self.assertEqual(0, self.cpu.p_overflow)
        self.assertEqual(0, self.cpu.p_sign)
        self.assertEqual(0, self.cpu.p_zero)

    def test_adc_with_carry_in(self) -> None:
        self.cpu.a = 0x20
        self.cpu.p_carry = 1
        self.write_bytes(START_PC, [0x69, 0x10])
        self.cpu.execute()

        self.assertEqual(0x31, self.cpu.a)
        self.assertEqual(0, self.cpu.p_carry)
        self.assertEqual(0, self.cpu.p_overflow)
        self.assertEqual(0, self.cpu.p_sign)
        self.assertEqual(0, self.cpu.p_zero)

    def test_adc_unsigned_overflow_carry_out(self) -> None:
        self.cpu.a = 0xFF
        self.cpu.p_carry = 0
        self.write_bytes(START_PC, [0x69, 0x01])
        self.cpu.execute()

        self.assertEqual(0x00, self.cpu.a)
        self.assertEqual(1, self.cpu.p_carry)
        self.assertEqual(0, self.cpu.p_overflow)
        self.assertEqual(0, self.cpu.p_sign)
        self.assertEqual(1, self.cpu.p_zero)

    def test_adc_signed_overflow_positive(self) -> None:
        self.cpu.a = 0x7F
        self.cpu.p_carry = 0
        self.write_bytes(START_PC, [0x69, 0x01])
        self.cpu.execute()

        self.assertEqual(0x80, self.cpu.a)
        self.assertEqual(0, self.cpu.p_carry)
        self.assertEqual(1, self.cpu.p_overflow)
        self.assertEqual(1, self.cpu.p_sign)
        self.assertEqual(0, self.cpu.p_zero)

    def test_adc_signed_overflow_negative(self) -> None:
        self.cpu.a = 0x80
        self.cpu.p_carry = 0
        self.write_bytes(START_PC, [0x69, 0xFF])
        self.cpu.execute()

        self.assertEqual(0x7F, self.cpu.a)
        self.assertEqual(1, self.cpu.p_carry)
        self.assertEqual(1, self.cpu.p_overflow)
        self.assertEqual(0, self.cpu.p_sign)
        self.assertEqual(0, self.cpu.p_zero)

    def test_adc_zp(self) -> None:
        self.cpu.a = 0xAB
        self.cpu.p_carry = 0x0
        self.write_bytes(START_PC, [0x65, 0xA0])
        self.write_bytes(0xA0, [0x01])

        self.cpu.execute()

        self.assertEqual(0xAC, self.cpu.a)
        self.assertEqual(0x0, self.cpu.p_zero)
        self.assertEqual(0x0, self.cpu.p_carry)
        self.assertEqual(0x1, self.cpu.p_sign)
        self.assertEqual(0x0, self.cpu.p_overflow)

    def test_adc_zp_x(self) -> None:
        self.cpu.a = 0xAB
        self.cpu.x = 0x1
        self.cpu.p_carry = 0x0
        self.write_bytes(START_PC, [0x75, 0xA0])
        self.write_bytes(0xA0 + self.cpu.x, [0x02])

        self.cpu.execute()

        self.assertEqual(0xAD, self.cpu.a)
        self.assertEqual(0x0, self.cpu.p_zero)
        self.assertEqual(0x0, self.cpu.p_carry)
        self.assertEqual(0x1, self.cpu.p_sign)
        self.assertEqual(0x0, self.cpu.p_overflow)

    def test_adc_abs(self) -> None:
        self.cpu.a = 0xDC
        self.write_bytes(START_PC, [0x6D, 0xA0, 0x03])
        self.write_bytes(0x03A0, [0x01])

        self.cpu.execute()

        self.assertEqual(0xDD, self.cpu.a)

    def test_adc_abs_x(self) -> None:
        self.cpu.a = 0xDC
        self.cpu.x = 0x2
        self.write_bytes(START_PC, [0x7D, 0xA0, 0x03])
        self.write_bytes(0x03A0 + self.cpu.x, [0x01])

        self.cpu.execute()

        self.assertEqual(0xDD, self.cpu.a)

    def test_adc_ind_x(self) -> None:
        self.cpu.a = 0xDC
        self.cpu.x = 0x2
        self.write_bytes(START_PC, [0x61, 0xA0])
        self.write_bytes(0xA0 + self.cpu.x, [0x01, 0x03])
        self.write_bytes(0x0301, [0x02])

        self.cpu.execute()

        self.assertEqual(0xDE, self.cpu.a)

    def test_adc_ind_y(self) -> None:
        self.cpu.a = 0xDC
        self.cpu.y = 0x2
        self.write_bytes(START_PC, [0x71, 0xA0])
        self.write_bytes(0xA0, [0x01, 0x03])
        self.write_bytes(0x0301 + self.cpu.y, [0x02])

        self.cpu.execute()

        self.assertEqual(0xDE, self.cpu.a)

    def test_sbc(self) -> None:
        self.cpu.a = 0xAB
        self.cpu.p_carry = 0x1
        self.write_bytes(START_PC, [0xE9, 0xA0])

        self.cpu.execute()

        self.assertEqual(0xB, self.cpu.a)
        self.assertEqual(1, self.cpu.p_carry)
        self.assertEqual(0, self.cpu.p_overflow)
        self.assertEqual(0, self.cpu.p_sign)
        self.assertEqual(0, self.cpu.p_zero)

    def test_and(self) -> None:
        self.cpu.a = 0b1010
        self.write_bytes(START_PC, [0x29, 0b0011])

        self.cpu.execute()

        self.assertEqual(0b10, self.cpu.a)

    def test_ora(self) -> None:
        self.cpu.a = 0b10100000
        self.write_bytes(START_PC, [0x09, 0b01100011])

        self.cpu.execute()

        self.assertEqual(0b11100011, self.cpu.a)
        self.assertEqual(0, self.cpu.p_zero)
        self.assertEqual(1, self.cpu.p_sign)

    def test_eor(self) -> None:
        self.cpu.a = 0xFF
        self.write_bytes(START_PC, [0x49, 0xFF])

        self.cpu.execute()

        self.assertEqual(0x00, self.cpu.a)
        self.assertEqual(1, self.cpu.p_zero)
        self.assertEqual(0, self.cpu.p_sign)

    def test_cmp(self) -> None:
        self.cpu.a = 0x01
        self.write_bytes(START_PC, [0xC9, 0x02])

        self.cpu.execute()

        self.assertEqual(0x1, self.cpu.p_sign)
        self.assertEqual(0x0, self.cpu.p_zero)
        self.assertEqual(0x0, self.cpu.p_carry)

    def test_cmp_x(self) -> None:
        self.cpu.x = 0x01
        self.write_bytes(START_PC, [0xE0, 0x02])

        self.cpu.execute()

        self.assertEqual(0x1, self.cpu.p_sign)
        self.assertEqual(0x0, self.cpu.p_zero)
        self.assertEqual(0x0, self.cpu.p_carry)

    def test_cmp_y(self) -> None:
        self.cpu.y = 0x01
        self.write_bytes(START_PC, [0xC0, 0x02])

        self.cpu.execute()

        self.assertEqual(0x1, self.cpu.p_sign)
        self.assertEqual(0x0, self.cpu.p_zero)
        self.assertEqual(0x0, self.cpu.p_carry)

    def test_bit_zp_zero(self) -> None:
        self.cpu.a = 0x0
        self.write_bytes(START_PC, [0x24, 0x02])
        self.write_bytes(0x0002, [0x0])

        self.cpu.execute()

        self.assertEqual(0x1, self.cpu.p_zero)
        self.assertEqual(0x0, self.cpu.p_sign)
        self.assertEqual(0x0, self.cpu.p_overflow)

    def test_bit_abs_sign_overflow(self) -> None:
        self.cpu.a = 0b11000000
        self.write_bytes(START_PC, [0x2C, 0x02, 0x01])
        self.write_bytes(0x0102, [0b11000000])

        self.cpu.execute()

        self.assertEqual(0x0, self.cpu.p_zero)
        self.assertEqual(0x1, self.cpu.p_sign)
        self.assertEqual(0x1, self.cpu.p_overflow)

    def test_inc_zp(self) -> None:
        self.write_bytes(START_PC, [0xE6, 0x02])
        self.write_bytes(0x02, [0x9])

        self.cpu.execute()

        self.assertEqual(0xA, self.cpu.bus.read(0x02))

    def test_inc_zp_wrap(self) -> None:
        self.write_bytes(START_PC, [0xE6, 0x02])
        self.write_bytes(0x02, [0xFF])

        self.cpu.execute()

        self.assertEqual(0x0, self.cpu.bus.read(0x02))
        self.assertEqual(0x1, self.cpu.p_zero)
        self.assertEqual(0x0, self.cpu.p_sign)

    def test_dec_zp(self) -> None:
        self.write_bytes(START_PC, [0xC6, 0x02])
        self.write_bytes(0x02, [0x0A])

        self.cpu.execute()

        self.assertEqual(0x09, self.cpu.bus.read(0x02))

    def test_dec_zp_wrap(self) -> None:
        self.write_bytes(START_PC, [0xC6, 0x02])
        self.write_bytes(0x02, [0x00])

        self.cpu.execute()

        self.assertEqual(0xFF, self.cpu.bus.read(0x02))
        self.assertEqual(0, self.cpu.p_zero)
        self.assertEqual(1, self.cpu.p_sign)

    def test_dec_zp_to_zero(self) -> None:
        self.write_bytes(START_PC, [0xC6, 0x02])
        self.write_bytes(0x02, [0x01])

        self.cpu.execute()

        self.assertEqual(0x00, self.cpu.bus.read(0x02))
        self.assertEqual(1, self.cpu.p_zero)
        self.assertEqual(0, self.cpu.p_sign)

    def test_asl_memory(self) -> None:
        self.write_bytes(START_PC, [0x06, 0x02])
        self.write_bytes(0x02, [0x81])

        self.cpu.execute()

        self.assertEqual(0x02, self.cpu.bus.read(0x02))
        self.assertEqual(1, self.cpu.p_carry)
        self.assertEqual(0, self.cpu.p_zero)
        self.assertEqual(0, self.cpu.p_sign)

    def test_lsr_memory(self) -> None:
        self.write_bytes(START_PC, [0x46, 0x02])
        self.write_bytes(0x02, [0x03])

        self.cpu.execute()

        self.assertEqual(0x01, self.cpu.bus.read(0x02))
        self.assertEqual(1, self.cpu.p_carry)
        self.assertEqual(0, self.cpu.p_zero)
        self.assertEqual(0, self.cpu.p_sign)

    def test_rol_memory(self) -> None:
        self.cpu.p_carry = 1
        self.write_bytes(START_PC, [0x26, 0x02])
        self.write_bytes(0x02, [0x80])

        self.cpu.execute()

        self.assertEqual(0x01, self.cpu.bus.read(0x02))
        self.assertEqual(1, self.cpu.p_carry)
        self.assertEqual(0, self.cpu.p_zero)
        self.assertEqual(0, self.cpu.p_sign)

    def test_ror_memory_to_negative(self) -> None:
        self.cpu.p_carry = 1
        self.write_bytes(START_PC, [0x66, 0x02])
        self.write_bytes(0x02, [0x02])

        self.cpu.execute()

        self.assertEqual(0x81, self.cpu.bus.read(0x02))
        self.assertEqual(0, self.cpu.p_carry)
        self.assertEqual(0, self.cpu.p_zero)
        self.assertEqual(1, self.cpu.p_sign)

    def test_lsr_to_zero(self) -> None:
        self.write_bytes(START_PC, [0x46, 0x02])
        self.write_bytes(0x02, [0x01])

        self.cpu.execute()

        self.assertEqual(0x00, self.cpu.bus.read(0x02))
        self.assertEqual(1, self.cpu.p_carry)
        self.assertEqual(1, self.cpu.p_zero)
        self.assertEqual(0, self.cpu.p_sign)

    def test_asl_accumulator(self) -> None:
        self.cpu.a = 0b10001011
        self.write_bytes(START_PC, [0x0A])

        self.cpu.execute()

        self.assertEqual(0x16, self.cpu.a)
        self.assertEqual(1, self.cpu.p_carry)
        self.assertEqual(0, self.cpu.p_zero)
        self.assertEqual(0, self.cpu.p_sign)

    def test_lsr_accumulator_to_zero(self) -> None:
        self.cpu.a = 0b00000001
        self.write_bytes(START_PC, [0x4A])

        self.cpu.execute()

        self.assertEqual(0x00, self.cpu.a)
        self.assertEqual(1, self.cpu.p_carry)
        self.assertEqual(1, self.cpu.p_zero)
        self.assertEqual(0, self.cpu.p_sign)

    def test_rol_accumulator_with_carry(self) -> None:
        self.cpu.a = 0b10000010
        self.cpu.p_carry = 1
        self.write_bytes(START_PC, [0x2A])

        self.cpu.execute()

        self.assertEqual(0x05, self.cpu.a)
        self.assertEqual(1, self.cpu.p_carry)
        self.assertEqual(0, self.cpu.p_zero)
        self.assertEqual(0, self.cpu.p_sign)

    def test_ror_accumulator_sets_sign_flag(self) -> None:
        self.cpu.a = 0b01000100
        self.cpu.p_carry = 1
        self.write_bytes(START_PC, [0x6A])

        self.cpu.execute()

        self.assertEqual(0xA2, self.cpu.a)
        self.assertEqual(0, self.cpu.p_carry)
        self.assertEqual(0, self.cpu.p_zero)
        self.assertEqual(1, self.cpu.p_sign)

    def test_jmp(self) -> None:
        self.write_bytes(START_PC, [0x4C, 0xDC, 0xAC])

        self.cpu.execute()

        self.assertEqual(0xACDC, self.cpu.pc)

    def test_jmp_ind(self) -> None:
        self.write_bytes(START_PC, [0x6C, 0xDC, 0x0C])
        self.write_bytes(0x0CDC, [0xDE, 0xDE])

        self.cpu.execute()

        self.assertEqual(0xDEDE, self.cpu.pc)

    def test_jmp_ind_cross(self) -> None:
        self.write_bytes(START_PC, [0x6C, 0xFF, 0x0C])
        self.write_bytes(0x0CFF, [0xDE, 0xDE])
        self.write_bytes(0x0C00, [0xAA])

        self.cpu.execute()

        self.assertEqual(0xAADE, self.cpu.pc)

    def test_jsr(self) -> None:
        initial_pc = 0x0FFF
        self.cpu.pc = initial_pc
        self.cpu.s = 0xFF

        self.write_bytes(initial_pc, [0x20, 0x00, 0x02])

        self.cpu.execute()

        expected_high = 0x10
        expected_low = 0x01

        self.assertEqual(0x0200, self.cpu.pc)
        self.assertEqual(0xFD, self.cpu.s)

        self.assertEqual(expected_high, self.cpu.bus.read(0x01FF))
        self.assertEqual(expected_low, self.cpu.bus.read(0x01FE))

    def test_rts_restores_pc_plus_one(self) -> None:
        self.cpu.s = 0xFF

        self.cpu.bus.write(0x01FF, 0x10)
        self.cpu.bus.write(0x01FE, 0x01)

        self.cpu.s = 0xFD

        self.write_bytes(START_PC, [0x60])

        self.cpu.execute()

        self.assertEqual(0x1002, self.cpu.pc)
        self.assertEqual(0xFF, self.cpu.s)

    def test_rti_restores_flags_and_exact_pc(self) -> None:
        self.cpu.s = 0xFF
        self.cpu.bus.write(0x01FF, 0x20)
        self.cpu.bus.write(0x01FE, 0x50)
        status_payload = 0b11000001
        self.cpu.bus.write(0x01FD, status_payload)
        self.cpu.s = 0xFC
        self.write_bytes(START_PC, [0x40])

        self.cpu.execute()

        self.assertEqual(0x2050, self.cpu.pc)
        self.assertEqual(0xFF, self.cpu.s)
        self.assertEqual(1, self.cpu.p_sign)
        self.assertEqual(1, self.cpu.p_overflow)
        self.assertEqual(1, self.cpu.p_carry)
        self.assertEqual(0, self.cpu.p_zero)
        self.assertEqual(0, self.cpu.p_irq)

    def test_bpl_backward_cross_page(self) -> None:
        backward_steps: U8 = -4
        self.write_bytes(START_PC, [0x10, (backward_steps & 0xFF)])

        cycles = self.cpu.execute()

        self.assertEqual(START_PC - 2, self.cpu.pc)
        self.assertEqual(4, cycles)

    def test_bpl_backward_same_page(self) -> None:
        safe_start_pc = 0x1010
        self.cpu.pc = safe_start_pc

        backward_steps = -4
        self.write_bytes(safe_start_pc, [0x10, (backward_steps & 0xFF)])

        cycles = self.cpu.execute()

        self.assertEqual(0x100E, self.cpu.pc)
        self.assertEqual(3, cycles)

    def test_bpl_backward_no_branch(self) -> None:
        self.cpu.p_sign = 1
        safe_start_pc = 0x1010
        self.cpu.pc = safe_start_pc

        backward_steps = -4
        self.write_bytes(safe_start_pc, [0x10, (backward_steps & 0xFF)])

        cycles = self.cpu.execute()

        self.assertEqual(safe_start_pc + 2, self.cpu.pc)
        self.assertEqual(2, cycles)

    def test_bmi(self) -> None:
        safe_start_pc = 0x1010
        self.cpu.pc = safe_start_pc
        self.cpu.p_sign = 0x1

        backward_steps = -4
        self.write_bytes(safe_start_pc, [0x30, (backward_steps & 0xFF)])

        cycles = self.cpu.execute()

        self.assertEqual(0x100E, self.cpu.pc)
        self.assertEqual(3, cycles)

    def test_bvs(self) -> None:
        safe_start_pc = 0x1010
        self.cpu.pc = safe_start_pc
        self.cpu.p_overflow = 0x1

        backward_steps = -4
        self.write_bytes(safe_start_pc, [0x70, (backward_steps & 0xFF)])

        cycles = self.cpu.execute()

        self.assertEqual(0x100E, self.cpu.pc)
        self.assertEqual(3, cycles)

    def test_bvc(self) -> None:
        safe_start_pc = 0x1010
        self.cpu.pc = safe_start_pc
        self.cpu.p_overflow = 0x0

        backward_steps = -4
        self.write_bytes(safe_start_pc, [0x50, (backward_steps & 0xFF)])

        cycles = self.cpu.execute()

        self.assertEqual(0x100E, self.cpu.pc)
        self.assertEqual(3, cycles)

    def test_bcc(self) -> None:
        safe_start_pc = 0x1010
        self.cpu.pc = safe_start_pc
        self.cpu.p_carry = 0x0

        backward_steps = -4
        self.write_bytes(safe_start_pc, [0x90, (backward_steps & 0xFF)])

        cycles = self.cpu.execute()

        self.assertEqual(0x100E, self.cpu.pc)
        self.assertEqual(3, cycles)

    def test_bcs(self) -> None:
        safe_start_pc = 0x1010
        self.cpu.pc = safe_start_pc
        self.cpu.p_carry = 0x1

        backward_steps = -4
        self.write_bytes(safe_start_pc, [0xB0, (backward_steps & 0xFF)])

        cycles = self.cpu.execute()

        self.assertEqual(0x100E, self.cpu.pc)
        self.assertEqual(3, cycles)

    def test_bne(self) -> None:
        safe_start_pc = 0x1010
        self.cpu.pc = safe_start_pc
        self.cpu.p_zero = 0x0

        backward_steps = -4
        self.write_bytes(safe_start_pc, [0xD0, (backward_steps & 0xFF)])

        cycles = self.cpu.execute()

        self.assertEqual(0x100E, self.cpu.pc)
        self.assertEqual(3, cycles)

    def test_beq(self) -> None:
        safe_start_pc = 0x1010
        self.cpu.pc = safe_start_pc
        self.cpu.p_zero = 0x1

        backward_steps = -4
        self.write_bytes(safe_start_pc, [0xF0, (backward_steps & 0xFF)])

        cycles = self.cpu.execute()

        self.assertEqual(0x100E, self.cpu.pc)
        self.assertEqual(3, cycles)

    def test_brk(self) -> None:
        self.cpu.p_irq = 0x0
        zelda = Cartridge()
        zelda.load(f"{CARTRIDGE_PATH}zelda/Zelda.NES")
        self.cpu.bus.cartridge = zelda
        padding = 0xA1
        self.write_bytes(START_PC, [0x00, padding])

        cycles = self.cpu.execute()

        self.assertEqual(0xC62A, self.cpu.pc)
        self.assertEqual(0x0, self.cpu.p_brk)
        self.assertEqual(0x1, self.cpu.p_irq)
        self.assertEqual(7, cycles)

    def test_nop(self) -> None:
        self.write_bytes(START_PC, [0xEA])

        cycles = self.cpu.execute()

        self.assertEqual(2, cycles)
