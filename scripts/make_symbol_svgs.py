#!/usr/bin/env python3
"""Generate the original SVG line drawings used on the welding symbol pages.

Two drawings are produced for every symbol:

  static/symbols/<id>.svg        the AWS A2.4 notation (reference line, leader,
                                 arrowhead and the weld symbol itself)
  static/symbols/<id>-joint.svg  a cross-section of the joint the symbol calls for

Both are plain, dependency-free SVG. Colours come from CSS custom properties
with hard-coded fallbacks, so the files look right inlined in a page or opened
on their own.
"""

import math
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "static", "symbols")

VIEWBOX = "0 0 280 180"

# Reference line geometry, shared by every notation drawing.
REF_Y = 90.0
REF_X1, REF_X2 = 80.0, 250.0
LEADER_END = (34.0, 138.0)

STYLE = """
  .ln   { fill: none; stroke: var(--svg-line, #c8d2e2); stroke-width: 2.4;
          stroke-linecap: round; stroke-linejoin: round; }
  .head { fill: var(--svg-line, #c8d2e2); stroke: none; }
  .sym  { fill: none; stroke: var(--svg-accent, #ff8a3d); stroke-width: 3;
          stroke-linecap: round; stroke-linejoin: round; }
  .symf { fill: var(--svg-accent, #ff8a3d); stroke: none; }
  .bar  { fill: none; stroke: var(--svg-accent, #ff8a3d); stroke-width: 5.5;
          stroke-linecap: round; }
  .part { fill: var(--svg-part, #3a4557); stroke: var(--svg-line, #c8d2e2);
          stroke-width: 2; stroke-linejoin: round; }
  .weld { fill: var(--svg-accent, #ff8a3d); stroke: var(--svg-accent, #ff8a3d);
          stroke-width: 1.5; stroke-linejoin: round; fill-opacity: .85; }
  .hair { fill: none; stroke: var(--svg-line, #c8d2e2); stroke-width: 1.2;
          stroke-dasharray: 5 4; opacity: .6; }
  .lbl  { fill: var(--svg-line, #c8d2e2); font: 500 12px ui-sans-serif, system-ui, sans-serif; }
"""


def arrowhead(tip, tail, length=15.0, half_width=5.2):
    """Filled triangle at `tip`, pointing away from `tail`."""
    dx, dy = tip[0] - tail[0], tip[1] - tail[1]
    mag = math.hypot(dx, dy)
    ux, uy = dx / mag, dy / mag
    bx, by = tip[0] - ux * length, tip[1] - uy * length
    px, py = -uy * half_width, ux * half_width
    pts = f"{tip[0]:.1f},{tip[1]:.1f} {bx + px:.1f},{by + py:.1f} {bx - px:.1f},{by - py:.1f}"
    return f'<polygon class="head" points="{pts}"/>'


def scaffold(tail_fork=False):
    """Reference line, leader and arrowhead — the frame every symbol sits on."""
    start = (REF_X1, REF_Y)
    parts = [
        f'<line class="ln" x1="{REF_X1}" y1="{REF_Y}" x2="{REF_X2}" y2="{REF_Y}"/>',
        f'<line class="ln" x1="{start[0]}" y1="{start[1]}" '
        f'x2="{LEADER_END[0]}" y2="{LEADER_END[1]}"/>',
        arrowhead(LEADER_END, start),
    ]
    if tail_fork:
        parts.append(f'<polyline class="ln" points="{REF_X2 - 26},{REF_Y - 16} '
                     f'{REF_X2},{REF_Y} {REF_X2 - 26},{REF_Y + 16}"/>')
    return parts


def doc(body, title, desc, uid):
    """`uid` keeps title/desc ids unique, since several of these get inlined
    into the same HTML page."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VIEWBOX}" '
        f'role="img" aria-labelledby="{uid}-t {uid}-d">\n'
        f'  <title id="{uid}-t">{title}</title>\n'
        f'  <desc id="{uid}-d">{desc}</desc>\n'
        f'  <style>{STYLE}  </style>\n  '
        + "\n  ".join(body)
        + "\n</svg>\n"
    )


# --------------------------------------------------------------------------
# Notation drawings: the weld symbol on the reference line.
# --------------------------------------------------------------------------

def sym_fillet():
    # Right triangle, perpendicular leg always on the left, below the line.
    return ['<polygon class="symf" points="140,90 140,122 172,90"/>']


def sym_v_groove():
    return ['<polyline class="sym" points="136,90 153,121 170,90"/>']


def sym_bevel_groove():
    # Perpendicular leg on the left; the leader is broken to point at the
    # member that gets prepared.
    return ['<polyline class="sym" points="146,90 146,121 169,90"/>']


def sym_u_groove():
    return ['<path class="sym" d="M136,90 C136,122 170,122 170,90"/>']


def sym_j_groove():
    return ['<path class="sym" d="M144,90 V106 C144,122 168,122 168,90"/>']


def sym_plug():
    return ['<rect class="sym" x="138" y="90" width="34" height="28"/>']


def sym_slot():
    return ['<rect class="sym" x="128" y="90" width="54" height="28"/>']


def sym_spot():
    return ['<circle class="sym" cx="153" cy="90" r="16"/>']


def sym_seam():
    # A circle with a horizontal line through it. The bar is drawn heavier and
    # longer than the circle so it reads as part of the symbol rather than as
    # the reference line passing behind.
    return [
        '<line class="bar" x1="115" y1="90" x2="191" y2="90"/>',
        '<circle class="sym" cx="153" cy="90" r="16"/>',
    ]


def sym_back():
    # Groove symbol on the arrow side, backing semicircle on the other side.
    return [
        '<polyline class="sym" points="128,90 153,123 178,90"/>',
        '<path class="sym" d="M139,90 Q153,64 167,90"/>',
    ]


def sym_surfacing():
    return [
        '<path class="sym" d="M126,90 Q141,118 156,90"/>',
        '<path class="sym" d="M156,90 Q171,118 186,90"/>',
    ]


# --------------------------------------------------------------------------
# Joint cross-sections: what the finished weld looks like.
# --------------------------------------------------------------------------

def joint_fillet():
    return [
        '<rect class="part" x="34" y="112" width="212" height="34"/>',
        '<rect class="part" x="128" y="34" width="30" height="78"/>',
        '<path class="weld" d="M128,112 L128,66 L82,112 Z"/>',
        '<text class="lbl" x="34" y="30">T-joint, one fillet on the arrow side</text>',
    ]


def joint_v_groove():
    return [
        '<path class="part" d="M34,74 H116 L134,124 H34 Z"/>',
        '<path class="part" d="M246,74 H164 L146,124 H246 Z"/>',
        '<path class="weld" d="M116,74 Q140,64 164,74 L146,124 H134 Z"/>',
        '<text class="lbl" x="34" y="30">Both members bevelled, single-V groove</text>',
    ]


def joint_bevel_groove():
    return [
        '<path class="part" d="M34,70 H138 V128 H34 Z"/>',
        '<path class="part" d="M246,70 H192 L150,128 H246 Z"/>',
        '<path class="weld" d="M138,70 Q165,58 192,70 L150,128 H138 Z"/>',
        '<text class="lbl" x="34" y="30">One member bevelled, one left square</text>',
    ]


def joint_u_groove():
    return [
        '<path class="part" d="M34,74 H124 C124,102 128,116 138,124 H34 Z"/>',
        '<path class="part" d="M246,74 H156 C156,102 152,116 142,124 H246 Z"/>',
        '<path class="weld" d="M124,74 Q140,64 156,74 C156,102 152,116 142,124 '
        'H138 C128,116 124,102 124,74 Z"/>',
        '<text class="lbl" x="34" y="30">Curved prep, narrow root, less filler</text>',
    ]


def joint_j_groove():
    return [
        '<path class="part" d="M34,70 H138 V128 H34 Z"/>',
        '<path class="part" d="M246,70 H182 C182,104 176,120 158,128 H246 Z"/>',
        '<path class="weld" d="M138,70 Q160,58 182,70 C182,104 176,120 158,128 H138 Z"/>',
        '<text class="lbl" x="34" y="30">J prep on one member only</text>',
    ]


def joint_plug():
    return [
        '<rect class="part" x="34" y="106" width="212" height="34"/>',
        '<path class="part" d="M34,68 H124 V106 H156 V68 H246 V106 H34 Z"/>',
        '<path class="weld" d="M124,68 Q140,60 156,68 V106 H124 Z"/>',
        '<text class="lbl" x="34" y="30">Round hole in the top member, filled</text>',
    ]


def joint_slot():
    return [
        '<rect class="part" x="34" y="106" width="212" height="34"/>',
        '<path class="part" d="M34,68 H104 V106 H176 V68 H246 V106 H34 Z"/>',
        '<path class="weld" d="M104,68 Q140,60 176,68 V106 H104 Z"/>',
        '<text class="lbl" x="34" y="30">Elongated slot in the top member, filled</text>',
    ]


def joint_spot():
    return [
        '<rect class="part" x="34" y="98" width="212" height="26"/>',
        '<rect class="part" x="34" y="72" width="212" height="26"/>',
        '<ellipse class="weld" cx="140" cy="98" rx="26" ry="17"/>',
        '<line class="hair" x1="140" y1="46" x2="140" y2="72"/>',
        '<line class="hair" x1="140" y1="124" x2="140" y2="150"/>',
        '<text class="lbl" x="34" y="30">Nugget formed at the faying surface</text>',
    ]


def joint_seam():
    return [
        '<rect class="part" x="34" y="98" width="212" height="26"/>',
        '<rect class="part" x="34" y="72" width="212" height="26"/>',
        '<rect class="weld" x="76" y="82" width="132" height="32" rx="16"/>',
        '<text class="lbl" x="34" y="30">Continuous nugget — overlapping spots</text>',
    ]


def joint_back():
    return [
        '<path class="part" d="M34,74 H116 L134,118 H34 Z"/>',
        '<path class="part" d="M246,74 H164 L146,118 H246 Z"/>',
        '<path class="weld" d="M116,74 Q140,64 164,74 L146,118 H134 Z"/>',
        '<path class="weld" d="M112,118 H168 Q140,148 112,118 Z"/>',
        '<text class="lbl" x="34" y="30">Bead deposited on the far side of the groove</text>',
    ]


def joint_surfacing():
    beads = "".join(
        f'<path class="weld" d="M{x},94 Q{x + 22},58 {x + 44},94 Z"/>'
        for x in (46, 84, 122, 160)
    )
    return [
        '<rect class="part" x="34" y="94" width="212" height="48"/>',
        beads,
        '<text class="lbl" x="34" y="30">Overlapping beads build the surface up</text>',
    ]


SYMBOLS = [
    ("fillet-weld", "Fillet weld symbol", sym_fillet, joint_fillet, False),
    ("v-groove-weld", "V-groove weld symbol", sym_v_groove, joint_v_groove, False),
    ("bevel-groove-weld", "Bevel-groove weld symbol", sym_bevel_groove,
     joint_bevel_groove, True),
    ("u-groove-weld", "U-groove weld symbol", sym_u_groove, joint_u_groove, False),
    ("j-groove-weld", "J-groove weld symbol", sym_j_groove, joint_j_groove, True),
    ("plug-weld", "Plug weld symbol", sym_plug, joint_plug, False),
    ("slot-weld", "Slot weld symbol", sym_slot, joint_slot, False),
    ("spot-weld", "Spot weld symbol", sym_spot, joint_spot, False),
    ("seam-weld", "Seam weld symbol", sym_seam, joint_seam, False),
    ("back-weld", "Back or backing weld symbol", sym_back, joint_back, False),
    ("surfacing-weld", "Surfacing weld symbol", sym_surfacing, joint_surfacing, False),
]


def broken_leader():
    """The kinked leader used on bevel and J-groove symbols."""
    knee = (58.0, 116.0)
    return [
        f'<polyline class="ln" points="{REF_X1},{REF_Y} {knee[0]},{knee[1]} '
        f'{LEADER_END[0]},{LEADER_END[1]}"/>',
        arrowhead(LEADER_END, knee),
    ]


def build():
    os.makedirs(OUT, exist_ok=True)
    for sid, title, sym_fn, joint_fn, broken in SYMBOLS:
        if broken:
            frame = [f'<line class="ln" x1="{REF_X1}" y1="{REF_Y}" '
                     f'x2="{REF_X2}" y2="{REF_Y}"/>'] + broken_leader()
        else:
            frame = scaffold()
        body = frame + sym_fn()
        with open(os.path.join(OUT, f"{sid}.svg"), "w") as fh:
            fh.write(doc(body, title,
                         f"AWS A2.4 {title.lower()}: reference line, leader, "
                         f"arrowhead and weld symbol.", sid))
        with open(os.path.join(OUT, f"{sid}-joint.svg"), "w") as fh:
            fh.write(doc(joint_fn(), f"{title.replace(' symbol', '')} joint section",
                         "Cross-section through the finished joint.", sid + "-j"))
    print(f"wrote {len(SYMBOLS) * 2} SVG files to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    build()
