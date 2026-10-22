from paines.ppu.mmio import PPUMMIO
from paines.bus.bus import CPUBus
from paines.cpu.cpu import CPU6502
from paines.ppu.ppu import (
    PPU,
    PPU_DOTS_PER_FRAME,
    PPU_DOTS_PER_SCANLINE,
    VBLANK_END,
    VBLANK_START,
)


def test_ppu_advances_three_dots_per_cpu_cycle() -> None:
    ppu = PPU()

    ppu.advance_cpu_cycles(4)

    assert (ppu.scanline, ppu.dot) == (261, 12)


def test_vblank_starts_and_raises_nmi_when_enabled() -> None:
    ppu = PPU()
    ppu.v_blank_enabled = 1
    dots_until_vblank = (
        VBLANK_START - (ppu.scanline * PPU_DOTS_PER_SCANLINE + ppu.dot)
    ) % PPU_DOTS_PER_FRAME

    ppu.advance_dots(dots_until_vblank)

    assert ppu.v_blank_status == 1
    assert ppu.nmi_pending
    assert (ppu.scanline, ppu.dot) == (241, 1)


def test_vblank_ends_at_pre_render_scanline() -> None:
    ppu = PPU()
    ppu.v_blank_status = 1
    ppu._update_nmi_line()
    dots_until_end = (
        VBLANK_END - (ppu.scanline * PPU_DOTS_PER_SCANLINE + ppu.dot)
    ) % PPU_DOTS_PER_FRAME

    ppu.advance_dots(dots_until_end)

    assert ppu.v_blank_status == 0
    assert (ppu.scanline, ppu.dot) == (261, 1)


def test_enabling_nmi_during_vblank_raises_nmi() -> None:
    ppu = PPU()
    ppu.v_blank_status = 1

    PPUMMIO(ppu).write(0x2000, 0x80)

    assert ppu.nmi_pending


def test_status_read_clears_vblank_but_does_not_cancel_pending_nmi() -> None:
    ppu = PPU()
    ppu.v_blank_enabled = 1
    ppu.v_blank_status = 1
    ppu._update_nmi_line()
    mmio = PPUMMIO(ppu)

    status = mmio.read(0x2002)

    assert status & 0x80
    assert ppu.v_blank_status == 0
    assert ppu.nmi_pending


def test_cpu_services_pending_ppu_nmi_and_advances_timing(tmp_path) -> None:
    bus = CPUBus()
    bus.cartridge.prg = bytearray(0x8000)
    bus.cartridge.prg_mask = 0x7FFF
    bus.cartridge.prg[0x7FFA] = 0x78
    bus.cartridge.prg[0x7FFB] = 0x56
    ppu = bus.ppu_mmio.ppu
    ppu.nmi_pending = True
    cpu = CPU6502(bus=bus, file_name=str(tmp_path / "cpu.log"))

    cycles = cpu.execute()

    assert cycles == 7
    assert cpu.total_cycle == 7
    assert cpu.pc == 0x5678
    assert (ppu.scanline, ppu.dot) == (261, 21)


def test_frame_boundary_renders_and_exposes_a_frame() -> None:
    ppu = PPU()
    ppu.write_vram(0x3F00, 0x2A)
    dots_until_frame = (
        VBLANK_START - (ppu.scanline * PPU_DOTS_PER_SCANLINE + ppu.dot)
    ) % PPU_DOTS_PER_FRAME

    ppu.advance_dots(dots_until_frame)

    frame = ppu.take_frame()
    assert frame is not None
    assert frame[0] == 0x2A
    assert frame[-1] == 0x2A
    assert (ppu.scanline, ppu.dot) == (241, 1)
    assert ppu.take_frame() is None


def test_cpu_run_frame_advances_until_frame_is_ready(tmp_path) -> None:
    bus = CPUBus()
    bus.cartridge.prg = bytearray(0x8000)
    bus.cartridge.prg_mask = 0x7FFF
    bus.cartridge.prg[0:3] = b"\x4c\x00\x80"
    cpu = CPU6502(bus=bus, file_name=str(tmp_path / "cpu.log"))
    cpu.pc = 0x8000

    frame = cpu.run_frame()

    assert len(frame) == 256 * 240
    assert cpu.total_cycle > 0
    assert not bus.ppu_mmio.ppu.frame_ready
