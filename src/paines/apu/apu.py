from array import array
from typing import Callable

from paines.apu.channels import DMC, Noise, Pulse, Triangle

CPU_CLOCK_HZ = 1_789_773
SAMPLE_RATE = 44100

# https://www.nesdev.org/wiki/APU_Mixer
PULSE_MIX = [0.0] + [95.52 / (8128.0 / n + 100) for n in range(1, 31)]
TND_MIX = [0.0] + [163.67 / (24329.0 / n + 100) for n in range(1, 203)]

# (cpu cycle, action) where action bits: 1 = quarter frame, 2 = half frame, 4 = IRQ.
# The last entry only marks where the sequence wraps.
FOUR_STEP = ((7457, 1), (14913, 3), (22371, 1), (29828, 4), (29829, 7), (29830, 4))
FIVE_STEP = ((7457, 1), (14913, 3), (22371, 1), (29829, 0), (37281, 3), (37282, 0))


class APU:
    def __init__(self, read_memory: Callable[[int], int] = lambda address: 0) -> None:
        self.pulse1 = Pulse(ones_complement_sweep=True)
        self.pulse2 = Pulse(ones_complement_sweep=False)
        self.triangle = Triangle()
        self.noise = Noise()
        self.dmc = DMC(read_memory)

        self.frame_irq = False
        self.irq_inhibit = False
        self.five_step = False
        self._events = FOUR_STEP
        self._event_index = 0
        self._frame_cycle = 0

        self.output_enabled = False
        self.samples = array("h")
        self.sample_period = CPU_CLOCK_HZ / SAMPLE_RATE
        self._sample_acc = 0.0
        self._since_sync = 0
        self._pending = 0
        self._threshold = 1
        self._filter_in = 0.0
        self._filter_out = 0.0

    @property
    def irq_pending(self) -> bool:
        return self.frame_irq or self.dmc.irq_pending

    def read_status(self) -> int:
        self._process()
        status = (
            (self.pulse1.length > 0)
            | ((self.pulse2.length > 0) << 1)
            | ((self.triangle.length > 0) << 2)
            | ((self.noise.length > 0) << 3)
            | ((self.dmc.bytes_remaining > 0) << 4)
            | (self.frame_irq << 6)
            | (self.dmc.irq_pending << 7)
        )
        self.frame_irq = False
        return status

    def write(self, address: int, value: int) -> None:
        # Elapsed cycles must be resolved with the old register values before they change.
        if self._pending:
            self._process()
        if address <= 0x4013:
            register = address & 3
            if address < 0x4004:
                self.pulse1.write(register, value)
            elif address < 0x4008:
                self.pulse2.write(register, value)
            elif address < 0x400C:
                self.triangle.write(register, value)
            elif address < 0x4010:
                self.noise.write(register, value)
            else:
                self.dmc.write(register, value)
        elif address == 0x4015:
            self.pulse1.set_enabled(bool(value & 1))
            self.pulse2.set_enabled(bool(value & 2))
            self.triangle.set_enabled(bool(value & 4))
            self.noise.set_enabled(bool(value & 8))
            self.dmc.set_enabled(bool(value & 16))
        elif address == 0x4017:
            self.five_step = bool(value & 0x80)
            self.irq_inhibit = bool(value & 0x40)
            if self.irq_inhibit:
                self.frame_irq = False
            self._events = FIVE_STEP if self.five_step else FOUR_STEP
            self._event_index = 0
            self._frame_cycle = 0
            if self.five_step:
                self._clock_frame(3)
            self._threshold = 1

    def _clock_frame(self, action: int) -> None:
        if action & 1:
            self.pulse1.envelope.clock()
            self.pulse2.envelope.clock()
            self.noise.envelope.clock()
            self.triangle.clock_linear()
        if action & 2:
            self.pulse1.clock_length_and_sweep()
            self.pulse2.clock_length_and_sweep()
            self.triangle.clock_length()
            self.noise.clock_length()
        if action & 4 and not self.irq_inhibit:
            self.frame_irq = True

    def tick(self, cycles: int) -> None:
        self._pending += cycles
        if self._pending >= self._threshold:
            self._process()

    def _process(self) -> None:
        elapsed = self._pending
        self._pending = 0
        self._frame_cycle += elapsed
        events = self._events
        while self._frame_cycle >= events[self._event_index][0]:
            cycle, action = events[self._event_index]
            if action:
                self._clock_frame(action)
            self._event_index += 1
            if self._event_index == len(events):
                self._event_index = 0
                self._frame_cycle -= cycle

        self._since_sync += elapsed
        self._sample_acc += elapsed
        if self._sample_acc >= self.sample_period:
            self._sync()
        self._threshold = max(
            1,
            min(
                int(self.sample_period - self._sample_acc) + 1,
                events[self._event_index][0] - self._frame_cycle,
            ),
        )

    def _sync(self) -> None:
        elapsed = self._since_sync
        self._since_sync = 0
        # A silent channel's phase is unobservable, so only running ones are advanced.
        if self.pulse1.length:
            self.pulse1.advance(elapsed)
        if self.pulse2.length:
            self.pulse2.advance(elapsed)
        if self.triangle.length:
            self.triangle.advance(elapsed)
        if self.noise.length:
            self.noise.advance(elapsed)
        dmc = self.dmc
        if dmc.bytes_remaining or not dmc.silence or dmc.buffer is not None:
            dmc.advance(elapsed)

        count = int(self._sample_acc // self.sample_period)
        self._sample_acc -= count * self.sample_period
        if not self.output_enabled:
            return

        mixed = (
            PULSE_MIX[self.pulse1.output() + self.pulse2.output()]
            + TND_MIX[
                3 * self.triangle.output() + 2 * self.noise.output() + self.dmc.output()
            ]
        )
        # High-pass filter removes the DC offset like the console's output stage.
        filtered = mixed - self._filter_in + 0.996 * self._filter_out
        self._filter_in = mixed
        self._filter_out = filtered
        value = max(-32768, min(32767, int(filtered * 32767)))
        if count == 1:
            self.samples.append(value)
        else:
            self.samples.extend(array("h", [value]) * count)

    def take_samples(self) -> bytes:
        data = self.samples.tobytes()
        del self.samples[:]
        return data


def apu_builder(read_memory: Callable[[int], int] = lambda address: 0) -> APU:
    return APU(read_memory)
