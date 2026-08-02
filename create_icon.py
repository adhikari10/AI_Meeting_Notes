"""
create_icon.py — Generate icon.ico for Meeting Notes AI
Design: microphone inside a purple gradient circle with a sparkle accent.

Run once before building:
    pip install Pillow
    python create_icon.py
"""

import math
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Pillow is required: pip install Pillow")


def lerp_color(c1, c2, t):
    """Linear interpolate between two RGB tuples."""
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def draw_rounded_rect(draw, xy, radius, fill):
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + 2 * radius, y0 + 2 * radius], fill=fill)
    draw.ellipse([x1 - 2 * radius, y0, x1, y0 + 2 * radius], fill=fill)
    draw.ellipse([x0, y1 - 2 * radius, x0 + 2 * radius, y1], fill=fill)
    draw.ellipse([x1 - 2 * radius, y1 - 2 * radius, x1, y1], fill=fill)


def make_icon(size: int) -> Image.Image:
    img  = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s    = size

    # ── Purple gradient background (simulate via horizontal bands) ──────────
    top_color = (100, 30, 210)
    bot_color = (168, 60, 230)
    radius    = int(s * 0.22)

    # Fill rounded rect row by row for gradient effect
    for y in range(s):
        t     = y / s
        color = lerp_color(top_color, bot_color, t) + (255,)
        draw.line([(0, y), (s - 1, y)], fill=color)

    # Clip to rounded rect shape using a mask
    mask = Image.new('L', (s, s), 0)
    mask_draw = ImageDraw.Draw(mask)
    draw_rounded_rect(mask_draw, [0, 0, s - 1, s - 1], radius, 255)
    img.putalpha(mask)

    draw = ImageDraw.Draw(img)

    # ── Microphone body ────────────────────────────────────────────────────
    mic_w  = int(s * 0.22)
    mic_h  = int(s * 0.34)
    mic_x  = (s - mic_w) // 2
    mic_y  = int(s * 0.16)
    mic_r  = mic_w // 2
    white  = (255, 255, 255, 255)

    # Rounded rectangle (microphone capsule)
    draw.rounded_rectangle(
        [mic_x, mic_y, mic_x + mic_w, mic_y + mic_h],
        radius=mic_r,
        fill=white,
    )

    # ── Stand arc ─────────────────────────────────────────────────────────
    arc_margin = int(s * 0.14)
    arc_box    = [arc_margin, int(s * 0.42), s - arc_margin, int(s * 0.68)]
    line_w     = max(2, int(s * 0.055))
    draw.arc(arc_box, start=0, end=180, fill=white, width=line_w)

    # ── Stem ──────────────────────────────────────────────────────────────
    stem_x = s // 2
    stem_y1 = int(s * 0.68)
    stem_y2 = int(s * 0.78)
    draw.line([(stem_x, stem_y1), (stem_x, stem_y2)], fill=white, width=line_w)

    # ── Base bar ──────────────────────────────────────────────────────────
    base_w  = int(s * 0.36)
    base_x  = (s - base_w) // 2
    base_y  = stem_y2
    base_h  = max(2, int(s * 0.05))
    draw.rounded_rectangle(
        [base_x, base_y, base_x + base_w, base_y + base_h],
        radius=base_h // 2,
        fill=white,
    )

    # ── Sparkle (top-right) ───────────────────────────────────────────────
    sp_x = int(s * 0.72)
    sp_y = int(s * 0.14)
    sp_r = max(2, int(s * 0.045))
    gold = (255, 220, 80, 230)

    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        outer = sp_r * 1.8
        inner = sp_r * 0.7
        ox = sp_x + outer * math.cos(rad)
        oy = sp_y + outer * math.sin(rad)
        ix = sp_x + inner * math.cos(rad + math.pi / 4)
        iy = sp_y + inner * math.sin(rad + math.pi / 4)
        draw.line([(sp_x, sp_y), (ox, oy)], fill=gold, width=max(1, int(s * 0.025)))

    return img


def main():
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [make_icon(s) for s in sizes]

    out = Path('icon.ico')
    frames[0].save(
        out,
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f"✅  icon.ico written ({out.stat().st_size // 1024} KB) with sizes: {sizes}")


if __name__ == '__main__':
    main()
