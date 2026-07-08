"""A unique, procedurally-generated app icon - no binary assets required.

We render a small RGBA image in code (a Kali-blue 'onion + chain link' mark on
a dark rounded tile) and encode it as a valid PNG using only the standard
library (zlib + struct). The base64 PNG can be handed straight to Tk via
`tk.PhotoImage(data=...)`, and the same bytes are written to disk for the
.desktop launcher.

The design: concentric rings (the Tor 'onion') pierced by a vertical chain
link (the 'chain'), in the Kali palette - instantly recognizable and ours.
"""
from __future__ import annotations

import base64
import math
import struct
import zlib

# Palette (matches theme.py)
_BG = (11, 14, 20, 255)        # #0B0E14
_BG_EDGE = (20, 26, 34, 255)
_BLUE = (54, 123, 240, 255)    # #367BF0 Kali blue
_BLUE_HI = (91, 149, 245, 255)
_CYAN = (23, 178, 195, 255)
_RED = (237, 28, 36, 255)      # dragon red accent
_WHITE = (233, 237, 245, 255)


def _blank(size, color):
    return [[list(color) for _ in range(size)] for _ in range(size)]


def _blend(dst, src, a):
    dst_a = dst[3] / 255.0
    out_a = dst_a * (1.0 - a) + a
    if out_a <= 0:
        return [0, 0, 0, 0]
    out_r = int((dst[0] * dst_a * (1.0 - a) + src[0] * a) / out_a)
    out_g = int((dst[1] * dst_a * (1.0 - a) + src[1] * a) / out_a)
    out_b = int((dst[2] * dst_a * (1.0 - a) + src[2] * a) / out_a)
    return [out_r, out_g, out_b, int(out_a * 255)]


def _aa_ring(px, size, cx, cy, radius, width, color):
    """Anti-aliased ring (annulus) centered at cx,cy."""
    for y in range(size):
        for x in range(size):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            edge = width / 2.0
            t = edge - abs(d - radius)
            if t > 0:
                a = min(1.0, t)
                px[y][x] = _blend(px[y][x], color, a)


def _aa_disc(px, size, cx, cy, radius, color):
    for y in range(size):
        for x in range(size):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            t = radius - d
            if t > 0:
                px[y][x] = _blend(px[y][x], color, min(1.0, t))


def _rounded_bg(px, size, rad):
    for y in range(size):
        for x in range(size):
            # distance outside the rounded rectangle -> transparent-ish edge
            dx = max(rad - x, x - (size - 1 - rad), 0)
            dy = max(rad - y, y - (size - 1 - rad), 0)
            corner = math.hypot(dx, dy)
            # vertical gradient background
            f = y / (size - 1)
            base = [int(_BG[i] * (1 - f) + _BG_EDGE[i] * f) for i in range(3)] + [255]
            if corner > rad:
                px[y][x] = [0, 0, 0, 0]
            elif corner > rad - 1:
                px[y][x] = base[:3] + [int(255 * (rad - corner))]
            else:
                px[y][x] = base


def render(size: int = 64) -> bytes:
    """Render the icon and return raw PNG bytes."""
    px = _blank(size, _BG)
    _rounded_bg(px, size, rad=max(6, size // 6))
    c = size / 2.0
    unit = size / 64.0
    # Onion rings.
    _aa_ring(px, size, c, c, 22 * unit, 3.0 * unit, _BLUE)
    _aa_ring(px, size, c, c, 15 * unit, 2.6 * unit, _CYAN)
    _aa_disc(px, size, c, c, 6.5 * unit, _BLUE_HI)
    # Vertical chain link piercing the onion (two rounded bars + gap = link).
    _aa_ring(px, size, c, c - 13 * unit, 6 * unit, 3.0 * unit, _WHITE)
    _aa_ring(px, size, c, c + 13 * unit, 6 * unit, 3.0 * unit, _WHITE)
    # Dragon-red status pip (bottom-right).
    _aa_disc(px, size, size - 13 * unit, size - 13 * unit, 5 * unit, _RED)
    return _encode_png(px, size)


def _encode_png(px, size) -> bytes:
    raw = bytearray()
    for y in range(size):
        raw.append(0)  # filter type 0 (None)
        for x in range(size):
            raw.extend(px[y][x])
    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return c + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")


def png_base64(size: int = 64) -> str:
    return base64.b64encode(render(size)).decode("ascii")


def write_png(path: str, size: int = 128) -> None:
    with open(path, "wb") as fh:
        fh.write(render(size))


def tk_photo(size: int = 64):
    """Return a tk.PhotoImage of the icon (Tk 8.6+ supports PNG via data=)."""
    import tkinter as tk
    return tk.PhotoImage(data=png_base64(size))
