"""Dedicated server-side banner camera with selectable day, dusk, and night lighting.
Pure Pillow (no GPU / browser needed) so it is reliable inside any container. Output is exactly 1734x574 PNG."""
import io
import math

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from ..world.catalogue import BUILDINGS, footprint
from ..world.generator import BRIDGE, FOREST, GRASS, ROAD, SAND, WATER, TileMap, hash01

W, H, SS = 1734, 574, 2
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _mul(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


GROUND = {GRASS: (118, 176, 98), SAND: (230, 208, 150), ROAD: (70, 74, 86), BRIDGE: (140, 128, 112),
          FOREST: (86, 150, 84), WATER: (62, 132, 196)}


def _view_items(city):
    return city.get("items", [])


def render_banner(city: dict, mode: str = "day") -> bytes:
    seed, unlocked = city["seed"], city["unlocked"]
    tm = TileMap(seed, unlocked)
    items = _view_items(city)
    cw, ch = W * SS, H * SS

    # ---- camera: fit the built-up area, centred; never zoomed out so far the city looks tiny
    pts = [p for it in items if it["type"] not in ("tree", "streetlight")
           for p in footprint(it["type"], it["x"], it["z"], it["rot"])[0]] or [(8, 8)]
    xs, zs = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, z0, z1 = min(xs) - 3, max(xs) + 4, min(zs) - 3, max(zs) + 4
    sxr = ((x1 - z0) - (x0 - z1))  # in half-tile units
    syr = ((x1 + z1) - (x0 + z0)) / 2
    tw = min(cw * 0.9 / max(sxr / 2, 1), ch * 0.8 / max(syr / 2 + 5, 1))
    tw = max(14 * SS, min(46 * SS, tw))
    u = tw * 0.5
    ccx, ccz = (x0 + x1) / 2, (z0 + z1) / 2
    ox = cw / 2 - (ccx - ccz) * tw / 2
    oy = ch * 0.54 - (ccx + ccz) * tw / 4

    def P(x, z, h=0.0):
        return (ox + (x - z) * tw / 2, oy + (x + z) * tw / 4 - h * u)

    # ---- sky
    img = Image.new("RGB", (cw, ch))
    d = ImageDraw.Draw(img)
    palettes = {
        "day": ((104, 170, 218), (185, 218, 228), (244, 248, 238)),
        "dusk": ((38, 52, 104), (126, 104, 156), (244, 170, 112)),
        "night": ((8, 15, 38), (28, 44, 78), (74, 91, 135)),
    }
    top, mid, hor = palettes.get(mode, palettes["day"])
    for y in range(ch):
        t = y / ch
        d.line([(0, y), (cw, y)], fill=_mix(top, mid, t / .45) if t < .45 else _mix(mid, hor, min(1, (t - .45) / .4)))
    if mode != "night":
        glow = Image.new("RGB", (cw, ch), (0, 0, 0))
        ImageDraw.Draw(glow).ellipse([cw * .72, ch * .02, cw * .9, ch * .38], fill=(255, 200, 130))
        glow = glow.filter(ImageFilter.GaussianBlur(ch * .12))
        img = ImageChops.add(img, glow.point(lambda v: int(v * (.28 if mode == "day" else .55))))
    d = ImageDraw.Draw(img, "RGBA")

    # ---- ground (painter's order by x+z)
    rx = int(cw / tw) + 6
    rz = int(ch * 2 / tw) + 8
    lo_x, hi_x = int(ccx) - rx, int(ccx) + rx
    lo_z, hi_z = int(ccz) - rx, int(ccz) + rx
    tiles = []
    for x in range(lo_x, hi_x):
        for z in range(lo_z, hi_z):
            px, py = P(x, z)
            if -tw <= px <= cw + tw and -tw * 3 <= py <= ch + tw * 2:
                tiles.append((x + z, x, z))
    tiles.sort()
    trees = []
    for _, x, z in tiles:
        h, t = tm.at(x, z)
        elev = 0.0 if t == WATER else 0.5 * h
        base = GROUND[t]
        j = 0.94 + 0.1 * hash01(seed, x, z, 5)
        top = _mul(base, j)
        if t == WATER:
            top = _mix(top, (150, 200, 235), 0.25 * hash01(seed, x, z, 6))
        a, b, c, e = P(x, z, elev), P(x + 1, z, elev), P(x + 1, z + 1, elev), P(x, z + 1, elev)
        if t != WATER and elev > 0:
            d.polygon([e, c, P(x + 1, z + 1, 0), P(x, z + 1, 0)], fill=_mul(base, .62))
            d.polygon([b, c, P(x + 1, z + 1, 0), P(x + 1, z, 0)], fill=_mul(base, .48))
        d.polygon([a, b, c, e], fill=top)
        if t in (ROAD, BRIDGE) and (x % 8 == 0) and z % 2 == 0 and t == ROAD:
            m1, m2 = P(x + .5, z + .2, elev), P(x + .5, z + .8, elev)
            d.line([m1, m2], fill=(235, 220, 140, 200), width=max(1, int(tw / 16)))
        if t == FOREST and hash01(seed, x, z, 8) < .8:
            trees.append((x, z, elev))

    # ---- objects (sorted by front edge)
    objs = []
    for it in items:
        fp, w, dd = footprint(it["type"], it["x"], it["z"], it["rot"])
        objs.append((it["x"] + w + it["z"] + dd, it, w, dd))
    for x, z, el in trees:
        objs.append((x + z + 2, {"type": "_tree", "x": x, "z": z, "rot": 0, "el": el}, 1, 1))
    objs.sort(key=lambda o: (o[0], o[1]["x"]))
    for _, it, w, dd in objs:
        t = it["type"]
        if t == "road":
            a, b, c, e = P(it["x"], it["z"], .5), P(it["x"] + 1, it["z"], .5), P(it["x"] + 1, it["z"] + 1, .5), P(it["x"], it["z"] + 1, .5)
            d.polygon([a, b, c, e], fill=(70, 74, 86))
            continue
        if t in ("tree", "_tree"):
            _tree(d, P(it["x"] + .5, it["z"] + .5, it.get("el", .5)), tw, hash01(seed, it["x"], it["z"], 3))
            continue
        if t == "streetlight":
            p = P(it["x"] + .5, it["z"] + .5, .5)
            d.line([p, (p[0], p[1] - u * 1.6)], fill=(40, 40, 50), width=max(1, int(tw / 14)))
            r = tw * .22
            d.ellipse([p[0] - r, p[1] - u * 1.6 - r, p[0] + r, p[1] - u * 1.6 + r], fill=(255, 226, 150, 235))
            continue
        b = BUILDINGS[t]
        if t == "park":
            a, bb, c, e = (P(it["x"], it["z"], .6), P(it["x"] + w, it["z"], .6), P(it["x"] + w, it["z"] + dd, .6), P(it["x"], it["z"] + dd, .6))
            d.polygon([a, bb, c, e], fill=(96, 168, 96))
            _tree(d, P(it["x"] + .7, it["z"] + .7, .6), tw, .3)
            continue
        _box(d, P, it["x"], it["z"], w, dd, b, tw, u, hash01(seed, it["x"], it["z"], 11))

    # Apply the selected lighting to the whole scene, not only the sky.
    brightness = {"day": 1.0, "dusk": 0.72, "night": 0.38}.get(mode, 1.0)
    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)

    # ---- evening light wash + vignette
    wash_color = {"day": (255, 255, 255), "dusk": (255, 150, 90), "night": (70, 90, 150)}.get(mode, (255, 255, 255))
    wash = Image.new("RGBA", (cw, ch), (*wash_color, 0))
    wd = ImageDraw.Draw(wash)
    for i in range(0, ch, 4):
        alpha = 8 if mode == "day" else 34 if mode == "dusk" else 12
        wd.rectangle([0, i, cw, i + 4], fill=(*wash_color, int(alpha * (i / ch))))
    img = Image.alpha_composite(img.convert("RGBA"), wash)

    # ---- overlay text
    ov = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    pad = 26 * SS
    f1, f2, f3 = _font(FONT_B, 30 * SS), _font(FONT_R, 17 * SS), _font(FONT_B, 13 * SS)
    name = city.get("name") or f"{city['username']}'s DevTown"
    user = f"@{city['username']}"
    wtxt = max(od.textlength(name, font=f1), od.textlength(user, font=f2) + 150 * SS)
    box = [pad, ch - pad - 86 * SS, pad + wtxt + 36 * SS, ch - pad]
    od.rounded_rectangle(box, radius=14 * SS, fill=(22, 26, 52, 188))
    od.text((box[0] + 18 * SS, box[1] + 10 * SS), name, font=f1, fill=(255, 255, 255, 255))
    od.text((box[0] + 18 * SS, box[1] + 54 * SS), user, font=f2, fill=(220, 224, 245, 255))
    lv = f"LEVEL {city.get('level', 1)}"
    lw = od.textlength(lv, font=f3)
    lx = box[0] + 18 * SS + od.textlength(user, font=f2) + 18 * SS
    od.rounded_rectangle([lx, box[1] + 55 * SS, lx + lw + 20 * SS, box[1] + 55 * SS + 24 * SS], radius=10 * SS, fill=(242, 177, 52, 255))
    od.text((lx + 10 * SS, box[1] + 59 * SS), lv, font=f3, fill=(30, 36, 64, 255))
    brand = "devtown"
    od.text((cw - pad - od.textlength(brand, font=f3), ch - pad - 16 * SS), brand, font=f3, fill=(255, 255, 255, 150))
    img = Image.alpha_composite(img, ov).convert("RGB").resize((W, H), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def _tree(d, p, tw, j):
    s = tw * (.32 + .1 * j)
    d.rectangle([p[0] - s * .12, p[1] - s * .5, p[0] + s * .12, p[1]], fill=(92, 64, 44))
    for k, col in enumerate(((46, 120, 70), (60, 142, 80))):
        y = p[1] - s * (.4 + k * .55)
        d.polygon([(p[0] - s * (.62 - k * .15), y), (p[0] + s * (.62 - k * .15), y), (p[0], y - s * 1.05)], fill=col)


def _box(d, P, x, z, w, dd, b, tw, u, j):
    col = _hex(b["color"])
    hh = b["h"]
    e = .5
    tops = hh + e
    A, B, C, D = P(x, z, tops), P(x + w, z, tops), P(x + w, z + dd, tops), P(x, z + dd, tops)
    gB, gC, gD = P(x + w, z, e), P(x + w, z + dd, e), P(x, z + dd, e)
    d.polygon([D, C, gC, gD], fill=_mul(col, .74))     # left face (z+ side)
    d.polygon([B, C, gC, gB], fill=_mul(col, .56))     # right face (x+ side)
    # windows
    for face, (p0, p1, g0, g1, sh) in (("L", (D, C, gD, gC, .5)), ("R", (B, C, gB, gC, .38))):
        n = max(1, int((w if face == "L" else dd) * 1.5))
        for f in range(hh):
            for k in range(n):
                if hash01(int(j * 1e6), k, f, ord(face)) < .62:
                    t0, t1 = (k + .25) / n, (k + .75) / n
                    y0, y1 = f + .25, f + .75
                    def pt(t, yy):
                        gx = g0[0] + (g1[0] - g0[0]) * t
                        gy = g0[1] + (g1[1] - g0[1]) * t
                        return (gx, gy - yy * u)
                    d.polygon([pt(t0, y0), pt(t1, y0), pt(t1, y1), pt(t0, y1)], fill=(255, 224, 150, 210))
    d.polygon([A, B, C, D], fill=_mul(col, 1.12))
    if b["h"] >= 5:  # setback crown
        s = .28
        a2, b2, c2, d2 = (P(x + w * s, z + dd * s, tops + 1.2), P(x + w * (1 - s), z + dd * s, tops + 1.2),
                          P(x + w * (1 - s), z + dd * (1 - s), tops + 1.2), P(x + w * s, z + dd * (1 - s), tops + 1.2))
        d.polygon([d2, c2, P(x + w * (1 - s), z + dd * (1 - s), tops), P(x + w * s, z + dd * (1 - s), tops)], fill=_mul(col, .8))
        d.polygon([b2, c2, P(x + w * (1 - s), z + dd * (1 - s), tops), P(x + w * (1 - s), z + dd * s, tops)], fill=_mul(col, .6))
        d.polygon([a2, b2, c2, d2], fill=_mul(col, 1.2))
    if b["id"] in ("broadcast_tower", "control_tower", "automation_tower"):
        m = P(x + w / 2, z + dd / 2, tops + 1.2)
        d.line([m, (m[0], m[1] - u * 2.2)], fill=(230, 230, 240), width=max(1, int(tw / 12)))
        d.ellipse([m[0] - tw * .08, m[1] - u * 2.2 - tw * .08, m[0] + tw * .08, m[1] - u * 2.2 + tw * .08], fill=(255, 90, 90))
