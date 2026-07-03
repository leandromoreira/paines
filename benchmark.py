import time
from pathlib import Path
from paines.ram.memory import RAM
from paines.bus.bus import CPUBus
from paines.cpu.cpu import CPU6502
from paines.cartridge.cartridge import Cartridge


def setup_cpu() -> CPU6502:
    ram = RAM()
    nes_test = Cartridge()
    nes_test.load("tests/cartridge/nestest.nes")
    bus = CPUBus(ram=ram, cartridge=nes_test)
    cpu = CPU6502(bus=bus, debug=False)

    cpu.pc = 0xC000
    cpu.s = 0xFD
    cpu.p_irq = 0x1
    cpu.p_unused = 0x1
    cpu.p_brk = 0x0
    cpu.compose_p()
    return cpu


def run_sustained_benchmark() -> None:
    for _ in range(100):
        cpu = setup_cpu()
        for _ in range(8991):
            cpu.execute()

    cpu = setup_cpu()

    start_time = time.perf_counter()
    for _ in range(8991):
        cpu.execute()
    end_time = time.perf_counter()

    duration_ms = (end_time - start_time) * 1000
    cycles = 26553

    print(f"\n--------------------------------------------------------")
    print(f"Warmed-up CPU Execution Time: {duration_ms:.6f} ms")
    print(f"NES CPU Cycles               : {cycles}")
    print(f"Real time / NES CPU Cycles   : {duration_ms / cycles:.6f} ms")
    print(f"--------------------------------------------------------")


if __name__ == "__main__":
    run_sustained_benchmark()
