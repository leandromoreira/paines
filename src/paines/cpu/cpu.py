from typing import Callable, Any

from paines.bus.bus import CPUBus, cpu_bus_builder
from paines.types import U16, U8


class Instruction:
    def __init__(
        self,
        name: str,
        execute: Callable[[U8], Any],
        mode: Callable[[], tuple[U16, bool]],
        cycles: U8,
        op_code: U8,
        is_branch: bool = False,
    ) -> None:
        self.name = name
        self.execute = execute
        self.mode = mode
        self.cycles = cycles
        self.op_code = op_code
        self.is_branch = is_branch


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

    def _mode_rel(self) -> tuple[U16, bool]:
        offset = self.bus.read(self.pc)
        self.pc += 1
        signed_offset = offset - 256 if offset >= 0x80 else offset
        destination: U16 = (self.pc + signed_offset) & 0xFFFF
        actual_page_crossed = (destination & 0xFF00) != (self.pc & 0xFF00)
        return destination, actual_page_crossed

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

        allows_page_penalty: bool = False
        has_branched: bool = False

        if instruction.is_branch:
            allows_page_penalty, has_branched = instruction.execute(addr)
        else:
            allows_page_penalty = instruction.execute(addr)

        cycles += instruction.cycles

        if has_branched:
            cycles += 1
            if allows_page_penalty and page_crossed:
                cycles += 1
        elif allows_page_penalty and page_crossed:
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

        if instruction.is_branch:
            raw_operand = memory_slice[1].value
            raw_operand = raw_operand - 256 if raw_operand >= 0x80 else raw_operand
            current_pc = memory_slice[1].address
            asm_trace = instruction.name.format(current_pc + 1 + raw_operand)
        elif len(memory_slice) == 2:
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

        self.instruction_set[0x48] = Instruction(
            "PHA", self.pha, self._mode_implied, 3, 0x48
        )
        self.instruction_set[0x08] = Instruction(
            "PHP", self.php, self._mode_implied, 3, 0x08
        )
        self.instruction_set[0x68] = Instruction(
            "PLA", self.pla, self._mode_implied, 4, 0x68
        )
        self.instruction_set[0x28] = Instruction(
            "PLP", self.plp, self._mode_implied, 4, 0x28
        )
        self.instruction_set[0x69] = Instruction(
            "ADC #{:02X}", self.adc, self._mode_imm, 2, 0x69
        )
        self.instruction_set[0x65] = Instruction(
            "ADC {:02X}", self.adc, self._mode_zp, 3, 0x65
        )
        self.instruction_set[0x75] = Instruction(
            "ADC {:02X}, X", self.adc, self._mode_zp_x, 4, 0x75
        )
        self.instruction_set[0x6D] = Instruction(
            "ADC {:04X}", self.adc, self._mode_abs, 4, 0x6D
        )
        self.instruction_set[0x7D] = Instruction(
            "ADC {:04X}, X", self.adc, self._mode_abs_x, 4, 0x7D
        )
        self.instruction_set[0x79] = Instruction(
            "ADC {:04X}, Y", self.adc, self._mode_abs_y, 4, 0x79
        )
        self.instruction_set[0x61] = Instruction(
            "ADC ({:02X}, X)", self.adc, self._mode_ind_x, 6, 0x61
        )
        self.instruction_set[0x71] = Instruction(
            "ADC ({:02X}), Y", self.adc, self._mode_ind_y, 5, 0x71
        )
        self.instruction_set[0xE9] = Instruction(
            "SBC #{:02X}", self.sbc, self._mode_imm, 2, 0xE9
        )
        self.instruction_set[0xE5] = Instruction(
            "SBC {:02X}", self.sbc, self._mode_zp, 3, 0xE5
        )
        self.instruction_set[0xF5] = Instruction(
            "SBC {:02X}, X", self.sbc, self._mode_zp_x, 4, 0xF5
        )
        self.instruction_set[0xED] = Instruction(
            "SBC {:04X}", self.sbc, self._mode_abs, 4, 0xED
        )
        self.instruction_set[0xFD] = Instruction(
            "SBC {:04X}, X", self.sbc, self._mode_abs_x, 4, 0xFD
        )
        self.instruction_set[0xF9] = Instruction(
            "SBC {:04X}, Y", self.sbc, self._mode_abs_y, 4, 0xF9
        )
        self.instruction_set[0xE1] = Instruction(
            "SBC ({:02X}, X)", self.sbc, self._mode_ind_x, 6, 0xE1
        )
        self.instruction_set[0xF1] = Instruction(
            "SBC ({:02X}), Y", self.sbc, self._mode_ind_y, 5, 0xF1
        )
        self.instruction_set[0x29] = Instruction(
            "AND #{:02X}", self.op_and, self._mode_imm, 2, 0x29
        )
        self.instruction_set[0x25] = Instruction(
            "AND {:02X}", self.op_and, self._mode_zp, 3, 0x25
        )
        self.instruction_set[0x35] = Instruction(
            "AND {:02X}, X", self.op_and, self._mode_zp_x, 4, 0x35
        )
        self.instruction_set[0x2D] = Instruction(
            "AND {:04X}", self.op_and, self._mode_abs, 4, 0x2D
        )
        self.instruction_set[0x3D] = Instruction(
            "AND {:04X}, X", self.op_and, self._mode_abs_x, 4, 0x3D
        )
        self.instruction_set[0x39] = Instruction(
            "AND {:04X}, Y", self.op_and, self._mode_abs_y, 4, 0x39
        )
        self.instruction_set[0x21] = Instruction(
            "AND ({:02X}, X)", self.op_and, self._mode_ind_x, 6, 0x21
        )
        self.instruction_set[0x31] = Instruction(
            "AND ({:02X}), Y", self.op_and, self._mode_ind_y, 5, 0x31
        )
        self.instruction_set[0x09] = Instruction(
            "ORA #{:02X}", self.op_or, self._mode_imm, 2, 0x09
        )
        self.instruction_set[0x05] = Instruction(
            "ORA {:02X}", self.op_or, self._mode_zp, 3, 0x05
        )
        self.instruction_set[0x15] = Instruction(
            "ORA {:02X}, X", self.op_or, self._mode_zp_x, 4, 0x15
        )
        self.instruction_set[0x0D] = Instruction(
            "ORA {:04X}", self.op_or, self._mode_abs, 4, 0x0D
        )
        self.instruction_set[0x1D] = Instruction(
            "ORA {:04X}, X", self.op_or, self._mode_abs_x, 4, 0x1D
        )
        self.instruction_set[0x19] = Instruction(
            "ORA {:04X}, Y", self.op_or, self._mode_abs_y, 4, 0x19
        )
        self.instruction_set[0x01] = Instruction(
            "ORA ({:02X}, X)", self.op_or, self._mode_ind_x, 6, 0x01
        )
        self.instruction_set[0x11] = Instruction(
            "ORA ({:02X}), Y", self.op_or, self._mode_ind_y, 5, 0x11
        )
        self.instruction_set[0x49] = Instruction(
            "EOR #{:02X}", self.op_xor, self._mode_imm, 2, 0x49
        )
        self.instruction_set[0x45] = Instruction(
            "EOR {:02X}", self.op_xor, self._mode_zp, 3, 0x45
        )
        self.instruction_set[0x55] = Instruction(
            "EOR {:02X}, X", self.op_xor, self._mode_zp_x, 4, 0x55
        )
        self.instruction_set[0x4D] = Instruction(
            "EOR {:04X}", self.op_xor, self._mode_abs, 4, 0x4D
        )
        self.instruction_set[0x5D] = Instruction(
            "EOR {:04X}, X", self.op_xor, self._mode_abs_x, 4, 0x5D
        )
        self.instruction_set[0x59] = Instruction(
            "EOR {:04X}, Y", self.op_xor, self._mode_abs_y, 4, 0x59
        )
        self.instruction_set[0x41] = Instruction(
            "EOR ({:02X}, X)", self.op_xor, self._mode_ind_x, 6, 0x41
        )
        self.instruction_set[0x51] = Instruction(
            "EOR ({:02X}), Y", self.op_xor, self._mode_ind_y, 5, 0x51
        )
        self.instruction_set[0xC9] = Instruction(
            "CMP #{:02X}", self.cmp, self._mode_imm, 2, 0xC9
        )
        self.instruction_set[0xC9] = Instruction(
            "CMP #{:02X}", self.cmp, self._mode_imm, 2, 0xC9
        )
        self.instruction_set[0xC5] = Instruction(
            "CMP {:02X}", self.cmp, self._mode_zp, 3, 0xC5
        )
        self.instruction_set[0xD5] = Instruction(
            "CMP {:02X}, X", self.cmp, self._mode_zp_x, 4, 0xD5
        )
        self.instruction_set[0xCD] = Instruction(
            "CMP {:04X}", self.cmp, self._mode_abs, 4, 0xCD
        )
        self.instruction_set[0xDD] = Instruction(
            "CMP {:04X}, X", self.cmp, self._mode_abs_x, 4, 0xDD
        )
        self.instruction_set[0xD9] = Instruction(
            "CMP {:04X}, Y", self.cmp, self._mode_abs_y, 4, 0xD9
        )
        self.instruction_set[0xC1] = Instruction(
            "CMP ({:02X}, X)", self.cmp, self._mode_ind_x, 6, 0xC1
        )
        self.instruction_set[0xD1] = Instruction(
            "CMP ({:02X}), Y", self.cmp, self._mode_ind_y, 5, 0xD1
        )
        self.instruction_set[0xE0] = Instruction(
            "CPX #{:02X}", self.cpx, self._mode_imm, 2, 0xE0
        )
        self.instruction_set[0xE4] = Instruction(
            "CPX {:02X}", self.cpx, self._mode_zp, 3, 0xE4
        )
        self.instruction_set[0xEC] = Instruction(
            "CPX {:04X}", self.cpx, self._mode_abs, 4, 0xEC
        )
        self.instruction_set[0xC0] = Instruction(
            "CPY #{:02X}", self.cpy, self._mode_imm, 2, 0xC0
        )
        self.instruction_set[0xC4] = Instruction(
            "CPY {:02X}", self.cpy, self._mode_zp, 3, 0xC4
        )
        self.instruction_set[0xCC] = Instruction(
            "CPY {:04X}", self.cpy, self._mode_abs, 4, 0xCC
        )
        self.instruction_set[0x24] = Instruction(
            "BIT {:02X}", self.bit, self._mode_zp, 3, 0x24
        )
        self.instruction_set[0x2C] = Instruction(
            "BIT {:04X}", self.bit, self._mode_abs, 4, 0x2C
        )
        self.instruction_set[0xE6] = Instruction(
            "INC {:02X}", self.inc, self._mode_zp, 5, 0xE6
        )
        self.instruction_set[0xF6] = Instruction(
            "INC {:02X}, X", self.inc, self._mode_zp_x, 6, 0xF6
        )
        self.instruction_set[0xEE] = Instruction(
            "INC {:04X}", self.inc, self._mode_abs, 6, 0xEE
        )
        self.instruction_set[0xFE] = Instruction(
            "INC {:04X}, X", self.inc, self._mode_abs_x, 7, 0xFE
        )
        self.instruction_set[0xC6] = Instruction(
            "DEC {:02X}", self.dec, self._mode_zp, 5, 0xC6
        )
        self.instruction_set[0xD6] = Instruction(
            "DEC {:02X}, X", self.dec, self._mode_zp_x, 6, 0xD6
        )
        self.instruction_set[0xCE] = Instruction(
            "DEC {:04X}", self.dec, self._mode_abs, 6, 0xCE
        )
        self.instruction_set[0xDE] = Instruction(
            "DEC {:04X}, X", self.dec, self._mode_abs_x, 7, 0xDE
        )
        self.instruction_set[0x0A] = Instruction(
            "ASL A", self.asl_acc, self._mode_implied, 2, 0x0A
        )
        self.instruction_set[0x06] = Instruction(
            "ASL {:02X}", self.asl, self._mode_zp, 5, 0x06
        )
        self.instruction_set[0x16] = Instruction(
            "ASL {:02X}, X", self.asl, self._mode_zp_x, 6, 0x16
        )
        self.instruction_set[0x0E] = Instruction(
            "ASL {:04X}", self.asl, self._mode_abs, 6, 0x0E
        )
        self.instruction_set[0x1E] = Instruction(
            "ASL {:04X}, X", self.asl, self._mode_abs_x, 7, 0x1E
        )
        self.instruction_set[0x4A] = Instruction(
            "LSR A", self.lsr_acc, self._mode_implied, 2, 0x4A
        )
        self.instruction_set[0x46] = Instruction(
            "LSR {:02X}", self.lsr, self._mode_zp, 5, 0x46
        )
        self.instruction_set[0x56] = Instruction(
            "LSR {:02X}, X", self.lsr, self._mode_zp_x, 6, 0x56
        )
        self.instruction_set[0x4E] = Instruction(
            "LSR {:04X}", self.lsr, self._mode_abs, 6, 0x4E
        )
        self.instruction_set[0x5E] = Instruction(
            "LSR {:04X}, X", self.lsr, self._mode_abs_x, 7, 0x5E
        )
        self.instruction_set[0x2A] = Instruction(
            "ROL A", self.rol_acc, self._mode_implied, 2, 0x2A
        )
        self.instruction_set[0x26] = Instruction(
            "ROL {:02X}", self.rol, self._mode_zp, 5, 0x26
        )
        self.instruction_set[0x36] = Instruction(
            "ROL {:02X}, X", self.rol, self._mode_zp_x, 6, 0x36
        )
        self.instruction_set[0x2E] = Instruction(
            "ROL {:04X}", self.rol, self._mode_abs, 6, 0x2E
        )
        self.instruction_set[0x3E] = Instruction(
            "ROL {:04X}, X", self.rol, self._mode_abs_x, 7, 0x3E
        )
        self.instruction_set[0x6A] = Instruction(
            "ROR A", self.ror_acc, self._mode_implied, 2, 0x6A
        )
        self.instruction_set[0x66] = Instruction(
            "ROR {:02X}", self.ror, self._mode_zp, 5, 0x66
        )
        self.instruction_set[0x76] = Instruction(
            "ROR {:02X}, X", self.ror, self._mode_zp_x, 6, 0x76
        )
        self.instruction_set[0x6E] = Instruction(
            "ROR {:04X}", self.ror, self._mode_abs, 6, 0x6E
        )
        self.instruction_set[0x7E] = Instruction(
            "ROR {:04X}, X", self.ror, self._mode_abs_x, 7, 0x7E
        )
        self.instruction_set[0x4C] = Instruction(
            "JMP {:04X}", self.jmp, self._mode_abs, 3, 0x4C
        )
        self.instruction_set[0x6C] = Instruction(
            "JMP ({:04X})", self.jmp_i, self._mode_abs, 5, 0x6C
        )
        self.instruction_set[0x20] = Instruction(
            "JSR {:04X}", self.jsr, self._mode_abs, 6, 0x20
        )
        self.instruction_set[0x60] = Instruction(
            "RTS", self.rts, self._mode_implied, 6, 0x60
        )
        self.instruction_set[0x40] = Instruction(
            "RTI", self.rti, self._mode_implied, 6, 0x40
        )
        self.instruction_set[0x10] = Instruction(
            "BPL {:04X}", self.bpl, self._mode_rel, 2, 0x10, is_branch=True
        )
        self.instruction_set[0x30] = Instruction(
            "BMI {:04X}", self.bmi, self._mode_rel, 2, 0x30, is_branch=True
        )
        self.instruction_set[0x50] = Instruction(
            "BVC {:04X}", self.bvc, self._mode_rel, 2, 0x50, is_branch=True
        )
        self.instruction_set[0x70] = Instruction(
            "BVS {:04X}", self.bvs, self._mode_rel, 2, 0x70, is_branch=True
        )
        self.instruction_set[0x90] = Instruction(
            "BCC {:04X}", self.bcc, self._mode_rel, 2, 0x90, is_branch=True
        )
        self.instruction_set[0xB0] = Instruction(
            "BCS {:04X}", self.bcs, self._mode_rel, 2, 0xB0, is_branch=True
        )
        self.instruction_set[0xD0] = Instruction(
            "BNE {:04X}", self.bne, self._mode_rel, 2, 0xD0, is_branch=True
        )
        self.instruction_set[0xF0] = Instruction(
            "BEQ {:04X}", self.beq, self._mode_rel, 2, 0xF0, is_branch=True
        )
        self.instruction_set[0x00] = Instruction(
            "BRK", self.brk, self._mode_implied, 7, 0x00
        )

    def brk(self, _: U16) -> bool:
        return_address: U16 = (self.pc + 1) & 0xFFFF
        high_pc: U8 = (return_address >> 8) & 0xFF
        low_pc: U8 = return_address & 0xFF

        self.bus.write(0x0100 | self.s, high_pc)
        self.s = (self.s - 1) & 0xFF

        self.bus.write(0x0100 | self.s, low_pc)
        self.s = (self.s - 1) & 0xFF

        self.compose_p()
        pushed_status: U8 = self.p | 0x10 | 0x20
        self.bus.write(0x0100 | self.s, pushed_status)
        self.s = (self.s - 1) & 0xFF

        low_vector: U8 = self.bus.read(0xFFFE)
        high_vector: U8 = self.bus.read(0xFFFF)
        self.pc = (high_vector << 8) | low_vector
        self.p_irq = 0x1

        return False

    def beq(self, address: U16) -> tuple[bool, bool]:
        if self.p_zero == 1:
            self.pc = address
            return (True, True)
        return (False, False)

    def bne(self, address: U16) -> tuple[bool, bool]:
        if self.p_zero == 0:
            self.pc = address
            return (True, True)
        return (False, False)

    def bcs(self, address: U16) -> tuple[bool, bool]:
        if self.p_carry == 1:
            self.pc = address
            return (True, True)
        return (False, False)

    def bcc(self, address: U16) -> tuple[bool, bool]:
        if self.p_carry == 0:
            self.pc = address
            return (True, True)
        return (False, False)

    def bvs(self, address: U16) -> tuple[bool, bool]:
        if self.p_overflow == 1:
            self.pc = address
            return (True, True)
        return (False, False)

    def bvc(self, address: U16) -> tuple[bool, bool]:
        if self.p_overflow == 0:
            self.pc = address
            return (True, True)
        return (False, False)

    def bmi(self, address: U16) -> tuple[bool, bool]:
        if self.p_sign == 1:
            self.pc = address
            return (True, True)
        return (False, False)

    def bpl(self, address: U16) -> tuple[bool, bool]:
        if self.p_sign == 0:
            self.pc = address
            return (True, True)
        return (False, False)

    def rti(self, _: U16) -> bool:
        self.s = (self.s + 1) & 0xFF
        status_byte = self.bus.read(0x0100 | self.s)

        self.p_carry = status_byte & 0x01
        self.p_zero = (status_byte >> 1) & 0x01
        self.p_irq = (status_byte >> 2) & 0x01
        self.p_dcm = (status_byte >> 3) & 0x01
        self.p_unused = 0x1
        self.p_brk = 0x0
        self.p_overflow = (status_byte >> 6) & 0x01
        self.p_sign = (status_byte >> 7) & 0x01

        self.s = (self.s + 1) & 0xFF
        low = self.bus.read(0x0100 | self.s)

        self.s = (self.s + 1) & 0xFF
        high = self.bus.read(0x0100 | self.s)

        self.pc = (high << 8) | low

        return False

    def rts(self, _: U16) -> bool:
        self.s = (self.s + 1) & 0xFF
        low = self.bus.read(0x0100 | self.s)

        self.s = (self.s + 1) & 0xFF
        high = self.bus.read(0x0100 | self.s)

        return_address = (high << 8) | low
        self.pc = (return_address + 1) & 0xFFFF

        return False

    def jsr(self, address: U16) -> bool:
        return_address: U16 = (self.pc - 1) & 0xFFFF

        high: U8 = (return_address >> 8) & 0xFF
        low: U8 = return_address & 0xFF

        self.bus.write(0x0100 | self.s, high)
        self.s = (self.s - 1) & 0xFF

        self.bus.write(0x0100 | self.s, low)
        self.s = (self.s - 1) & 0xFF

        self.pc = address
        return False

    def jmp_i(self, address: U16) -> bool:
        low = address
        high: U16 = (address + 1) & 0xFFFF
        if (address & 0x00FF) == 0x00FF:
            high = address & 0xFF00

        target_low = self.bus.read(low)
        target_high = self.bus.read(high)

        self.pc = (target_high << 8) | target_low
        return False

    def jmp(self, address: U16) -> bool:
        self.pc = address
        return False

    def lsr_acc(self, _: U16) -> bool:
        self.p_carry = self.a & 0x1
        new_value = self.a >> 1
        self.a = new_value
        self.check_nz(new_value)
        return False

    def rol_acc(self, _: U16) -> bool:
        old_carry = self.p_carry
        self.p_carry = (self.a >> 7) & 0x1
        new_value = ((self.a << 1) | old_carry) & 0xFF
        self.a = new_value
        self.check_nz(new_value)
        return False

    def ror_acc(self, _: U16) -> bool:
        old_carry = self.p_carry
        self.p_carry = self.a & 0x1
        new_value = (self.a >> 1) | (old_carry << 7)
        self.a = new_value
        self.check_nz(new_value)
        return False

    def asl_acc(self, _: U16) -> bool:
        self.p_carry = (self.a >> 7) & 0x1
        new_value = (self.a << 1) & 0xFF
        self.a = new_value
        self.check_nz(new_value)
        return False

    def asl(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        self.p_carry = (value >> 7) & 0x1
        new_value = (value << 1) & 0xFF
        self.bus.write(address, new_value)
        self.check_nz(new_value)
        return False

    def lsr(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        self.p_carry = value & 0x1
        new_value = value >> 1
        self.bus.write(address, new_value)
        self.check_nz(new_value)
        return False

    def rol(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        old_carry = self.p_carry
        self.p_carry = (value >> 7) & 0x1
        new_value = ((value << 1) | old_carry) & 0xFF
        self.bus.write(address, new_value)
        self.check_nz(new_value)
        return False

    def ror(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        old_carry = self.p_carry
        self.p_carry = value & 0x1
        new_value = (value >> 1) | (old_carry << 7)
        self.bus.write(address, new_value)
        self.check_nz(new_value)
        return False

    def dec(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        new_value: U8 = (value - 1) & 0xFF
        self.bus.write(address, new_value)
        self.check_nz(new_value)
        return False

    def inc(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        new_value: U8 = (value + 1) & 0xFF
        self.bus.write(address, new_value)
        self.check_nz(new_value)
        return False

    def bit(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        self.p_zero = 1 if (self.a & value) == 0 else 0
        self.p_sign = (value >> 7) & 0x1
        self.p_overflow = (value >> 6) & 0x1
        return False

    def cpy(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        result: U8 = (self.y - value) & 0xFF
        self.p_sign = (result >> 7) & 0x1
        self.p_carry = 1 if self.y >= value else 0
        self.p_zero = 1 if self.y == value else 0
        return False

    def cpx(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        result: U8 = (self.x - value) & 0xFF
        self.p_sign = (result >> 7) & 0x1
        self.p_carry = 1 if self.x >= value else 0
        self.p_zero = 1 if self.x == value else 0
        return False

    def cmp(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        result: U8 = (self.a - value) & 0xFF
        self.p_sign = (result >> 7) & 0x1
        self.p_carry = 1 if self.a >= value else 0
        self.p_zero = 1 if self.a == value else 0
        return True

    def op_or(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        self.a = self.a | value
        self.check_nz(self.a)
        return True

    def op_xor(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        self.a = self.a ^ value
        self.check_nz(self.a)
        return True

    def op_and(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        self.a = self.a & value
        self.check_nz(self.a)
        return True

    def sbc(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        return self._adc(value ^ 0xFF)

    def adc(self, address: U16) -> bool:
        value: U8 = self.bus.read(address)
        return self._adc(value)

    def _adc(self, value: U8) -> bool:
        raw_result: int = self.a + value + self.p_carry
        result: U16 = raw_result & 0xFF

        if raw_result > 0xFF:
            self.p_carry = 1
        else:
            self.p_carry = 0

        if (self.a ^ result) & (value ^ result) & 0x80:
            self.p_overflow = 1
        else:
            self.p_overflow = 0

        self.a = result
        self.check_nz(self.a)
        return True

    def plp(self, _: U16) -> bool:
        self.s = (self.s + 1) & 0xFF
        self.p = self.bus.read(0x0100 | self.s)

        self.p_carry = self.p & 0x1
        self.p_zero = (self.p >> 1) & 0x1
        self.p_irq = (self.p >> 2) & 0x1
        self.p_dcm = (self.p >> 3) & 0x1
        self.p_brk = (self.p >> 4) & 0x1
        self.p_unused = (self.p >> 5) & 0x1
        self.p_overflow = (self.p >> 6) & 0x1
        self.p_sign = (self.p >> 7) & 0x1

        return False

    def pla(self, _: U16) -> bool:
        self.s = (self.s + 1) & 0xFF
        self.a = self.bus.read(0x0100 | self.s)
        self.check_nz(self.a)
        return False

    def php(self, _: U16) -> bool:
        self.compose_p()
        self.bus.write(0x0100 | self.s, self.p | 0x30)
        self.s = (self.s - 1) & 0xFF
        return False

    def pha(self, _: U16) -> bool:
        self.bus.write(0x0100 | self.s, self.a)
        self.s = (self.s - 1) & 0xFF
        return False

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
