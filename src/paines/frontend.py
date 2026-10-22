import threading
import time
from array import array

from paines.apu.apu import SAMPLE_RATE
from paines.cpu.cpu import CPU6502
from paines.ppu.frame import NES_PALETTE
from paines.ppu.ppu import FRAME_HEIGHT, FRAME_WIDTH

FRAME_SECONDS = 1 / 60
AUDIO_CHUNK_SAMPLES = 512
TARGET_BUFFER_SAMPLES = 2048
MAX_BUFFER_SAMPLES = 8192
BUFFER_CORRECTION = 0.02
CRT_SCANLINE_DEPTH = 0.45
CRT_MASK_FLOOR = 200
CRT_VIGNETTE = 0.35

# Bit order matches the controller shift register: A, B, Select, Start, Up, Down, Left, Right
def _buttons():
    import pygame

    return (
        ("A", pygame.K_x, 0x01),
        ("B", pygame.K_z, 0x02),
        ("Select", pygame.K_RSHIFT, 0x04),
        ("Select", pygame.K_TAB, 0x04),
        ("Start", pygame.K_RETURN, 0x08),
        ("Up", pygame.K_UP, 0x10),
        ("Down", pygame.K_DOWN, 0x20),
        ("Left", pygame.K_LEFT, 0x40),
        ("Right", pygame.K_RIGHT, 0x80),
    )


def resample(data: bytes, length: int) -> bytes:
    """Linearly stretches or shrinks 16-bit mono samples to `length` samples."""
    source = array("h")
    source.frombytes(data)
    count = len(source)
    if count == length or count < 2 or length < 1:
        return data
    last = count - 1
    step = last / max(length - 1, 1)
    out = array("h", bytes(2 * length))
    for i in range(length):
        position = i * step
        index = int(position)
        if index >= last:
            out[i] = source[last]
        else:
            fraction = position - index
            out[i] = int(source[index] + (source[index + 1] - source[index]) * fraction)
    return out.tobytes()


def audio_target_length(frame_period: float, buffered_samples: int) -> int:
    """Samples to emit for one frame so audio is produced as fast as it is played.

    The emulator may run slower than 60 FPS; emitting exactly the wall-clock period's
    worth of samples (slightly slowing the sound) avoids buffer underruns, and a small
    correction keeps the buffer near its desired fill.
    """
    error = (TARGET_BUFFER_SAMPLES - buffered_samples) / TARGET_BUFFER_SAMPLES
    correction = 1 + max(-1.0, min(1.0, error)) * BUFFER_CORRECTION
    return max(1, round(frame_period * SAMPLE_RATE * correction))


class AudioBuffer:
    """Thread-safe FIFO between the emulator (producer) and the audio callback (consumer)."""

    def __init__(self) -> None:
        self._data = bytearray()
        self._lock = threading.Lock()
        self._playing = False
        self._last = b"\x00\x00"

    @property
    def samples(self) -> int:
        return len(self._data) // 2

    def push(self, data: bytes) -> None:
        with self._lock:
            self._data += data
            # Dropping the oldest audio keeps latency bounded when the consumer stalls.
            overflow = len(self._data) - 2 * MAX_BUFFER_SAMPLES
            if overflow > 0:
                del self._data[:overflow]
            if len(self._data) >= 2 * TARGET_BUFFER_SAMPLES:
                self._playing = True

    def pull(self, size: int) -> bytes:
        with self._lock:
            if not self._playing:
                return self._last * (size // 2)
            chunk = bytes(self._data[:size])
            del self._data[:size]
            if chunk:
                self._last = chunk[-2:]
            if len(chunk) < size:
                # Underrun: hold the last sample and wait for the cushion to refill.
                self._playing = False
                chunk += self._last * ((size - len(chunk)) // 2)
            return chunk


def _start_audio(pygame, cpu: CPU6502):
    try:
        pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1)
        from pygame._sdl2.audio import AUDIO_S16, AudioDevice

        buffer = AudioBuffer()

        def callback(device, view) -> None:
            view[:] = buffer.pull(len(view))

        device = AudioDevice(
            devicename=None,
            iscapture=False,
            frequency=SAMPLE_RATE,
            audioformat=AUDIO_S16,
            numchannels=1,
            chunksize=AUDIO_CHUNK_SAMPLES,
            allowed_changes=0,
            callback=callback,
        )
    except (pygame.error, ImportError):
        return None, None
    cpu.bus.apu.output_enabled = True
    device.pause(0)
    return device, buffer


def _queue_audio(cpu: CPU6502, buffer: AudioBuffer | None, frame_period: float) -> None:
    if buffer is None:
        return
    data = cpu.bus.apu.take_samples()
    if data:
        buffer.push(resample(data, audio_target_length(frame_period, buffer.samples)))


def build_crt_overlay(pygame, size: tuple[int, int], scale: int):
    """Multiply-blend layer with scanlines, an RGB phosphor mask and a soft vignette.

    It is built once; each frame costs a single BLEND_MULT blit.
    """
    width, height = size
    overlay = pygame.Surface(size)
    overlay.fill((255, 255, 255))
    for y in range(height):
        # Brightest at the middle of each source pixel row, darkest at the seam between rows.
        phase = ((y % scale) + 0.5) / scale
        level = 1 - CRT_SCANLINE_DEPTH * (2 * abs(phase - 0.5)) ** 2
        shade = int(255 * level)
        pygame.draw.line(overlay, (shade, shade, shade), (0, y), (width, y))

    mask = pygame.Surface(size)
    tints = ((255, CRT_MASK_FLOOR, CRT_MASK_FLOOR), (CRT_MASK_FLOOR, 255, CRT_MASK_FLOOR),
             (CRT_MASK_FLOOR, CRT_MASK_FLOOR, 255))  # fmt: skip
    for x in range(width):
        pygame.draw.line(mask, tints[x % 3], (x, 0), (x, height))
    overlay.blit(mask, (0, 0), special_flags=pygame.BLEND_MULT)

    vignette = pygame.Surface((64, 48))
    for y in range(48):
        for x in range(64):
            dx, dy = (x - 31.5) / 32, (y - 23.5) / 24
            level = 1 - CRT_VIGNETTE * min(1.0, (dx * dx + dy * dy) / 2) ** 1.5
            shade = int(255 * level)
            vignette.set_at((x, y), (shade, shade, shade))
    overlay.blit(pygame.transform.smoothscale(vignette, size), (0, 0), special_flags=pygame.BLEND_MULT)
    return overlay.convert()


def _open_shader_window(pygame, size: tuple[int, int], signal: str = "rgb"):
    """Open an OpenGL window and return a CRTShader, or None if moderngl/GL is unavailable."""
    try:
        import moderngl

        from paines.crt_shader import CRTShader

        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_FORWARD_COMPATIBLE_FLAG, 1)
        pygame.display.set_mode(size, pygame.OPENGL | pygame.DOUBLEBUF)
        return CRTShader(moderngl.create_context(), size, signal)
    except Exception as error:
        print(f"CRT shader unavailable ({error}); using the software overlay")
        return None


def play(cpu: CPU6502, scale: int = 3, show_fps: bool = True, crt: bool = False, signal: str = "rgb") -> None:
    import pygame

    pygame.init()
    size = (FRAME_WIDTH * scale, FRAME_HEIGHT * scale)
    shader = _open_shader_window(pygame, size, signal) if crt else None
    window = None if shader else pygame.display.set_mode(size)
    pygame.display.set_caption("paines")
    palette = [tuple(color) for color in NES_PALETTE]
    key_map = _buttons()
    held = ""
    audio_device, audio_buffer = _start_audio(pygame, cpu)
    overlay = build_crt_overlay(pygame, window.get_size(), scale) if crt and window else None
    frames = 0
    fps_start = time.perf_counter()
    next_frame = fps_start
    last_frame = fps_start
    frame_period = FRAME_SECONDS
    running = True
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
            pressed = pygame.key.get_pressed()
            buttons = 0
            names = []
            for name, key, bit in key_map:
                if pressed[key]:
                    buttons |= bit
                    names.append(name)
            held = " ".join(dict.fromkeys(names))
            cpu.bus.controller_buttons[0] = buttons

            frame = cpu.run_frame()
            frame_started = time.perf_counter()
            frame_period += (max(frame_started - last_frame, FRAME_SECONDS) - frame_period) * 0.1
            last_frame = frame_started
            _queue_audio(cpu, audio_buffer, frame_period)
            if shader is not None:
                shader.draw(bytes(frame))
            else:
                surface = pygame.image.frombuffer(bytes(frame), (FRAME_WIDTH, FRAME_HEIGHT), "P")
                surface.set_palette(palette)
                pygame.transform.scale(surface.convert(window), window.get_size(), window)
                if overlay is not None:
                    window.blit(overlay, (0, 0), special_flags=pygame.BLEND_MULT)
            pygame.display.flip()

            frames += 1
            now = time.perf_counter()
            if show_fps and now - fps_start >= 0.5:
                fps = frames / (now - fps_start)
                pygame.display.set_caption(f"paines - {fps:.1f} FPS [{held}]")
                frames = 0
                fps_start = now

            next_frame += FRAME_SECONDS
            delay = next_frame - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_frame = time.perf_counter()
    finally:
        if audio_device is not None:
            audio_device.close()
        pygame.quit()
