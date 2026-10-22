"""APU sound channels.

Channels are not stepped every CPU cycle (too slow in Python). Instead the APU
asks each one to `advance(cycles)` right before an output sample is taken, and
the timers are resolved arithmetically.
"""

from typing import Callable

# https://www.nesdev.org/wiki/APU_Length_Counter
LENGTH_TABLE = (
    10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14,
    12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30,
)  # fmt: skip

DUTY_SEQUENCES = (
    (0, 1, 0, 0, 0, 0, 0, 0),
    (0, 1, 1, 0, 0, 0, 0, 0),
    (0, 1, 1, 1, 1, 0, 0, 0),
    (1, 0, 0, 1, 1, 1, 1, 1),
)

NOISE_PERIODS = (4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068)

DMC_RATES = (428, 380, 340, 320, 286, 254, 226, 214, 190, 160, 142, 128, 106, 84, 72, 54)

TRIANGLE_SEQUENCE = tuple(range(15, -1, -1)) + tuple(range(16))


class Envelope:
    def __init__(self) -> None:
        self.start = False
        self.loop = False  # also the length counter halt flag
        self.constant = False
        self.period = 0  # volume when constant
        self.divider = 0
        self.decay = 0

    def clock(self) -> None:
        if self.start:
            self.start = False
            self.decay = 15
            self.divider = self.period
        elif self.divider == 0:
            self.divider = self.period
            if self.decay > 0:
                self.decay -= 1
            elif self.loop:
                self.decay = 15
        else:
            self.divider -= 1

    @property
    def volume(self) -> int:
        return self.period if self.constant else self.decay


class Pulse:
    def __init__(self, ones_complement_sweep: bool) -> None:
        self.ones_complement_sweep = ones_complement_sweep
        self.enabled = False
        self.envelope = Envelope()
        self.duty = 0
        self.step = 0
        self.timer_period = 0
        self.timer = 0
        self.length = 0
        self.sweep_enabled = False
        self.sweep_period = 0
        self.sweep_negate = False
        self.sweep_shift = 0
        self.sweep_divider = 0
        self.sweep_reload = False

    def write(self, register: int, value: int) -> None:
        if register == 0:
            self.duty = value >> 6
            self.envelope.loop = bool(value & 0x20)
            self.envelope.constant = bool(value & 0x10)
            self.envelope.period = value & 0x0F
        elif register == 1:
            self.sweep_enabled = bool(value & 0x80)
            self.sweep_period = (value >> 4) & 7
            self.sweep_negate = bool(value & 0x08)
            self.sweep_shift = value & 7
            self.sweep_reload = True
        elif register == 2:
            self.timer_period = (self.timer_period & 0x700) | value
        else:
            self.timer_period = (self.timer_period & 0xFF) | ((value & 7) << 8)
            if self.enabled:
                self.length = LENGTH_TABLE[value >> 3]
            self.step = 0
            self.envelope.start = True

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self.length = 0

    def _sweep_target(self) -> int:
        change = self.timer_period >> self.sweep_shift
        if self.sweep_negate:
            return self.timer_period - change - (1 if self.ones_complement_sweep else 0)
        return self.timer_period + change

    def _muted(self) -> bool:
        return self.timer_period < 8 or self._sweep_target() > 0x7FF

    def clock_length_and_sweep(self) -> None:
        if not self.envelope.loop and self.length > 0:
            self.length -= 1
        if self.sweep_divider == 0 and self.sweep_enabled and self.sweep_shift and not self._muted():
            self.timer_period = self._sweep_target()
        if self.sweep_divider == 0 or self.sweep_reload:
            self.sweep_divider = self.sweep_period
            self.sweep_reload = False
        else:
            self.sweep_divider -= 1

    def advance(self, cycles: int) -> None:
        period = (self.timer_period + 1) * 2
        if cycles < self.timer:
            self.timer -= cycles
            return
        remaining = cycles - self.timer
        self.step = (self.step + 1 + remaining // period) & 7
        self.timer = period - remaining % period

    def output(self) -> int:
        if not self.enabled or self.length == 0 or self._muted():
            return 0
        if not DUTY_SEQUENCES[self.duty][self.step]:
            return 0
        return self.envelope.volume


class Triangle:
    def __init__(self) -> None:
        self.enabled = False
        self.control = False  # also the length counter halt flag
        self.linear_reload_value = 0
        self.linear = 0
        self.linear_reload = False
        self.timer_period = 0
        self.timer = 0
        self.length = 0
        self.step = 0

    def write(self, register: int, value: int) -> None:
        if register == 0:
            self.control = bool(value & 0x80)
            self.linear_reload_value = value & 0x7F
        elif register == 2:
            self.timer_period = (self.timer_period & 0x700) | value
        elif register == 3:
            self.timer_period = (self.timer_period & 0xFF) | ((value & 7) << 8)
            if self.enabled:
                self.length = LENGTH_TABLE[value >> 3]
            self.linear_reload = True

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self.length = 0

    def clock_linear(self) -> None:
        if self.linear_reload:
            self.linear = self.linear_reload_value
        elif self.linear > 0:
            self.linear -= 1
        if not self.control:
            self.linear_reload = False

    def clock_length(self) -> None:
        if not self.control and self.length > 0:
            self.length -= 1

    def advance(self, cycles: int) -> None:
        if self.length == 0 or self.linear == 0:
            return
        period = self.timer_period + 1
        if cycles < self.timer:
            self.timer -= cycles
            return
        remaining = cycles - self.timer
        self.step = (self.step + 1 + remaining // period) & 31
        self.timer = period - remaining % period

    def output(self) -> int:
        if self.timer_period < 2:  # ultrasonic: hold the middle of the wave
            return 7
        return TRIANGLE_SEQUENCE[self.step]


class Noise:
    def __init__(self) -> None:
        self.enabled = False
        self.envelope = Envelope()
        self.mode = False
        self.timer_period = NOISE_PERIODS[0]
        self.timer = 0
        self.length = 0
        self.shift = 1

    def write(self, register: int, value: int) -> None:
        if register == 0:
            self.envelope.loop = bool(value & 0x20)
            self.envelope.constant = bool(value & 0x10)
            self.envelope.period = value & 0x0F
        elif register == 2:
            self.mode = bool(value & 0x80)
            self.timer_period = NOISE_PERIODS[value & 0x0F]
        elif register == 3:
            if self.enabled:
                self.length = LENGTH_TABLE[value >> 3]
            self.envelope.start = True

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if not enabled:
            self.length = 0

    def clock_length(self) -> None:
        if not self.envelope.loop and self.length > 0:
            self.length -= 1

    def advance(self, cycles: int) -> None:
        if cycles < self.timer:
            self.timer -= cycles
            return
        remaining = cycles - self.timer
        steps = 1 + remaining // self.timer_period
        self.timer = self.timer_period - remaining % self.timer_period
        tap = 6 if self.mode else 1
        shift = self.shift
        for _ in range(steps):
            feedback = (shift ^ (shift >> tap)) & 1
            shift = (shift >> 1) | (feedback << 14)
        self.shift = shift

    def output(self) -> int:
        if not self.enabled or self.length == 0 or self.shift & 1:
            return 0
        return self.envelope.volume


class DMC:
    def __init__(self, read_memory: Callable[[int], int]) -> None:
        self.read_memory = read_memory
        self.irq_enabled = False
        self.loop = False
        self.timer_period = DMC_RATES[0]
        self.timer = DMC_RATES[0]
        self.output_level = 0
        self.sample_address = 0xC000
        self.sample_length = 1
        self.address = 0xC000
        self.bytes_remaining = 0
        self.buffer: int | None = None
        self.shift = 0
        self.bits_remaining = 8
        self.silence = True
        self.irq_pending = False

    def write(self, register: int, value: int) -> None:
        if register == 0:
            self.irq_enabled = bool(value & 0x80)
            self.loop = bool(value & 0x40)
            self.timer_period = DMC_RATES[value & 0x0F]
            if not self.irq_enabled:
                self.irq_pending = False
        elif register == 1:
            self.output_level = value & 0x7F
        elif register == 2:
            self.sample_address = 0xC000 | (value << 6)
        else:
            self.sample_length = (value << 4) | 1

    def set_enabled(self, enabled: bool) -> None:
        self.irq_pending = False
        if not enabled:
            self.bytes_remaining = 0
        elif self.bytes_remaining == 0:
            self._restart()
            self._fill_buffer()

    def _restart(self) -> None:
        self.address = self.sample_address
        self.bytes_remaining = self.sample_length

    def _fill_buffer(self) -> None:
        if self.buffer is not None or self.bytes_remaining == 0:
            return
        self.buffer = self.read_memory(self.address)
        self.address = 0x8000 | ((self.address + 1) & 0x7FFF)
        self.bytes_remaining -= 1
        if self.bytes_remaining == 0:
            if self.loop:
                self._restart()
            elif self.irq_enabled:
                self.irq_pending = True

    def advance(self, cycles: int) -> None:
        if cycles < self.timer:
            self.timer -= cycles
            return
        remaining = cycles - self.timer
        steps = 1 + remaining // self.timer_period
        self.timer = self.timer_period - remaining % self.timer_period
        for _ in range(steps):
            self._clock_output()

    def _clock_output(self) -> None:
        if not self.silence:
            if self.shift & 1:
                if self.output_level <= 125:
                    self.output_level += 2
            elif self.output_level >= 2:
                self.output_level -= 2
            self.shift >>= 1
        self.bits_remaining -= 1
        if self.bits_remaining == 0:
            self.bits_remaining = 8
            if self.buffer is None:
                self.silence = True
            else:
                self.silence = False
                self.shift = self.buffer
                self.buffer = None
                self._fill_buffer()

    def output(self) -> int:
        return self.output_level
