import time

from paines.apu.apu import SAMPLE_RATE
from paines.cpu.cpu import CPU6502
from paines.ppu.frame import NES_PALETTE
from paines.ppu.ppu import FRAME_HEIGHT, FRAME_WIDTH

FRAME_SECONDS = 1 / 60
MAX_QUEUED_CHUNKS = 6

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


def _start_audio(pygame, cpu: CPU6502):
    try:
        pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=1024)
    except pygame.error:
        return None, []
    cpu.bus.apu.output_enabled = True
    return pygame.mixer.Channel(0), []


def _queue_audio(pygame, cpu: CPU6502, channel, backlog: list) -> None:
    if channel is None:
        return
    data = cpu.bus.apu.take_samples()
    if data:
        backlog.append(pygame.mixer.Sound(buffer=data))
    # Dropping the oldest chunks keeps latency bounded when audio and video drift apart.
    del backlog[:-MAX_QUEUED_CHUNKS]
    if backlog and not channel.get_busy():
        channel.play(backlog.pop(0))
    while backlog and channel.get_queue() is None:
        channel.queue(backlog.pop(0))


def play(cpu: CPU6502, scale: int = 3, show_fps: bool = True) -> None:
    import pygame

    pygame.init()
    window = pygame.display.set_mode((FRAME_WIDTH * scale, FRAME_HEIGHT * scale))
    pygame.display.set_caption("paines")
    palette = [tuple(color) for color in NES_PALETTE]
    key_map = _buttons()
    held = ""
    channel, backlog = _start_audio(pygame, cpu)
    frames = 0
    fps_start = time.perf_counter()
    next_frame = fps_start
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
            _queue_audio(pygame, cpu, channel, backlog)
            surface = pygame.image.frombuffer(bytes(frame), (FRAME_WIDTH, FRAME_HEIGHT), "P")
            surface.set_palette(palette)
            pygame.transform.scale(surface.convert(window), window.get_size(), window)
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
        pygame.quit()
