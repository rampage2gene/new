"""Generate the application icon set (PNG sizes, Windows .ico, macOS .icns, SVG).

The artwork is drawn procedurally with Pillow so the repository does not need
binary design sources. Run:  python desktop/make_icon.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT = HERE / "icons"
SIZES = [16, 24, 32, 48, 64, 128, 256, 512, 1024]

NAVY_TOP = (14, 44, 84)
NAVY_BOTTOM = (7, 25, 52)
WAVE = (32, 122, 196)
WAVE_LIGHT = (86, 176, 232)
PAPER = (247, 249, 252)
PAPER_SHADOW = (203, 214, 228)
LINE = (150, 168, 190)
BOLT = (255, 196, 40)
BOLT_DARK = (222, 154, 12)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def render(size: int = 1024) -> Image.Image:
    """Draw the icon at `size` px, supersampled 4x for clean edges."""
    s = size * 4
    u = s / 1024  # unit scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # Background: vertical navy gradient inside a rounded square.
    bg = Image.new("RGB", (s, s))
    px = bg.load()
    for y in range(s):
        c = _lerp(NAVY_TOP, NAVY_BOTTOM, y / s)
        for x in range(s):
            px[x, y] = c
    mask = _rounded_mask(s, int(s * 0.22))
    img.paste(bg, (0, 0), mask)

    d = ImageDraw.Draw(img)

    # Sea: two sine waves across the lower third.
    def wave(amplitude, y_base, color, phase):
        pts = []
        steps = 96
        for i in range(steps + 1):
            x = s * i / steps
            y = y_base + amplitude * math.sin(2 * math.pi * (i / steps) * 2 + phase)
            pts.append((x, y))
        pts += [(s, s), (0, s)]
        d.polygon(pts, fill=color)

    wave(26 * u, 800 * u, WAVE_LIGHT, 0.6)
    wave(30 * u, 850 * u, WAVE, 2.4)
    img.putalpha(mask)

    d = ImageDraw.Draw(img)

    # Document sheet with folded corner.
    left, top, right, bottom = 292 * u, 190 * u, 732 * u, 740 * u
    fold = 110 * u
    shadow_off = 14 * u
    sheet_shadow = [
        (left + shadow_off, top + shadow_off),
        (right - fold + shadow_off, top + shadow_off),
        (right + shadow_off, top + fold + shadow_off),
        (right + shadow_off, bottom + shadow_off),
        (left + shadow_off, bottom + shadow_off),
    ]
    d.polygon(sheet_shadow, fill=(0, 0, 0, 70))
    sheet = [(left, top), (right - fold, top), (right, top + fold), (right, bottom), (left, bottom)]
    d.polygon(sheet, fill=PAPER)
    d.polygon([(right - fold, top), (right - fold, top + fold), (right, top + fold)], fill=PAPER_SHADOW)

    # Text lines on the sheet (schematic-like rows).
    lw = 18 * u
    y = top + 170 * u
    for i, frac in enumerate((0.62, 0.48, 0.70, 0.40)):
        x0 = left + 60 * u
        d.rounded_rectangle((x0, y, x0 + (right - left - 120 * u) * frac, y + lw), radius=lw / 2, fill=LINE)
        y += 62 * u

    # Lightning bolt over the sheet.
    cx, cy = 512 * u, 520 * u
    bolt = [
        (cx + 40 * u, cy - 250 * u),
        (cx - 110 * u, cy + 20 * u),
        (cx - 10 * u, cy + 20 * u),
        (cx - 60 * u, cy + 250 * u),
        (cx + 120 * u, cy - 40 * u),
        (cx + 15 * u, cy - 40 * u),
    ]
    shadow = [(x + 10 * u, y + 12 * u) for x, y in bolt]
    d.polygon(shadow, fill=(0, 0, 0, 60))
    d.polygon(bolt, fill=BOLT, outline=BOLT_DARK, width=int(8 * u))

    return img.resize((size, size), Image.LANCZOS)


def write_svg(path: Path) -> None:
    """Vector version of the same artwork for docs and Linux themes."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0e2c54"/><stop offset="1" stop-color="#071934"/>
    </linearGradient>
    <clipPath id="clip"><rect width="1024" height="1024" rx="225"/></clipPath>
  </defs>
  <g clip-path="url(#clip)">
    <rect width="1024" height="1024" fill="url(#bg)"/>
    <path d="M0 800 Q128 760 256 800 T512 800 T768 800 T1024 800 V1024 H0 Z" fill="#56b0e8"/>
    <path d="M0 860 Q128 830 256 860 T512 860 T768 860 T1024 860 V1024 H0 Z" fill="#207ac4"/>
  </g>
  <polygon points="306,204 636,204 746,314 746,754 306,754" fill="#000" opacity="0.27"/>
  <polygon points="292,190 622,190 732,300 732,740 292,740" fill="#f7f9fc"/>
  <polygon points="622,190 622,300 732,300" fill="#cbd6e4"/>
  <g fill="#96a8be">
    <rect x="352" y="360" width="236" height="18" rx="9"/>
    <rect x="352" y="422" width="182" height="18" rx="9"/>
    <rect x="352" y="484" width="266" height="18" rx="9"/>
    <rect x="352" y="546" width="152" height="18" rx="9"/>
  </g>
  <polygon points="562,282 412,552 512,552 462,782 642,492 537,492" fill="#000" opacity="0.24"/>
  <polygon points="552,270 402,540 502,540 452,770 632,480 527,480" fill="#ffc428" stroke="#de9a0c" stroke-width="8" stroke-linejoin="round"/>
</svg>
"""
    path.write_text(svg)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    master = render(1024)
    images = {}
    for size in SIZES:
        im = master.resize((size, size), Image.LANCZOS) if size != 1024 else master
        im.save(OUT / f"icon-{size}.png")
        images[size] = im
    images[1024].save(OUT / "icon.png")
    # Windows: multi-resolution .ico
    images[256].save(OUT / "icon.ico", sizes=[(s, s) for s in SIZES if s <= 256])
    # macOS: .icns from the 1024 master (Pillow writes all standard sizes)
    images[1024].save(OUT / "icon.icns")
    write_svg(OUT / "icon.svg")
    print(f"wrote {len(list(OUT.iterdir()))} files to {OUT}")


if __name__ == "__main__":
    main()
