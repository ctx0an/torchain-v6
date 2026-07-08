import os
import math
import struct
import zlib

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
    # alpha blend src color into dst color
    alpha_out = a + (dst[3]/255.0) * (1 - a)
    if alpha_out == 0:
        return [0, 0, 0, 0]
    r = int((src[0] * a + dst[0] * (dst[3]/255.0) * (1 - a)) / alpha_out)
    g = int((src[1] * a + dst[1] * (dst[3]/255.0) * (1 - a)) / alpha_out)
    b = int((src[2] * a + dst[2] * (dst[3]/255.0) * (1 - a)) / alpha_out)
    return [r, g, b, int(alpha_out * 255)]

def _aa_ring(px, size, cx, cy, radius, width, color):
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
            dx = max(rad - x, x - (size - 1 - rad), 0)
            dy = max(rad - y, y - (size - 1 - rad), 0)
            corner = math.hypot(dx, dy)
            f = y / (size - 1)
            base = [int(_BG[i] * (1 - f) + _BG_EDGE[i] * f) for i in range(3)] + [255]
            if corner > rad:
                px[y][x] = [0, 0, 0, 0]
            elif corner > rad - 1:
                px[y][x] = base[:3] + [int(255 * (rad - corner))]
            else:
                px[y][x] = base

def _encode_png(px, size):
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            raw.extend(px[y][x])
    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return c + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")

def render_launcher(size, is_round=False):
    px = _blank(size, (0, 0, 0, 0))
    if is_round:
        _aa_disc(px, size, size/2.0, size/2.0, (size/2.0) - 1, _BG)
    else:
        _rounded_bg(px, size, rad=max(6, size // 6))
    
    c = size / 2.0
    unit = size / 64.0
    _aa_ring(px, size, c, c, 22 * unit, 3.0 * unit, _BLUE)
    _aa_ring(px, size, c, c, 15 * unit, 2.6 * unit, _CYAN)
    _aa_disc(px, size, c, c, 6.5 * unit, _BLUE_HI)
    _aa_ring(px, size, c, c - 13 * unit, 6 * unit, 3.0 * unit, _WHITE)
    _aa_ring(px, size, c, c + 13 * unit, 6 * unit, 3.0 * unit, _WHITE)
    _aa_disc(px, size, size - 13 * unit, size - 13 * unit, 5 * unit, _RED)
    return _encode_png(px, size)

def render_foreground(size):
    px = _blank(size, (0, 0, 0, 0))
    c = size / 2.0
    unit = size / 96.0
    _aa_ring(px, size, c, c, 22 * unit, 3.0 * unit, _BLUE)
    _aa_ring(px, size, c, c, 15 * unit, 2.6 * unit, _CYAN)
    _aa_disc(px, size, c, c, 6.5 * unit, _BLUE_HI)
    _aa_ring(px, size, c, c - 13 * unit, 6 * unit, 3.0 * unit, _WHITE)
    _aa_ring(px, size, c, c + 13 * unit, 6 * unit, 3.0 * unit, _WHITE)
    _aa_disc(px, size, size/2.0 + 20 * unit, size/2.0 + 20 * unit, 5 * unit, _RED)
    return _encode_png(px, size)

RES_DIR = "app/src/main/res"
CONFIGS = {
    "mipmap-mdpi": {"launcher": 48, "foreground": 108},
    "mipmap-hdpi": {"launcher": 72, "foreground": 162},
    "mipmap-xhdpi": {"launcher": 96, "foreground": 216},
    "mipmap-xxhdpi": {"launcher": 144, "foreground": 324},
    "mipmap-xxxhdpi": {"launcher": 192, "foreground": 432},
}

for folder, sizes in CONFIGS.items():
    folder_path = os.path.join(RES_DIR, folder)
    os.makedirs(folder_path, exist_ok=True)
    
    # 1. Standard ic_launcher
    with open(os.path.join(folder_path, "ic_launcher.png"), "wb") as f:
        f.write(render_launcher(sizes["launcher"], is_round=False))
        
    # 2. Round ic_launcher
    with open(os.path.join(folder_path, "ic_launcher_round.png"), "wb") as f:
        f.write(render_launcher(sizes["launcher"], is_round=True))
        
    # 3. Foreground ic_launcher
    with open(os.path.join(folder_path, "ic_launcher_foreground.png"), "wb") as f:
        f.write(render_foreground(sizes["foreground"]))

print("All Android launcher icons generated successfully!")
