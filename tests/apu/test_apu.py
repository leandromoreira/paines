import array

from paines.apu.apu import APU, CPU_CLOCK_HZ, SAMPLE_RATE
from paines.apu.channels import LENGTH_TABLE
from paines.bus.bus import CPUBus
from paines.cpu.cpu import CPU6502


def run(apu: APU, cycles: int) -> None:
    # Small steps like the CPU does, so frame events and samples interleave as in a real run.
    for _ in range(cycles // 4):
        apu.tick(4)


def samples_of(apu: APU) -> list[int]:
    values = array.array("h")
    values.frombytes(apu.take_samples())
    return list(values)


def test_length_counter_loads_and_shows_in_status() -> None:
    apu = APU()
    apu.write(0x4015, 0x01)
    apu.write(0x4003, 0x08)  # length index 1
    assert apu.pulse1.length == LENGTH_TABLE[1]
    assert apu.read_status() & 0x01


def test_disabled_channel_ignores_length_loads_and_is_cleared() -> None:
    apu = APU()
    apu.write(0x4003, 0x08)
    assert apu.pulse1.length == 0

    apu.write(0x4015, 0x01)
    apu.write(0x4003, 0x08)
    apu.write(0x4015, 0x00)
    assert apu.pulse1.length == 0
    assert apu.read_status() & 0x01 == 0


def test_length_counter_counts_down_on_half_frames_and_halt_stops_it() -> None:
    apu = APU()
    apu.write(0x4015, 0x03)
    apu.write(0x4000, 0x30)  # pulse 1: halt + constant volume
    apu.write(0x4003, 0x18)  # length 2
    apu.write(0x4007, 0x18)  # pulse 2: not halted, length 2
    run(apu, 14913 + 8)  # first half frame
    assert apu.pulse2.length == 1
    assert apu.pulse1.length == 2


def test_frame_irq_is_raised_cleared_by_status_read_and_can_be_inhibited() -> None:
    apu = APU()
    run(apu, 29830 + 8)
    assert apu.irq_pending
    assert apu.read_status() & 0x40
    assert not apu.irq_pending

    run(apu, 29830 * 2)
    assert apu.irq_pending
    apu.write(0x4017, 0x40)
    assert not apu.irq_pending
    run(apu, 29830 * 2)
    assert not apu.irq_pending


def test_five_step_mode_has_no_irq_and_clocks_immediately() -> None:
    apu = APU()
    apu.write(0x4015, 0x02)
    apu.write(0x4007, 0x08)
    apu.write(0x4017, 0x80)
    assert apu.pulse2.length == LENGTH_TABLE[1] - 1  # half frame clock on write
    run(apu, 37282 * 2)
    assert not apu.irq_pending


def test_pulse_outputs_duty_pattern_at_the_programmed_frequency() -> None:
    apu = APU()
    apu.output_enabled = True
    apu.write(0x4015, 0x01)
    apu.write(0x4000, 0xBF)  # 50% duty, halt, constant volume 15
    apu.write(0x4002, 0xFD)
    apu.write(0x4003, 0x08)  # period 253 -> ~440 Hz
    run(apu, CPU_CLOCK_HZ // 10)
    samples = samples_of(apu)

    assert max(samples) > 2000 and min(samples) < -2000
    crossings = sum(1 for a, b in zip(samples, samples[1:]) if a < 0 <= b)
    frequency = crossings * 10
    assert 400 < frequency < 480


def test_channel_register_writes_first_account_for_elapsed_cycles() -> None:
    apu = APU()
    apu._threshold = 1000  # keep the cycles pending, as happens between CPU instructions
    apu.tick(10)
    assert apu._pending == 10
    apu.write(0x4002, 0x20)
    assert apu._pending == 0
    assert apu._frame_cycle == 10


def test_pulse_is_muted_for_tiny_periods() -> None:
    apu = APU()
    apu.write(0x4015, 0x01)
    apu.write(0x4000, 0xBF)
    apu.write(0x4002, 0x04)
    apu.write(0x4003, 0x08)
    assert apu.pulse1.output() == 0


def test_sweep_changes_the_pulse_period() -> None:
    apu = APU()
    apu.write(0x4015, 0x01)
    apu.write(0x4000, 0x3F)
    apu.write(0x4001, 0x81)  # enabled, period 0, add, shift 1
    apu.write(0x4002, 0x00)
    apu.write(0x4003, 0x09)  # period 0x100
    run(apu, 14913 + 8)
    assert apu.pulse1.timer_period > 0x100


def test_envelope_decays_when_not_constant() -> None:
    apu = APU()
    apu.write(0x4015, 0x01)
    apu.write(0x4000, 0x00)  # decay, period 0, no loop
    apu.write(0x4003, 0x08)
    run(apu, 7457 * 4)
    assert apu.pulse1.envelope.volume < 15


def test_triangle_needs_linear_and_length_counters_to_play() -> None:
    apu = APU()
    apu.write(0x4015, 0x04)
    apu.write(0x4008, 0x81)  # control, linear reload 1
    apu.write(0x400A, 0x10)
    apu.write(0x400B, 0x08)
    step = apu.triangle.step
    apu.triangle.advance(1000)
    assert apu.triangle.step == step  # linear counter not loaded yet

    run(apu, 7457 + 8)
    apu.triangle.advance(1000)
    assert apu.triangle.step != step


def test_noise_lfsr_matches_the_reference_sequence() -> None:
    apu = APU()
    noise = apu.noise
    noise.timer = 0
    noise.timer_period = 4
    noise.advance(0)  # one step
    assert noise.shift == 0x4000  # bit0 ^ bit1 = 1 shifted into bit 14

    noise.mode = True
    noise.shift = 1
    noise.timer = 0
    noise.advance(0)
    assert noise.shift == 0x4000


def test_noise_output_follows_register_volume() -> None:
    apu = APU()
    apu.write(0x4015, 0x08)
    apu.write(0x400C, 0x3A)  # halt, constant volume 10
    apu.write(0x400F, 0x08)
    apu.noise.shift = 2  # bit 0 clear
    assert apu.noise.output() == 10
    apu.noise.shift = 3
    assert apu.noise.output() == 0


class FakeMemory:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.reads: list[int] = []

    def __call__(self, address: int) -> int:
        self.reads.append(address)
        return self.data[(address - 0xC000) % len(self.data)]


def test_dmc_reads_samples_from_memory_and_moves_the_output_level() -> None:
    memory = FakeMemory(b"\xff\xff")
    apu = APU(read_memory=memory)
    apu.write(0x4010, 0x0F)  # fastest rate
    apu.write(0x4011, 0x00)
    apu.write(0x4012, 0x00)  # $C000
    apu.write(0x4013, 0x01)  # 17 bytes
    apu.write(0x4015, 0x10)
    assert memory.reads[0] == 0xC000
    assert apu.read_status() & 0x10

    run(apu, 54 * 8 * 4)
    assert apu.dmc.output_level > 0
    assert 0xC001 in memory.reads


def test_dmc_raises_irq_at_the_end_of_the_sample_and_status_write_clears_it() -> None:
    apu = APU(read_memory=FakeMemory(b"\x00"))
    apu.write(0x4010, 0x8F)  # IRQ enabled, no loop
    apu.write(0x4013, 0x00)  # a single byte
    apu.write(0x4015, 0x10)
    assert apu.irq_pending
    assert apu.read_status() & 0x80
    apu.write(0x4015, 0x00)
    assert not apu.irq_pending


def test_dmc_direct_load_sets_the_output_level() -> None:
    apu = APU()
    apu.write(0x4011, 0xFF)
    assert apu.dmc.output_level == 0x7F


def test_sample_count_matches_the_output_rate() -> None:
    apu = APU()
    apu.output_enabled = True
    run(apu, CPU_CLOCK_HZ)
    assert abs(len(samples_of(apu)) - SAMPLE_RATE) <= 2


def test_samples_are_not_collected_when_output_is_disabled() -> None:
    apu = APU()
    run(apu, CPU_CLOCK_HZ // 10)
    assert samples_of(apu) == []


def test_idle_apu_settles_to_silence_after_the_filter_removes_the_dc_offset() -> None:
    apu = APU()
    apu.output_enabled = True
    run(apu, CPU_CLOCK_HZ)
    samples = samples_of(apu)
    assert max(abs(value) for value in samples[SAMPLE_RATE // 2 :]) <= 1


def test_bus_routes_apu_registers_and_keeps_controller_2_reads() -> None:
    bus = CPUBus()
    bus.write(0x4015, 0x01)
    bus.write(0x4003, 0x08)
    assert bus.apu.pulse1.length == LENGTH_TABLE[1]
    assert bus.read(0x4015) & 0x01

    bus.controller_buttons[1] = 0x01
    bus.write(0x4017, 0x40)  # goes to the APU, not the controller
    assert bus.apu.irq_inhibit
    bus.write(0x4016, 1)
    bus.write(0x4016, 0)
    assert bus.read(0x4017) & 1 == 1


def test_cpu_takes_the_frame_irq_only_when_interrupts_are_enabled(tmp_path) -> None:
    bus = CPUBus()
    bus.cartridge.prg = bytearray(0x8000)
    bus.cartridge.prg_offsets = [0, 0x2000, 0x4000, 0x6000]
    bus.cartridge.prg[0x7FFE:0x8000] = b"\x00\x90"
    bus.cartridge.prg[0:1] = b"\xea"  # NOP
    cpu = CPU6502(bus=bus, file_name=str(tmp_path / "cpu.log"))
    cpu.pc = 0x8000
    cpu.p_irq = 1
    bus.apu.frame_irq = True
    cpu.execute()
    assert cpu.pc == 0x8001

    cpu.p_irq = 0
    cpu.execute()
    assert cpu.pc == 0x9000
