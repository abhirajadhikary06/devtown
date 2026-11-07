import json
import uuid
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..banner.renderer import render_banner
from ..economy import rewards
from ..lighting import DEFAULT_PREFERENCES, banner_revision, resolve_mode
from ..mapping.engine import analyse, lock_reason
from ..models import Banner, City, Ledger
from ..world import generator as gen
from ..world.catalogue import BASE_UNLOCKS, BUILDINGS, FREE


# ---------- city construction
def new_city_data(snapshot: dict, analysis: dict, seed: int, auto_build: bool = True) -> dict:
    act = analysis["activity"]
    if auto_build:
        # Auto-build uses the complete profile plan. The generator still skips
        # buildings that cannot fit, preserving a valid deterministic layout.
        items, deferred, nid = gen.place_starter(seed, analysis["plan"], gen.STARTER_CHUNKS, 0, act["streetlights"], act["milestone_markers"])
    else:
        items, deferred, nid = [], analysis["plan"], 1
    return {"unlocked": [list(c) for c in gen.STARTER_CHUNKS], "items": items, "next_id": nid, "unlocks": analysis["unlocks"],
            "level": act["level"], "deferred": deferred, "lighting": dict(DEFAULT_PREFERENCES),
            "auto_build": auto_build}


@lru_cache
def demo_city() -> dict:
    snap = json.loads((Path(__file__).parent.parent / "data" / "demo_snapshot.json").read_text())
    an = analyse(snap)
    seed = gen.seed_from("demo")
    return {"username": "demo", "name": "Demo Heights", "seed": seed, "gen_version": gen.GEN_VERSION, "version": 1,
            "data": new_city_data(snap, an, seed), "analysis": an}


def city_dict(row: City) -> dict:
    d = row.data
    return {"username": row.username, "name": row.name, "seed": row.seed, "gen_version": row.gen_version, "version": row.version,
            "level": d.get("level", 1), "unlocked": d["unlocked"], "items": d["items"], "unlocks": d["unlocks"],
            "lighting": d.get("lighting", dict(DEFAULT_PREFERENCES))}


def view_payload(c: dict, ring: int = 1) -> dict:
    """Public city payload: claimed chunks plus `ring` chunks of generated wilderness around them."""
    unl = {tuple(x) for x in (c["unlocked"] if "unlocked" in c else c["data"]["unlocked"])}
    items = c.get("items") or c["data"]["items"]
    chunks = set(unl)
    edge_bounds = ((max(cx for cx, _ in unl) + 1) * gen.CHUNK - 1,
                   (max(cz for _, cz in unl) + 1) * gen.CHUNK - 1)
    for cx, cz in unl:
        for dx in range(-ring, ring + 1):
            for dz in range(-ring, ring + 1):
                chunks.add((cx + dx, cz + dz))
    return {"username": c["username"], "name": c["name"], "level": c.get("level", c.get("data", {}).get("level", 1)),
            "seed": c["seed"], "gen_version": c["gen_version"], "version": c["version"], "chunk_size": gen.CHUNK,
            "unlocked": sorted(unl), "items": items,
            "chunks": [gen.generate_chunk(c["seed"], cx, cz, (cx, cz) in unl, edge_bounds)
                       for cx, cz in sorted(chunks)],
            "expandable": [list(x) for x in gen.neighbours(unl)]}


def catalogue_payload(unlocks) -> list[dict]:
    u = set(unlocks)
    return [dict(b, unlocked=b["id"] in u or b["id"] in BASE_UNLOCKS,
                 lock_reason="" if b["id"] in u or b["id"] in BASE_UNLOCKS else lock_reason(b["id"]))
            for b in BUILDINGS.values()]


# ---------- ledger
def balances(db: Session, user_id: int) -> dict:
    rows = db.execute(select(Ledger.resource, func.sum(Ledger.amount)).where(Ledger.user_id == user_id).group_by(Ledger.resource)).all()
    b = {"energy": 0, "coins": 0, "materials": 0, "reputation": 0}
    b.update({r: int(s or 0) for r, s in rows})
    return b


def sync_grants(db: Session, user_id: int, snapshot: dict):
    granted: dict = {}
    for src, res, tot in db.execute(select(Ledger.source, Ledger.resource, func.sum(Ledger.amount)).where(
            Ledger.user_id == user_id, Ledger.amount > 0, Ledger.idem_key.like("grant:%")).group_by(Ledger.source, Ledger.resource)):
        granted[(src, res)] = int(tot)
    n = 0
    for row in rewards.grant_deltas(rewards.entitlements(snapshot), granted):
        exists = db.scalar(select(Ledger.id).where(Ledger.user_id == user_id, Ledger.idem_key == row["idem_key"]))
        if not exists:
            db.add(Ledger(user_id=user_id, **row))
            n += 1
    db.flush()
    return n


def spend(db: Session, user_id: int, cost: dict, reason: str, sign: int = -1):
    op = uuid.uuid4().hex
    for res in ("coins", "materials"):
        if cost.get(res):
            db.add(Ledger(user_id=user_id, resource=res, amount=sign * cost[res], source="spend" if sign < 0 else "refund",
                          idem_key=f"{'spend' if sign < 0 else 'refund'}:{op}:{res}", reason=reason))


class EditError(Exception):
    pass


# ---------- edits (all validated server-side)
def _afford(db, user_id, cost):
    b = balances(db, user_id)
    if b["coins"] < cost.get("coins", 0) or b["materials"] < cost.get("materials", 0):
        raise EditError("Not enough coins or materials")


def place(db, row: City, user_id: int, btype: str, x: int, z: int, rot: int):
    d = dict(row.data)
    if btype not in BUILDINGS:
        raise EditError("Unknown building")
    if btype not in d["unlocks"] and btype not in BASE_UNLOCKS:
        raise EditError("This building is not unlocked yet")
    tm = gen.TileMap(row.seed, d["unlocked"])
    err = gen.placement_error(tm, d["items"], btype, x, z, rot % 4)
    if err:
        raise EditError(err[0].upper() + err[1:])
    cost = {k: BUILDINGS[btype][k] for k in ("coins", "materials")}
    _afford(db, user_id, cost)
    spend(db, user_id, cost, f"build {btype}")
    item = {"id": d["next_id"], "type": btype, "x": x, "z": z, "rot": rot % 4, "origin": "user"}
    d["items"] = d["items"] + [item]
    d["next_id"] += 1
    _commit(row, d)
    return item


def remove(db, row: City, user_id: int, item_id: int):
    d = dict(row.data)
    it = next((i for i in d["items"] if i["id"] == item_id), None)
    if not it:
        raise EditError("Item not found")
    if it["origin"] == "user":
        b = BUILDINGS[it["type"]]
        spend(db, user_id, {"coins": b["coins"] // 2, "materials": b["materials"] // 2}, f"demolish {it['type']}", sign=1)
    d["items"] = [i for i in d["items"] if i["id"] != item_id]
    _commit(row, d)


def move(db, row: City, item_id: int, x: int, z: int, rot: int):
    d = dict(row.data)
    it = next((i for i in d["items"] if i["id"] == item_id), None)
    if not it:
        raise EditError("Item not found")
    tm = gen.TileMap(row.seed, d["unlocked"])
    err = gen.placement_error(tm, d["items"], it["type"], x, z, rot % 4, skip_id=item_id)
    if err:
        raise EditError(err[0].upper() + err[1:])
    d["items"] = [dict(i, x=x, z=z, rot=rot % 4) if i["id"] == item_id else i for i in d["items"]]
    _commit(row, d)


def expand(db, row: City, user_id: int, cx: int, cz: int):
    d = dict(row.data)
    if [cx, cz] not in [list(c) for c in map(list, gen.neighbours(d["unlocked"]))]:
        raise EditError("Land must touch your existing city")
    cost = rewards.expansion_cost(len(d["unlocked"]))
    if d.get("level", 1) < cost["min_level"]:
        raise EditError(f"Reach city level {cost['min_level']} to expand")
    _afford(db, user_id, cost)
    spend(db, user_id, cost, "land expansion")
    d["unlocked"] = d["unlocked"] + [[cx, cz]]
    _commit(row, d)


def _commit(row: City, d: dict):
    row.data = d          # reassign (not mutate) so JSON change tracking fires
    row.version += 1


# ---------- banner cache
@lru_cache(maxsize=32)
def _render_banner_cached(payload: str, mode: str) -> bytes:
    return render_banner(json.loads(payload), mode)


def banner_png(db: Session, row: City, force: bool = False, lighting_mode: str | None = None) -> bytes:
    mode = lighting_mode or resolve_mode(row.data.get("lighting"))
    render_version = banner_revision(row.version, mode)
    b = db.get(Banner, row.id)
    if b and b.version == render_version and not force:
        return b.png
    payload = json.dumps(city_dict(row), sort_keys=True, separators=(",", ":"))
    png = _render_banner_cached(payload, mode)
    if b:
        b.version, b.png = render_version, png
    else:
        db.add(Banner(city_id=row.id, version=render_version, png=png))
    db.commit()
    return png


def city_dict_from_demo() -> dict:
    c = demo_city()
    return {"username": "demo", "name": c["name"], "seed": c["seed"], "level": c["data"]["level"],
            "unlocked": c["data"]["unlocked"], "items": c["data"]["items"]}
