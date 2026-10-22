import time

from paines.cpu.cpu import CPU6502
from paines.ppu.frame import NES_PALETTE
from paines.ppu.ppu import FRAME_HEIGHT, FRAME_WIDTH

FRAME_SECONDS = 1 / 60

# Bit order matches the controller shift register: A, B, Select, Start, Up, Down, Left, Right
KEY_BITS = {
    "x": 0x01,
    "z": 0x02,
    "right shift": 0x04,
    "return": 0x08,
    "up": 0x10,
    "down": 0x20,
    "left": 0x40,
    "right": 0x80,
}


def play(cpu: CPU6502, scale: int = 3, show_fps: bool = True) -> None:
    import pygame

    pygame.init()
    window = pygame.display.set_mode((FRAME_WIDTH * scale, FRAME_HEIGHT * scale))
    pygame.display.set_caption("paines")
    palette = [tuple(color) for color in NES_PALETTE]
    buttons = 0
    frames = 0
    fps_start = time.perf_counter()
    next_frame = fps_start
    running = True
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type in (pygame.KEYDOWN, pygame.KEYUP):
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        continue
                    bit = KEY_BITS.get(pygame.key.name(event.key))
                    if bit is not None:
                        buttons = buttons | bit if event.type == pygame.KEYDOWN else buttons & ~bit
            cpu.bus.controller_buttons[0] = buttons

            frame = cpu.run_frame()
            surface = pygame.image.frombuffer(bytes(frame), (FRAME_WIDTH, FRAME_HEIGHT), "P")
            surface.set_palette(palette)
            pygame.transform.scale(surface.convert(window), window.get_size(), window)
            pygame.display.flip()

            frames += 1
            now = time.perf_counter()
            if show_fps and now - fps_start >= 1:
                pygame.display.set_caption(f"paines - {frames / (now - fps_start):.1f} FPS")
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
