#!/usr/bin/env python3
"""Generate the joint-type cross-section drawings used on the joint pages.

Shares the drawing conventions and CSS hooks defined in make_symbol_svgs.py:
base metal uses the `part` class, deposited weld metal uses `weld`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_symbol_svgs import STYLE, VIEWBOX  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static", "joints")


def doc(body, title, desc, uid):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VIEWBOX}" '
        f'role="img" aria-labelledby="{uid}-t {uid}-d">\n'
        f'  <title id="{uid}-t">{title}</title>\n'
        f'  <desc id="{uid}-d">{desc}</desc>\n'
        f'  <style>{STYLE}  </style>\n  '
        + "\n  ".join(body)
        + "\n</svg>\n"
    )


def butt_joint():
    return [
        '<path class="part" d="M28,72 H120 L136,122 H28 Z"/>',
        '<path class="part" d="M252,72 H160 L144,122 H252 Z"/>',
        '<path class="weld" d="M120,72 Q140,60 160,72 L144,122 H136 Z"/>',
        '<text class="lbl" x="28" y="34">Two members in the same plane, edge to edge</text>',
    ]


def lap_joint():
    return [
        '<rect class="part" x="28" y="96" width="172" height="30"/>',
        '<rect class="part" x="80" y="66" width="172" height="30"/>',
        '<path class="weld" d="M80,96 L80,70 L52,96 Z"/>',
        '<path class="weld" d="M200,96 L200,122 L226,96 Z"/>',
        '<text class="lbl" x="28" y="34">Members overlapping, filleted at each edge</text>',
    ]


def tee_joint():
    return [
        '<rect class="part" x="28" y="112" width="224" height="34"/>',
        '<rect class="part" x="126" y="40" width="30" height="72"/>',
        '<path class="weld" d="M126,112 L126,74 L88,112 Z"/>',
        '<path class="weld" d="M156,112 L156,74 L194,112 Z"/>',
        '<text class="lbl" x="28" y="30">One member perpendicular to the other</text>',
    ]


def corner_joint():
    return [
        # The distinguishing feature against a T-joint: the upright lands on
        # the END of the other member, not in the middle of it.
        '<rect class="part" x="60" y="112" width="192" height="34"/>',
        '<rect class="part" x="60" y="42" width="32" height="70"/>',
        '<path class="weld" d="M92,112 L92,80 L124,112 Z"/>',
        '<text class="lbl" x="28" y="30">Upright at the END of the other member, forming an L</text>',
    ]


def edge_joint():
    return [
        '<rect class="part" x="112" y="60" width="30" height="96"/>',
        '<rect class="part" x="142" y="60" width="30" height="96"/>',
        '<path class="weld" d="M112,60 Q142,36 172,60 Z"/>',
        '<text class="lbl" x="28" y="30">Parallel members welded along a common edge</text>',
    ]


JOINTS = [
    ("butt-joint", "Butt joint", butt_joint),
    ("lap-joint", "Lap joint", lap_joint),
    ("tee-joint", "T-joint", tee_joint),
    ("corner-joint", "Corner joint", corner_joint),
    ("edge-joint", "Edge joint", edge_joint),
]


def build():
    os.makedirs(OUT, exist_ok=True)
    for jid, title, fn in JOINTS:
        with open(os.path.join(OUT, f"{jid}.svg"), "w") as fh:
            fh.write(doc(fn(), f"{title} cross-section",
                         f"Cross-section through a {title.lower()}.", jid))
    print(f"wrote {len(JOINTS)} SVG files to {os.path.normpath(OUT)}")


if __name__ == "__main__":
    build()
