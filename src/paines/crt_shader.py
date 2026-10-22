"""GPU CRT filter: barrel curvature, bloom, scanlines, phosphor mask and vignette.

The frame is uploaded as 8-bit palette indices; the palette lookup happens in the fragment shader,
so each frame uploads 60 KB instead of an RGB image.
"""

from array import array

from paines.ppu.frame import NES_PALETTE
from paines.ppu.ppu import FRAME_HEIGHT, FRAME_WIDTH

VERTEX = """
#version 330
in vec2 position;
out vec2 uv;
void main() {
    uv = position * 0.5 + 0.5;
    gl_Position = vec4(position, 0.0, 1.0);
}
"""

FRAGMENT = """
#version 330
uniform sampler2D frame;    // R8: palette index / 255
uniform sampler2D palette;  // 64x1 RGB
uniform vec2 source_size;
uniform float curvature;
uniform float bloom;
uniform float scanline_depth;
uniform float mask_floor;
uniform float vignette;
uniform float chroma_blur;   // chroma smear width in source pixels (0 = RGB)
uniform float crawl;         // dot-crawl / colour fringing strength
uniform float ghost;         // delayed echo of the signal
uniform float noise;         // RF snow
uniform float jitter;        // horizontal line wobble in source pixels
uniform float time;          // frame counter
in vec2 uv;
out vec4 color;

vec3 texel(vec2 p) {
    vec2 clamped = clamp(p, vec2(0.0), vec2(1.0));
    float index = floor(texture(frame, vec2(clamped.x, 1.0 - clamped.y)).r * 255.0 + 0.5);
    return texture(palette, vec2((index + 0.5) / 64.0, 0.5)).rgb;
}

const mat3 TO_YIQ = mat3(0.299, 0.596, 0.211, 0.587, -0.274, -0.523, 0.114, -0.322, 0.312);
const mat3 FROM_YIQ = mat3(1.0, 1.0, 1.0, 0.956, -0.272, -1.106, 0.621, -0.647, 1.703);

float hash(vec2 v) {
    return fract(sin(dot(v, vec2(12.9898, 78.233))) * 43758.5453);
}

// Approximates a composite/RF signal: sharp luma, smeared chroma, dot crawl and an echo.
vec3 signal(vec2 p) {
    vec3 yiq = TO_YIQ * texel(p);
    if (chroma_blur <= 0.0) {
        return FROM_YIQ * yiq;
    }
    vec2 dx = vec2(chroma_blur / source_size.x, 0.0);
    vec2 iq = vec2(0.0);
    float total = 0.0;
    for (int i = -3; i <= 3; i++) {
        float w = exp(-float(i * i) / 4.0);
        iq += (TO_YIQ * texel(p + dx * float(i))).yz * w;
        total += w;
    }
    iq /= total;
    float y = yiq.x;
    vec2 px = floor(p * source_size);
    y += crawl * length(iq) * sin(2.0944 * (px.x + 2.0 * px.y + time));
    y += ghost * (TO_YIQ * texel(p - vec2(4.0 / source_size.x, 0.0))).x;
    return FROM_YIQ * vec3(y, iq);
}

void main() {
    // Barrel distortion around the screen centre.
    vec2 centred = uv * 2.0 - 1.0;
    centred *= 1.0 + curvature * dot(centred.yx, centred.yx);
    vec2 p = centred * 0.5 + 0.5;
    if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0) {
        color = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    p.x += jitter * (hash(vec2(floor(p.y * source_size.y), time)) - 0.5) / source_size.x;
    vec3 base = signal(p);

    // Bloom: wide gaussian-ish blur of the picture, added back on top.
    vec2 step = 1.0 / source_size;
    vec3 glow = vec3(0.0);
    float total = 0.0;
    for (int y = -2; y <= 2; y++) {
        for (int x = -3; x <= 3; x++) {
            float w = exp(-(float(x * x) / 4.5 + float(y * y) / 2.0));
            glow += texel(p + vec2(x, y) * step) * w;
            total += w;
        }
    }
    glow /= total;
    vec3 rgb = base + bloom * glow * glow * 2.0;

    // Scanlines: darkest on the seam between source rows.
    float row = fract(p.y * source_size.y);
    rgb *= 1.0 - scanline_depth * pow(abs(row - 0.5) * 2.0, 2.0);

    // Phosphor mask: one subpixel per screen column.
    int column = int(gl_FragCoord.x) % 3;
    vec3 tint = vec3(mask_floor);
    tint[column] = 1.0;
    rgb *= tint;

    rgb += noise * (hash(gl_FragCoord.xy + time) - 0.5);

    // Vignette.
    rgb *= 1.0 - vignette * pow(min(1.0, dot(centred, centred) / 2.0), 1.5);

    color = vec4(rgb, 1.0);
}
"""


SIGNALS = {
    "rgb": dict(chroma_blur=0.0, crawl=0.0, ghost=0.0, noise=0.0, jitter=0.0),
    "composite": dict(chroma_blur=1.5, crawl=0.12, ghost=0.0, noise=0.0, jitter=0.0),
    "rf": dict(chroma_blur=2.5, crawl=0.2, ghost=0.15, noise=0.12, jitter=0.35),
}


class CRTShader:
    def __init__(self, ctx, window_size: tuple[int, int], signal: str = "rgb") -> None:
        self.ctx = ctx
        self.window_size = window_size
        self.program = ctx.program(vertex_shader=VERTEX, fragment_shader=FRAGMENT)
        quad = array("f", [-1, -1, 1, -1, -1, 1, 1, 1])
        self.vao = ctx.vertex_array(self.program, [(ctx.buffer(quad.tobytes()), "2f", "position")])

        self.frame = ctx.texture((FRAME_WIDTH, FRAME_HEIGHT), 1, dtype="f1")
        self.frame.filter = (ctx.NEAREST, ctx.NEAREST)
        rgb = bytes(channel for color in NES_PALETTE for channel in color[:3])
        self.palette = ctx.texture((64, 1), 3, rgb)
        self.palette.filter = (ctx.NEAREST, ctx.NEAREST)

        self.program["frame"] = 0
        self.program["palette"] = 1
        self.program["source_size"] = (FRAME_WIDTH, FRAME_HEIGHT)
        self.program["curvature"] = 0.025
        for name, value in SIGNALS[signal].items():
            self.program[name] = value
        self.ticks = 0
        self.program["bloom"] = 0.35
        self.program["scanline_depth"] = 0.45
        self.program["mask_floor"] = 0.8
        self.program["vignette"] = 0.35

    def draw(self, frame: bytes) -> None:
        self.ticks += 1
        self.program["time"] = float(self.ticks % 1024)
        self.ctx.screen.use()
        self.ctx.viewport = (0, 0, *self.ctx.screen.size)
        self.frame.write(frame)
        self.frame.use(0)
        self.palette.use(1)
        self.vao.render(self.ctx.TRIANGLE_STRIP)
