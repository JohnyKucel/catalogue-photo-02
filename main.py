import math
import os
import struct
import zlib

W = 1024
H = 1024

buf = bytearray(W * H * 3)


def put(x, y, col):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        buf[i], buf[i + 1], buf[i + 2] = col


def blend(x, y, col, a):
    if 0 <= x < W and 0 <= y < H and a > 0:
        i = (y * W + x) * 3
        if a >= 1:
            buf[i], buf[i + 1], buf[i + 2] = col
        else:
            buf[i] = int(buf[i] * (1 - a) + col[0] * a)
            buf[i + 1] = int(buf[i + 1] * (1 - a) + col[1] * a)
            buf[i + 2] = int(buf[i + 2] * (1 - a) + col[2] * a)


def mix(c1, c2, t):
    return (
        int(c1[0] * (1 - t) + c2[0] * t),
        int(c1[1] * (1 - t) + c2[1] * t),
        int(c1[2] * (1 - t) + c2[2] * t),
    )


def shade(col, f):
    return (
        max(0, min(255, int(col[0] * f))),
        max(0, min(255, int(col[1] * f))),
        max(0, min(255, int(col[2] * f))),
    )


def hline(y, x0, x1, col, a=1.0):
    if y < 0 or y >= H:
        return
    x0 = max(0, x0)
    x1 = min(W - 1, x1)
    if x0 > x1:
        return
    if a >= 1:
        i = (y * W + x0) * 3
        buf[i:(y * W + x1 + 1) * 3] = bytes(col) * (x1 - x0 + 1)
    else:
        for x in range(x0, x1 + 1):
            blend(x, y, col, a)


def rect(x0, y0, x1, y1, col, a=1.0):
    for y in range(max(0, y0), min(H, y1 + 1)):
        hline(y, x0, x1, col, a)


def rrect(x0, y0, x1, y1, r, col, a=1.0):
    for y in range(y0, y1 + 1):
        if y < y0 + r:
            dy = y0 + r - y
            dx = int(r - math.sqrt(max(0, r * r - dy * dy)))
            hline(y, x0 + dx, x1 - dx, col, a)
        elif y > y1 - r:
            dy = y - (y1 - r)
            dx = int(r - math.sqrt(max(0, r * r - dy * dy)))
            hline(y, x0 + dx, x1 - dx, col, a)
        else:
            hline(y, x0, x1, col, a)


def ellipse(cx, cy, rx, ry, col, a=1.0):
    for dy in range(-ry, ry + 1):
        yy = cy + dy
        if yy < 0 or yy >= H:
            continue
        f = 1.0 - (dy / ry) ** 2
        if f < 0:
            continue
        dx = int(rx * math.sqrt(f))
        hline(yy, cx - dx, cx + dx, col, a)


def poly(pts, col, a=1.0):
    pts = [(int(p[0]), int(p[1])) for p in pts]
    ys = [p[1] for p in pts]
    for y in range(max(0, min(ys)), min(H, max(ys) + 1)):
        xs = []
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            if (y0 <= y < y1) or (y1 <= y < y0):
                t = (y - y0) / (y1 - y0)
                xs.append(int(x0 + t * (x1 - x0)))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            hline(y, xs[i], xs[i + 1], col, a)


def disc(cx, cy, r, col, a=1.0):
    ellipse(cx, cy, r, r, col, a)


def line(x0, y0, x1, y1, col, w=2, a=1.0):
    steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    for i in range(steps + 1):
        t = i / steps
        x = int(x0 + t * (x1 - x0))
        y = int(y0 + t * (y1 - y0))
        disc(x, y, max(1, w // 2), col, a)


def soft_shadow(cx, cy, rx, ry, peak=0.28):
    for k in range(9, 0, -1):
        f = k / 9.0
        ellipse(cx, cy, int(rx * f), int(ry * f), (60, 55, 48), peak * (1 - f) * 0.55)


def vgrad(top, bottom, y0=0, y1=1024):
    for y in range(y0, min(H, y1)):
        t = (y - y0) / max(1, y1 - y0)
        c = mix(top, bottom, t)
        i = y * W * 3
        buf[i:i + W * 3] = bytes(c) * W


GLYPHS = {
    "A": [14, 17, 17, 31, 17, 17, 17],
    "D": [30, 17, 17, 17, 17, 17, 30],
    "E": [31, 16, 16, 30, 16, 16, 31],
    "I": [14, 4, 4, 4, 4, 4, 14],
    "L": [16, 16, 16, 16, 16, 16, 31],
    "M": [17, 27, 21, 21, 17, 17, 17],
    "O": [14, 17, 17, 17, 17, 17, 14],
    "P": [30, 17, 17, 30, 16, 16, 16],
    "R": [30, 17, 17, 30, 20, 18, 17],
    "S": [15, 16, 16, 14, 1, 1, 30],
    "T": [31, 4, 4, 4, 4, 4, 4],
    "0": [14, 17, 19, 21, 25, 17, 14],
    "1": [4, 12, 4, 4, 4, 4, 14],
    "-": [0, 0, 0, 31, 0, 0, 0],
    " ": [0, 0, 0, 0, 0, 0, 0],
}


def text(s, x, y, scale, col):
    cx = x
    for ch in s:
        g = GLYPHS.get(ch, GLYPHS[" "])
        for row in range(7):
            bits = g[row]
            for b in range(5):
                if bits & (1 << (4 - b)):
                    rect(cx + b * scale, y + row * scale,
                         cx + b * scale + scale - 1,
                         y + row * scale + scale - 1, col)
        cx += 6 * scale


def text_w(s, scale):
    return len(s) * 6 * scale - scale


def chunk(typ, data):
    c = struct.pack(">I", len(data)) + typ + data
    c += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    return c


def write_png(path):
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        raw += buf[y * W * 3:(y + 1) * W * 3]
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n"
    data += chunk(b"IHDR", ihdr)
    data += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    data += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)


STEEL_L = (228, 230, 233)
STEEL_M = (196, 199, 204)
STEEL_D = (148, 152, 158)
STEEL_X = (110, 114, 120)
CREAM = (245, 239, 226)
RED = (178, 44, 34)
RED_L = (214, 84, 62)
CRUST = (176, 112, 44)
CRUST_D = (146, 88, 32)
CRUMB = (243, 214, 158)
BUTTER = (250, 214, 92)
INK = (52, 50, 46)


def background():
    vgrad((238, 236, 230), (206, 202, 193))
    ellipse(512, 700, 470, 120, (255, 252, 244), 0.10)
    ellipse(512, 700, 380, 90, (255, 252, 244), 0.10)


def plate(cx, cy):
    soft_shadow(cx, cy + 26, 148, 28, 0.30)
    ellipse(cx, cy, 148, 48, (178, 174, 166), 1.0)
    ellipse(cx, cy - 8, 148, 48, (250, 250, 248), 1.0)
    ellipse(cx, cy - 8, 148, 48, (226, 224, 220), 0.35)
    ellipse(cx, cy - 10, 112, 34, (238, 238, 236), 1.0)
    ellipse(cx, cy - 10, 112, 34, (210, 208, 204), 0.18)
    ellipse(cx - 46, cy - 24, 40, 9, (255, 255, 255), 0.55)


def toaster():
    soft_shadow(440, 862, 250, 34, 0.32)
    rect(368, 838, 392, 852, (58, 56, 52))
    rect(488, 838, 512, 852, (58, 56, 52))
    poly([(300, 600), (580, 600), (566, 556), (314, 556)], STEEL_D)
    poly([(314, 556), (566, 556), (556, 548), (324, 548)], STEEL_X)
    rrect(326, 556, 414, 576, 8, (24, 22, 20))
    rrect(466, 556, 554, 576, 8, (24, 22, 20))
    rrect(332, 560, 408, 572, 6, (48, 44, 40))
    rrect(472, 560, 548, 572, 6, (48, 44, 40))
    for y in range(600, 840):
        t = (y - 600) / 239.0
        c = mix(STEEL_L, STEEL_M, t)
        if y < 640:
            c = mix(c, (255, 255, 255), 0.25 * (1 - (y - 600) / 40.0))
        if y < 626:
            dy = 626 - y
            dx = int(26 - math.sqrt(max(0, 26 * 26 - dy * dy)))
            hline(y, 300 + dx, 580 - dx, c)
        elif y > 814:
            dy = y - 814
            dx = int(26 - math.sqrt(max(0, 26 * 26 - dy * dy)))
            hline(y, 300 + dx, 580 - dx, c)
        else:
            hline(y, 300, 580, c)
        hline(y, 300, 306, (250, 251, 252), 0.85)
        hline(y, 308, 312, (255, 255, 255), 0.35)
        hline(y, 566, 580, STEEL_D, 0.9)
    line(300, 626, 580, 626, (120, 123, 128), 2, 0.35)
    line(300, 838, 580, 838, (96, 99, 104), 3, 0.6)
    for yy in range(636, 832, 18):
        line(306, yy, 574, yy, (255, 255, 255), 1, 0.05)
        line(306, yy + 1, 574, yy + 1, (90, 92, 96), 1, 0.05)
    bw = text_w("TOAST-AIR", 3)
    text("TOAST-AIR", 440 - bw // 2, 668, 3, (74, 76, 80))
    disc(440, 748, 26, (226, 228, 231))
    disc(440, 748, 26, (120, 123, 128), 0.25)
    disc(440, 748, 21, (238, 239, 241))
    line(440, 748, 440 + 13, 748 - 13, (178, 44, 34), 3)
    disc(440, 748, 4, (74, 76, 80))
    bw2 = text_w("MODEL P-01", 2)
    text("MODEL P-01", 440 - bw2 // 2, 792, 2, (110, 112, 116))
    disc(516, 668, 6, (214, 84, 62))
    disc(516, 668, 3, (255, 150, 120))
    rrect(580, 660, 596, 724, 8, STEEL_D)
    rrect(580, 660, 596, 690, 8, (88, 90, 95))
    rect(596, 676, 612, 700, (58, 56, 52))


def rot_pt(cx, cy, x, y, ang):
    ca = math.cos(ang)
    sa = math.sin(ang)
    return (cx + (x - cx) * ca - (y - cy) * sa,
            cy + (x - cx) * sa + (y - cy) * ca)


def rpoly_pts(cx, cy, hw, hh, r, ang):
    pts = []
    corners = [(hw - r, -hh + r, 270), (hw - r, hh - r, 0),
               (-hw + r, hh - r, 90), (-hw + r, -hh + r, 180)]
    for ccx, ccy, a0 in corners:
        for k in range(7):
            a = math.radians(a0 + 90 * k / 6)
            lx = ccx + r * math.cos(a)
            ly = ccy + r * math.sin(a)
            pts.append(rot_pt(cx, cy, cx + lx, cy + ly, ang))
    return pts


def toast(cx, cy, ang):
    hw, hh = 118, 82
    poly(rpoly_pts(cx, cy, hw, hh, 24, ang), CRUST_D)
    poly(rpoly_pts(cx, cy, hw - 12, hh - 12, 18, ang), CRUST)
    poly(rpoly_pts(cx, cy, hw - 24, hh - 24, 14, ang), CRUMB)
    seed = 12345
    for i in range(110):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        lx = -88 + (seed % 176)
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        ly = -52 + (seed % 104)
        px, py = rot_pt(cx, cy, cx + lx, cy + ly, ang)
        if abs(lx) < 88 and abs(ly) < 52:
            disc(int(px), int(py), 2, (214, 172, 108), 0.28)
    top = rot_pt(cx, cy, cx - 52, cy - hh + 8, ang)
    top2 = rot_pt(cx, cy, cx + 52, cy - hh + 8, ang)
    line(int(top[0]), int(top[1]), int(top2[0]), int(top2[1]), (196, 128, 54), 4, 0.6)
    bx, by = rot_pt(cx, cy, cx - 6, cy - 30, ang)
    bpts = []
    for sx, sy in [(-20, -12), (20, -12), (20, 12), (-20, 12)]:
        bpts.append(rot_pt(bx, by, bx + sx, by + sy, ang))
    poly(bpts, BUTTER)
    poly(bpts, (255, 240, 170), 0.4)
    gx, gy = rot_pt(cx, cy, cx - 22, cy - 38, ang)
    line(int(gx), int(gy), int(gx + 26), int(gy - 2), (255, 248, 210), 3, 0.8)
    hx, hy = rot_pt(cx, cy, cx - 30, cy + 34, ang)
    line(int(hx), int(hy), int(hx + 44), int(hy - 6), (255, 240, 200), 4, 0.45)


def parachute(cx, cy, rx, ry):
    panels = 6
    for i in range(panels):
        a0 = math.pi * i / panels
        a1 = math.pi * (i + 1) / panels
        pts = [(cx, cy)]
        steps = 14
        for s in range(steps + 1):
            a = a0 + (a1 - a0) * s / steps
            pts.append((cx + rx * math.cos(a), cy - ry * math.sin(a)))
        col = RED if i % 2 == 0 else CREAM
        poly(pts, col)
        pts2 = [(cx, cy)]
        for s in range(steps + 1):
            a = a0 + (a1 - a0) * s / steps
            pts2.append((cx + (rx - 26) * math.cos(a), cy - (ry - 18) * math.sin(a)))
        poly(pts2, RED_L if i % 2 == 0 else (252, 246, 236), 0.35)
    for i in range(panels + 1):
        a = math.pi * i / panels
        x = cx + rx * math.cos(a)
        y = cy - ry * math.sin(a)
        line(cx, cy, int(x), int(y), (120, 30, 22), 2, 0.55)
    ellipse(cx - 62, cy - 52, 48, 18, (255, 255, 255), 0.20)
    ellipse(cx, cy + 4, rx - 8, 10, (90, 22, 16), 0.18)
    line(cx - rx, cy + 2, cx + rx, cy + 2, (120, 30, 22), 3, 0.8)


def shroud_lines(canopy, toast_pts):
    for (x0, y0), (x1, y1) in zip(canopy, toast_pts):
        line(int(x0), int(y0), int(x1), int(y1), (70, 60, 52), 2)


def main():
    background()
    plate(730, 822)
    ellipse(710, 812, 96, 20, (120, 112, 100), 0.10)
    toaster()
    tcx, tcy = 700, 372
    ang = -0.24
    rim = [(522, 170), (606, 170), (700, 170), (794, 170), (878, 170)]
    tops = []
    for sx, sy in [(-104, -70), (-52, -78), (0, -82), (52, -78), (104, -70)]:
        tops.append(rot_pt(tcx, tcy, tcx + sx, tcy + sy, ang))
    shroud_lines(rim, tops)
    toast(tcx, tcy, ang)
    parachute(700, 168, 205, 92)
    out = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out, exist_ok=True)
    write_png(os.path.join(out, "entry.png"))


main()
