from typing import Callable

from paines.bus.bus import CPUBus, cpu_bus_builder
from paines.types import U16, U8


class Instruction:
    def __init__(
        self,
        name: str,
        execute: Callable[[U8], bool],
        mode: Callable[[], tuple[U16, bool]],
        cycles: U8,
        op_code: U8,
    ) -> None:
        self.name = name
        self.execute = execute
        self.mode = mode
        self.cycles = cycles
        self.op_code = op_code


class DebugTrace:
    def __init__(self, address: U16, value: U8) -> None:
        self.address = address
        self.value = value


class CPU6502:
    def __init__(self, bus: CPUBus = cpu_bus_builder(), debug: bool = False) -> None:
        self.pc: U16 = 0xFFFC
        self.a: U8 = 0x00
        self.x: U8 = 0x00
        self.y: U8 = 0x00
        self.s: U8 = 0xFD
        self.p_carry: U8 = 0x0
        self.p_zero: U8 = 0x0
        self.p_irq: U8 = 0x1
        self.p_dcm: U8 = 0x0
        self.p_brk: U8 = 0x0
        self.p_unused: U8 = 0x1
        self.p_overflow: U8 = 0x0
        self.p_sign: U8 = 0x0
        self.p: U8 = 0x0

        self.bus = bus
        self.total_cycle: int = 0
        self.debug = debug
        self.traces: list[str] = []
        self.debug_file = open("output.txt", "a")

        self.instruction_set: dict[U8, Instruction] = {}
        self.init_table()

    def reset(self) -> U8:
        low = self.bus.read(0xFFFC)
        high = self.bus.read(0xFFFD)
        self.pc = (high << 8) | low
        self.s = 0xFD
        self.p_irq = 0x1
        self.compose_p()
        return 7

    def compose_p(self) -> None:
        self.p = (
            self.p_carry
            | (self.p_zero << 1)
            | (self.p_irq << 2)
            | (self.p_dcm << 3)
            | (self.p_brk << 4)
            | (self.p_unused << 5)
            | (self.p_overflow << 6)
            | (self.p_sign << 7)
        )

    def check_nz(self, value: U8) -> None:
        self.p_sign = (value >> 7) & 1
        self.p_zero = 1 if value == 0 else 0

    def _mode_implied(self) -> tuple[U16, bool]:
        return 0, False

    def _mode_imm(self) -> tuple[U16, bool]:
        addr = self.pc
        self.pc += 1
        return addr, False

    def _mode_zp(self) -> tuple[U16, bool]:
        addr = self.bus.read(self.pc)
        self.pc += 1
        return addr & 0xFF, False

    def _mode_zp_x(self) -> tuple[U16, bool]:
        addr, _ = self._mode_zp()
        return (addr + self.x) & 0xFF, False

    def _mode_zp_y(self) -> tuple[U16, bool]:
        addr, _ = self._mode_zp()
        return (addr + self.y) & 0xFF, False

    def _mode_abs(self) -> tuple[U16, bool]:
        low = self.bus.read(self.pc)
        self.pc += 1
        high = self.bus.read(self.pc)
        self.pc += 1
        return (high << 8) | low, False

    def _mode_abs_x(self) -> tuple[U16, bool]:
        base, _ = self._mode_abs()
        final: U16 = (base + self.x) & 0xFFFF
        page_crossed = (final & 0xFF00) != (base & 0xFF00)
        return final, page_crossed

    def _mode_abs_y(self) -> tuple[U16, bool]:
        base, _ = self._mode_abs()
        final: U16 = (base + self.y) & 0xFFFF
        page_crossed = (final & 0xFF00) != (base & 0xFF00)
        return final, page_crossed

    def _mode_ind_x(self) -> tuple[U16, bool]:
        base = self.bus.read(self.pc)
        self.pc += 1
        ptr: U16 = (base + self.x) & 0xFF
        low = self.bus.read(ptr)
        high = self.bus.read((ptr + 1) & 0xFF)
        return (high << 8) | low, False

    def _mode_ind_y(self) -> tuple[U16, bool]:
        ptr = self.bus.read(self.pc)
        self.pc += 1
        low = self.bus.read(ptr)
        high = self.bus.read((ptr + 1) & 0xFF)
        base: U16 = (high << 8) | low
        final: U16 = (base + self.y) & 0xFFFF
        page_crossed = (final & 0xFF00) != (base & 0xFF00)
        return final, page_crossed

    def execute(self) -> U8:
        cycles: U8 = 0
        initial_address: U16 = self.pc
        op_code: U8 = self.bus.read(self.pc)
        self.pc += 1

        instruction = self.instruction_set.get(op_code)
        if instruction is None:
            raise NotImplementedError(f"Opcode {hex(op_code)} not implemented!")

        operand_address = self.pc
        addr, page_crossed = instruction.mode()

        if self.debug:
            self.perform_debug(instruction, op_code, initial_address, operand_address)

        allows_page_penalty = instruction.execute(addr)
        cycles += instruction.cycles
        if allows_page_penalty and page_crossed:
            cycles += 1

        self.total_cycle += cycles
        return cycles

    def perform_debug(
        self,
        instruction: Instruction,
        op_code: U8,
        initial_address: U16,
        operand_address: U16,
    ) -> None:
        operand_length: U8 = self.pc - operand_address
        bytes_for_debug: list[DebugTrace] = [
            DebugTrace(initial_address, op_code),
        ]
        for i in range(operand_length):
            # TODO: should be careful by reading IO mm
            bytes_for_debug.append(
                DebugTrace(
                    initial_address + 1 + i, self.bus.peek(initial_address + 1 + i)
                )
            )
        self.handle_debug_trace(bytes_for_debug, instruction)

    # helper to print expected nes test format
    # C000  4C F5 C5  JMP $C5F5                       A:00 X:00 Y:00 P:24 SP:FD PPU:  0, 21 CYC:7
    # https://github.com/christopherpow/nes-test-roms/blob/master/other/nestest.log
    def handle_debug_trace(
        self, memory_slice: list[DebugTrace], instruction: Instruction
    ) -> None:
        asm_trace = instruction.name
        if len(memory_slice) == 2:
            raw_operand = memory_slice[1].value
            asm_trace = instruction.name.format(raw_operand)
        elif len(memory_slice) == 3:
            low = memory_slice[1].value
            high = memory_slice[2].value
            raw_operand = (high << 8) | low
            asm_trace = instruction.name.format(raw_operand)

        opcode_plus_operand_bytes: str = "{:02X}".format(memory_slice[0].value)
        for i in range(1, len(memory_slice)):
            opcode_plus_operand_bytes += " {:02X}".format(memory_slice[i].value)
        bytes_str = f"{opcode_plus_operand_bytes:<9}"
        asm_trace = f"{asm_trace:<32}"
        self.compose_p()
        log_line = f"{memory_slice[0].address:04X}  {bytes_str} {asm_trace}A:{self.a:02X} X:{self.x:02X} Y:{self.y:02X} P:{self.p:02X} SP:{self.s:02X}"

        self.debug_file.write(f"{log_line}\n")
        self.debug_file.flush()
        self.traces.append(log_line)

    def init_table(self) -> None:
        self.instruction_set[0xA8] = Instruction(
            "TAY", self.tay, self._mode_implied, 2, 0xA8
        )
        self.instruction_set[0xAA] = Instruction(
            "TAX", self.tax, self._mode_implied, 2, 0xAA
        )
        self.instruction_set[0xBA] = Instruction(
            "TSX", self.tsx, self._mode_implied, 2, 0xBA
        )
        self.instruction_set[0x98] = Instruction(
            "TYA", self.tya, self._mode_implied, 2, 0x98
        )
        self.instruction_set[0x8A] = Instruction(
            "TXA", self.txa, self._mode_implied, 2, 0x8A
        )
        self.instruction_set[0x9A] = Instruction(
            "TXS", self.txs, self._mode_implied, 2, 0x9A
        )
        self.instruction_set[0xA9] = Instruction(
            "LDA #{:02X}", self.lda, self._mode_imm, 2, 0xA9
        )
        self.instruction_set[0xA2] = Instruction(
            "LDX #{:02X}", self.ldx, self._mode_imm, 2, 0xA2
        )
        self.instruction_set[0xA0] = Instruction(
            "LDY #{:02X}", self.ldy, self._mode_imm, 2, 0xA0
        )
        self.instruction_set[0xA4] = Instruction(
            "LDY {:02X}", self.ldy, self._mode_zp, 3, 0xA4
        )
        self.instruction_set[0xB4] = Instruction(
            "LDY {:02X}, X", self.ldy, self._mode_zp_x, 4, 0xB4
        )
        self.instruction_set[0xAC] = Instruction(
            "LDY {:04X}", self.ldy, self._mode_abs, 4, 0xAC
        )
        self.instruction_set[0xBC] = Instruction(
            "LDY {:04X}, X", self.ldy, self._mode_abs_x, 4, 0xBC
        )

        self.instruction_set[0xA5] = Instruction(
            "LDA {:02X}", self.lda, self._mode_zp, 3, 0xA5
        )
        self.instruction_set[0xB5] = Instruction(
            "LDA {:02X}, X", self.lda, self._mode_zp_x, 4, 0xB5
        )
        self.instruction_set[0xAD] = Instruction(
            "LDA {:04X}", self.lda, self._mode_abs, 4, 0xAD
        )
        self.instruction_set[0xBD] = Instruction(
            "LDA {:04X}, X", self.lda, self._mode_abs_x, 4, 0xBD
        )
        self.instruction_set[0xB9] = Instruction(
            "LDA {:04X}, Y", self.lda, self._mode_abs_y, 4, 0xB9
        )
        self.instruction_set[0xA1] = Instruction(
            "LDA ({:02X}, X)", self.lda, self._mode_ind_x, 6, 0xA1
        )
        self.instruction_set[0xB1] = Instruction(
            "LDA ({:02X}), Y", self.lda, self._mode_ind_y, 5, 0xB1
        )
        self.instruction_set[0xA6] = Instruction(
            "LDX {:02X}", self.ldx, self._mode_zp, 3, 0xA6
        )
        self.instruction_set[0xB6] = Instruction(
            "LDX {:02X}, Y", self.ldx, self._mode_zp_y, 4, 0xB6
        )
        self.instruction_set[0xAE] = Instruction(
            "LDX {:04X}", self.ldx, self._mode_abs, 4, 0xAE
        )
        self.instruction_set[0xBE] = Instruction(
            "LDX {:04X}, Y", self.ldx, self._mode_abs_y, 4, 0xBE
        )

        self.instruction_set[0x85] = Instruction(
            "STA {:02X}", self.sta, self._mode_zp, 3, 0x85
        )
        self.instruction_set[0x95] = Instruction(
            "STA {:02X}, X", self.sta, self._mode_zp_x, 4, 0x95
        )
        self.instruction_set[0x8D] = Instruction(
            "STA {:04X}", self.sta, self._mode_abs, 4, 0x8D
        )
        self.instruction_set[0x9D] = Instruction(
            "STA {:04X}, X", self.sta, self._mode_abs_x, 5, 0x9D
        )
        self.instruction_set[0x99] = Instruction(
            "STA {:04X}, Y", self.sta, self._mode_abs_y, 5, 0x99
        )
        self.instruction_set[0x81] = Instruction(
            "STA ({:02X}, X)", self.sta, self._mode_ind_x, 6, 0x81
        )
        self.instruction_set[0x91] = Instruction(
            "STA ({:02X}), Y", self.sta, self._mode_ind_y, 6, 0x91
        )
        self.instruction_set[0x86] = Instruction(
            "STX {:02X}", self.stx, self._mode_zp, 3, 0x86
        )
        self.instruction_set[0x96] = Instruction(
            "STX {:02X}, Y", self.stx, self._mode_zp_y, 4, 0x96
        )
        self.instruction_set[0x8E] = Instruction(
            "STX {:04X}", self.stx, self._mode_abs, 4, 0x8E
        )
        self.instruction_set[0x84] = Instruction(
            "STY {:02X}", self.sty, self._mode_zp, 3, 0x84
        )
        self.instruction_set[0x94] = Instruction(
            "STY {:02X}, X", self.sty, self._mode_zp_x, 4, 0x94
        )
        self.instruction_set[0x8C] = Instruction(
            "STY {:04X}", self.sty, self._mode_abs, 4, 0x8C
        )

    def sty(self, address: U16) -> bool:
        self.bus.write(address, self.y)
        return False

    def stx(self, address: U16) -> bool:
        self.bus.write(address, self.x)
        return False

    def sta(self, address: U16) -> bool:
        self.bus.write(address, self.a)
        return False

    def lda(self, address: U16) -> bool:
        operand: U8 = self.bus.read(address)
        self.a = operand
        self.check_nz(self.a)
        return True

    def ldx(self, address: U16) -> bool:
        operand: U8 = self.bus.read(address)
        self.x = operand
        self.check_nz(self.x)
        return True

    def ldy(self, address: U16) -> bool:
        operand: U8 = self.bus.read(address)
        self.y = operand
        self.check_nz(self.y)
        return True

    def tay(self, _: U16) -> bool:
        self.y = self.a
        self.check_nz(self.y)
        return False

    def tya(self, _: U16) -> bool:
        self.a = self.y
        self.check_nz(self.a)
        return False

    def tax(self, _: U16) -> bool:
        self.x = self.a
        self.check_nz(self.x)
        return False

    def txa(self, _: U16) -> bool:
        self.a = self.x
        self.check_nz(self.a)
        return False

    def txs(self, _: U16) -> bool:
        self.s = self.x
        return False

    def tsx(self, _: U16) -> bool:
        self.x = self.s
        self.check_nz(self.x)
        return False
