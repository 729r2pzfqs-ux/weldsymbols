#!/usr/bin/env python3
"""Generate the favicon pack for weldsymbols.org.

The mark is a simplified fillet weld symbol — a reference line with the
fillet triangle hanging below it on the arrow side. It is the same lockup as
the header logo with the leader and arrowhead dropped, because at 16 pixels
the arrow collapses into noise.

Output lands in static/favicons/ and is committed. generate_site.py copies it
to the site root at build time, so the build itself still depends only on
Jinja2 — this script needs Pillow but is only run when the icon changes:

    python3 scripts/make_favicons.py
"""

import os
import struct

from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "favicons")

BG = (13, 18, 24, 255)        # --bg        #0d1218
LINE = (200, 210, 226, 255)   # --svg-line  #c8d2e2
ACCENT = (255, 138, 61, 255)  # --accent    #ff8a3d

# Geometry in fractions of the canvas, so every size is the same drawing.
# Vertically the mark spans from the top of the reference line to the point of
# the triangle; those bounds are centred on the canvas rather than the line
# itself, or the whole icon sits visibly low.
LINE_Y = 0.32
LINE_X0, LINE_X1 = 0.13, 0.87
LINE_W = 0.095
TRI = ((0.31, 0.32), (0.31, 0.74), (0.71, 0.32))

SS = 8  # supersampling factor; ImageDraw has no antialiasing of its own


def render(size, radius_frac=0.18, full_bleed=False):
    """Draw the mark at `size` px, supersampled then downscaled for clean edges."""
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if full_bleed:
        d.rectangle([0, 0, s, s], fill=BG)
    else:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius_frac * s, fill=BG)

    width = max(1, int(round(LINE_W * s)))
    y = LINE_Y * s
    d.line([(LINE_X0 * s, y), (LINE_X1 * s, y)], fill=LINE, width=width)
    # Round the line ends by hand; ImageDraw has no cap style.
    r = width / 2
    for x in (LINE_X0 * s, LINE_X1 * s):
        d.ellipse([x - r, y - r, x + r, y + r], fill=LINE)

    d.polygon([(px * s, py * s) for px, py in TRI], fill=ACCENT)

    return img.resize((size, size), Image.LANCZOS)


def write_ico(path, images):
    """Assemble a multi-resolution .ico with PNG-compressed entries.

    Pillow's own ICO writer resizes a single source image for every entry;
    building the container here lets each size keep the art rendered for it.
    PNG-in-ICO is understood by every current browser and by Windows Vista on.
    """
    import io

    payloads = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        payloads.append(buf.getvalue())

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blobs = b"", b""
    for img, data in zip(images, payloads):
        w = 0 if img.width >= 256 else img.width
        h = 0 if img.height >= 256 else img.height
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)

    with open(path, "wb") as fh:
        fh.write(header + entries + blobs)


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" role="img" aria-label="WeldSymbols">
  <rect width="100" height="100" rx="18" fill="#0d1218"/>
  <line x1="13" y1="32" x2="87" y2="32" stroke="#c8d2e2" stroke-width="9.5" stroke-linecap="round"/>
  <polygon points="31,32 31,74 71,32" fill="#ff8a3d"/>
</svg>
"""


def build():
    os.makedirs(OUT, exist_ok=True)
    written = []

    def save(img, name):
        path = os.path.join(OUT, name)
        img.save(path, format="PNG", optimize=True)
        written.append((name, os.path.getsize(path)))

    ico_16 = render(16, radius_frac=0.12)
    ico_32 = render(32, radius_frac=0.14)
    # Google Search requires a favicon whose side is a multiple of 48 px; with only
    # 16 and 32 available it upscales the small one and the result looks tiny.
    ico_48 = render(48, radius_frac=0.16)

    save(ico_16, "favicon-16x16.png")
    save(ico_32, "favicon-32x32.png")
    save(ico_48, "favicon-48x48.png")
    save(render(96, radius_frac=0.18), "favicon-96x96.png")
    # Full bleed: iOS and Windows apply their own mask, so transparent
    # corners would show through as artefacts.
    save(render(180, full_bleed=True), "apple-touch-icon.png")
    save(render(150, full_bleed=True), "mstile-150x150.png")
    save(render(192, radius_frac=0.20), "android-chrome-192x192.png")
    save(render(512, radius_frac=0.22), "android-chrome-512x512.png")

    ico_path = os.path.join(OUT, "favicon.ico")
    write_ico(ico_path, [ico_16, ico_32, ico_48])
    written.append(("favicon.ico", os.path.getsize(ico_path)))

    svg_path = os.path.join(OUT, "favicon.svg")
    with open(svg_path, "w", encoding="utf-8") as fh:
        fh.write(SVG)
    written.append(("favicon.svg", os.path.getsize(svg_path)))

    print(f"wrote {len(written)} files to {os.path.normpath(OUT)}")
    for name, size in written:
        print(f"  {name:28} {size:>7,} bytes")


if __name__ == "__main__":
    build()
