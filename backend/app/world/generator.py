"""Deterministic chunk-based voxel terrain + starter-city placement.

Terrain is a pure function of (seed, gen_version, x, z, chunk-unlocked). Only the seed, the unlocked
chunk list and placed items are persisted; chunks are regenerated on demand.
Tile codes: 0 grass, 1 water, 2 sand, 3 road, 4 forest (unclaimed land only), 5 bridge.
"""
import math
import zlib
from functools import lru_cache

from .catalogue import BUILDINGS, footprint

CHUNK = 16
GEN_VERSION = 1
GRASS, WATER, SAND, ROAD, FOREST, BRIDGE = range(6)
ROAD_SPACING = 8
CENTER = (8, 8)  # centre of the 3x3 starter chunks
STARTER_CHUNKS = [(cx, cz) for cx in (-1, 0, 1) for cz in (-1, 0, 1)]


def hash01(seed: int, x: int, z: int, salt: int = 0) -> float:
    n = (x * 374761393 + z * 668265263 + seed * 2147483647 + salt * 1274126177) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((n ^ (n >> 16)) & 0xFFFFFFFF) / 0xFFFFFFFF


def noise(seed: int, x: float, z: float, scale: float, salt: int = 0) -> float:
    fx, fz = x / scale, z / scale
    x0, z0 = math.floor(fx), math.floor(fz)
    tx, tz = fx - x0, fz - z0
    tx, tz = tx * tx * (3 - 2 * tx), tz * tz * (3 - 2 * tz)
    a, b = hash01(seed, x0, z0, salt), hash01(seed, x0 + 1, z0, salt)
    c, d = hash01(seed, x0, z0 + 1, salt), hash01(seed, x0 + 1, z0 + 1, salt)
    return (a + (b - a) * tx) * (1 - tz) + (c + (d - c) * tx) * tz


def seed_from(login: str, salt: str = "") -> int:
    return zlib.crc32(f"devtown:{GEN_VERSION}:{login.lower()}:{salt}".encode()) & 0x7FFFFFFF


def river_z(seed: int, x: int) -> float:
    base = 9 + hash01(seed, 1, 1, 7) * 7
    phase = hash01(seed, 2, 2, 9) * 6.28
    return base + 2.6 * math.sin(x / 8.5 + phase) + 1.2 * math.sin(x / 3.7 + phase * 2)


def chunk_of(x: int, z: int):
    return (x // CHUNK, z // CHUNK)


def tile(seed: int, x: int, z: int, unlocked: bool):
    """returns (height, code)."""
    dz = abs(z - river_z(seed, x))
    water, bank = dz <= 1.6, dz <= 2.9
    if unlocked:
        road_v, road_h = x % ROAD_SPACING == 0, z % ROAD_SPACING == 0
        if water:
            return (1, BRIDGE) if road_v else (0, WATER)
        if road_v or road_h:
            return (1, ROAD)
        return (1, SAND if bank else GRASS)
    ring = max(abs(x // CHUNK), abs(z // CHUNK))
    if water:
        return 0, WATER
    n = noise(seed, x, z, 11, 3)
    h = 1 + int(max(0.0, n - 0.5) * 6 * min(1.0, ring / 3))
    if bank:
        return 1, SAND
    if noise(seed, x, z, 5, 4) > 0.62:
        return h, FOREST
    return h, GRASS


@lru_cache(maxsize=4096)
def _chunk(seed: int, cx: int, cz: int, unlocked: bool):
    hs, ts = [], []
    for lz in range(CHUNK):
        for lx in range(CHUNK):
            h, t = tile(seed, cx * CHUNK + lx, cz * CHUNK + lz, unlocked)
            hs.append(h)
            ts.append(t)
    return tuple(hs), tuple(ts)


def generate_chunk(seed: int, cx: int, cz: int, unlocked: bool, edge_bounds=None) -> dict:
    h, t = _chunk(seed, cx, cz, unlocked)
    heights, tiles = list(h), list(t)
    if unlocked and edge_bounds:
        max_x, max_z = edge_bounds
        for lz in range(CHUNK):
            for lx in range(CHUNK):
                x, z = cx * CHUNK + lx, cz * CHUNK + lz
                if x == max_x or z == max_z:
                    i = lz * CHUNK + lx
                    tiles[i] = BRIDGE if tiles[i] in (WATER, BRIDGE) else ROAD
                    heights[i] = 1
    return {"cx": cx, "cz": cz, "unlocked": unlocked, "h": heights, "t": tiles}


class TileMap:
    def __init__(self, seed: int, unlocked_chunks):
        self.seed = seed
        self.unlocked = {tuple(c) for c in unlocked_chunks}
        self.max_x = (max((c[0] for c in self.unlocked), default=0) + 1) * CHUNK - 1
        self.max_z = (max((c[1] for c in self.unlocked), default=0) + 1) * CHUNK - 1

    def at(self, x: int, z: int):
        c = (x // CHUNK, z // CHUNK)
        heights, tiles = _chunk(self.seed, c[0], c[1], c in self.unlocked)
        i = (z % CHUNK) * CHUNK + (x % CHUNK)
        h, t = heights[i], tiles[i]
        if c in self.unlocked and (x == self.max_x or z == self.max_z):
            # Close the east and north edges of the claimed map. Min edges
            # already align with the normal 8-tile street grid.
            t = BRIDGE if t in (WATER, BRIDGE) else ROAD
            h = 1
        return h, t

    def is_claimed(self, x, z):
        return (x // CHUNK, z // CHUNK) in self.unlocked


def occupancy(items, skip_id=None):
    occ = {}
    for it in items:
        if it["id"] == skip_id:
            continue
        for p in footprint(it["type"], it["x"], it["z"], it["rot"])[0]:
            occ[p] = it["id"]
    return occ


def placement_error(tm: TileMap, items, btype, x, z, rot, skip_id=None):
    """None if placeable, otherwise a short reason. Used for generation and user edits."""
    if btype not in BUILDINGS:
        return "unknown building"
    occ = occupancy(items, skip_id)
    for p in footprint(btype, x, z, rot)[0]:
        if not tm.is_claimed(*p):
            return "outside claimed land"
        _, t = tm.at(*p)
        if t not in (GRASS, SAND):
            return "tile is not buildable"
        if p in occ:
            return "tile is occupied"
    return None


def _anchor(category: str):
    ang = (zlib.crc32(category.encode()) % 360) * math.pi / 180
    return CENTER[0] + 12 * math.cos(ang), CENTER[1] + 12 * math.sin(ang)


def place_starter(seed: int, plan: list[dict], unlocked_chunks, limit: int, lights: int = 0, markers: int = 0):
    """Greedy deterministic district placement. plan entries: {'building': id, ...} in priority order."""
    tm = TileMap(seed, unlocked_chunks)
    items, deferred, nid = [], [], 1
    xs = [c[0] * CHUNK + i for c in tm.unlocked for i in range(CHUNK)]
    zs = [c[1] * CHUNK + i for c in tm.unlocked for i in range(CHUNK)]
    xr, zr = sorted(set(xs)), sorted(set(zs))
    for entry in plan[:limit] if limit else plan:
        bt = entry["building"]
        ax, az = _anchor(BUILDINGS[bt]["category"])
        best = None
        for x in xr:
            for z in zr:
                for rot in (0, 1):
                    fp, w, d = footprint(bt, x, z, rot)
                    # keep a 1-tile margin from roads so blocks read as blocks
                    if (x % ROAD_SPACING) + w > ROAD_SPACING or (z % ROAD_SPACING) + d > ROAD_SPACING:
                        continue
                    score = 0.5 * math.hypot(x - CENTER[0], z - CENTER[1]) + 0.8 * math.hypot(x - ax, z - az) + hash01(seed, x, z, nid) * 2
                    if best and score >= best[0]:
                        continue
                    if placement_error(tm, items, bt, x, z, rot) is None:
                        best = (score, x, z, rot)
        if best:
            items.append({"id": nid, "type": bt, "x": best[1], "z": best[2], "rot": best[3], "origin": "generated"})
            nid += 1
        else:
            deferred.append(bt)
    # Give every starter town a few small green spaces, even when GitHub has no
    # repository evidence yet. Park placement is seeded and avoids buildings.
    parks = 0
    for x in xr:
        for z in zr:
            if parks >= 4:
                break
            if x % 24 == 12 and z % 24 == 12 and placement_error(tm, items, "park", x, z, 0) is None:
                items.append({"id": nid, "type": "park", "x": x, "z": z, "rot": 0, "origin": "generated"})
                nid += 1
                parks += 1
    # decorations: trees, parks, street lights, milestone markers
    for x in xr:
        for z in zr:
            if hash01(seed, x, z, 77) < 0.045 and placement_error(tm, items, "tree", x, z, 0) is None:
                items.append({"id": nid, "type": "tree", "x": x, "z": z, "rot": 0, "origin": "generated"})
                nid += 1
    placed = 0
    for x in xr:
        for z in zr:
            if placed >= lights:
                break
            if x % ROAD_SPACING == 1 and z % ROAD_SPACING == 4 and placement_error(tm, items, "streetlight", x, z, 0) is None:
                items.append({"id": nid, "type": "streetlight", "x": x, "z": z, "rot": 0, "origin": "generated"})
                nid += 1
                placed += 1
    return items, deferred, nid


def place_budgeted(seed: int, candidates: list[tuple[str, int]], unlocked_chunks: list[list[int]], coins: int, materials: int):
    """Fill claimed land with the best affordable buildings, favoring population density."""
    tm = TileMap(seed, unlocked_chunks)
    items, spent, nid = [], {"coins": 0, "materials": 0}, 1
    xs = sorted({c[0] * CHUNK + i for c in tm.unlocked for i in range(CHUNK)})
    zs = sorted({c[1] * CHUNK + i for c in tm.unlocked for i in range(CHUNK)})
    remaining = list(candidates)
    for _ in range(256):
        options = []
        for bt, priority in remaining:
            b = BUILDINGS[bt]
            cost = {"coins": b["coins"], "materials": b["materials"]}
            if spent["coins"] + cost["coins"] > coins or spent["materials"] + cost["materials"] > materials:
                continue
            best = None
            for x in xs:
                for z in zs:
                    for rot in (0, 1):
                        _, w, d = footprint(bt, x, z, rot)
                        if (x % ROAD_SPACING) + w > ROAD_SPACING or (z % ROAD_SPACING) + d > ROAD_SPACING:
                            continue
                        if placement_error(tm, items, bt, x, z, rot) is not None:
                            continue
                        distance = math.hypot(x - CENTER[0], z - CENTER[1])
                        score = distance + hash01(seed, x, z, nid) * 2
                        if best is None or score < best[0]:
                            best = (score, x, z, rot)
            if best:
                population = 3 if BUILDINGS[bt]["category"] == "residential" else 1
                density = population / max(1, cost["coins"] + cost["materials"])
                # Population density is the primary objective; profile priority
                # breaks close ties without allowing expensive landmarks to
                # crowd out many affordable homes.
                options.append((density * 1000 + priority * 0.02, bt, best, cost))
        if not options:
            break
        _, bt, best, cost = max(options, key=lambda option: option[0])
        items.append({"id": nid, "type": bt, "x": best[1], "z": best[2], "rot": best[3], "origin": "auto"})
        nid += 1
        spent["coins"] += cost["coins"]
        spent["materials"] += cost["materials"]
    return items, spent, nid


def neighbours(unlocked):
    s = {tuple(c) for c in unlocked}
    out = set()
    for cx, cz in s:
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (cx + dx, cz + dz) not in s:
                out.add((cx + dx, cz + dz))
    return sorted(out)
