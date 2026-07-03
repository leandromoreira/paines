import unittest
from pathlib import Path
import re
import time

from paines.ram.memory import RAM
from paines.bus.bus import CPUBus
from paines.cpu.cpu import CPU6502
from paines.cartridge.cartridge import Cartridge
from paines.types import U16, U8

START_PC: U16 = 0x0FFF
CARTRIDGE_PATH = f"{Path(__file__).parent.parent}/tests/cartridge/"
NESTEST_PATH = f"{CARTRIDGE_PATH}nestest.nes"
NESTEST_LOG_PATH = "nes_test.log"
NESTEST_OFFICIAL_LOG_PATH = "nes_test_official.log"
TERMINAL_ADDRESS = 0x8991


class TestNESTests(unittest.TestCase):
    def setUp(self) -> None:
        file_path = Path(NESTEST_LOG_PATH)
        file_path.unlink(missing_ok=True)
        ram = RAM()
        nes_test = Cartridge()
        nes_test.load(NESTEST_PATH)
        bus = CPUBus(ram=ram, cartridge=nes_test)
        cpu = CPU6502(bus=bus, debug=True, file_name=NESTEST_LOG_PATH)

        cpu.pc = 0xC000
        cpu.s = 0xFD
        cpu.p_irq = 0x1
        cpu.p_unused = 0x1
        cpu.p_brk = 0x0
        cpu.compose_p()
        self.cpu = cpu

    def test_nes_tests(self) -> None:
        for _ in range(8991):
            self.cpu.execute()

        self.assertTrue(verify_logs(NESTEST_LOG_PATH, NESTEST_OFFICIAL_LOG_PATH))

        error_code_1 = self.cpu.bus.read(0x0002)
        error_code_2 = self.cpu.bus.read(0x0003)

        self.assertEqual(error_code_1, 0x00)
        self.assertEqual(error_code_2, 0x00)


# Emulator
# C737  B0 03     BCS C73C                        A:00 X:00 Y:00 P:26 SP:FB CYC:38
# Official log
# C737  B0 03     BCS $C73C                       A:00 X:00 Y:00 P:26 SP:FB PPU:  0,114 CYC:38
LOG_PATTERN = re.compile(
    r"^([0-9A-F]{4}).*?A:([0-9A-F]{2})\s+X:([0-9A-F]{2})\s+Y:([0-9A-F]{2})\s+P:([0-9A-F]{2})\s+SP:([0-9A-F]{2}).*?CYC:(\d+)"
)


def verify_logs(log_path: str, official_log_path: str) -> bool:
    with open(log_path) as emulator, open(official_log_path) as official:
        for line_num, (emulator_line, official_line) in enumerate(
            zip(emulator, official), 1
        ):
            match = LOG_PATTERN.match(emulator_line.strip())
            official_match = LOG_PATTERN.match(official_line.strip())

            if not match or not official_match:
                print(f"Row {line_num}: Encountered a malformed log pattern layout.")
                continue

            emulator_state_line_group = match.groups()
            official_state_line_group = official_match.groups()

            o_pc, o_a, o_x, o_y, o_p, o_sp, o_cyc = official_state_line_group
            e_pc, e_a, e_x, e_y, e_p, e_sp, e_cyc = emulator_state_line_group

            if emulator_state_line_group != official_state_line_group:
                print(f"❌ Mismatch identified on instruction row {line_num}!")
                print(
                    f"Expected (Official): PC:{o_pc} A:{o_a} X:{o_x} Y:{o_y} P:{o_p} SP:{o_sp} CYC:{o_cyc}"
                )
                print(
                    f"Received (Emulator): PC:{e_pc} A:{e_a} X:{e_x} Y:{e_y} P:{e_p} SP:{e_sp} CYC:{e_cyc}"
                )
                return False
    return True
