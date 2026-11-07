import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import security
from ..banner.renderer import render_banner
from ..config import settings
from ..db import SessionLocal, get_db
from ..github.client import GitHubClient
from ..github.ingest import collect_snapshot
from ..lighting import DEFAULT_PREFERENCES, MODES, banner_revision, resolve_mode
from ..mapping.engine import analyse
from ..models import City, Snapshot, User
from ..world import generator as gen
from ..world.catalogue import BUILDINGS
from . import services as svc
from . import showcase as sc

router = APIRouter(prefix="/api")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    u = db.get(User, request.session.get("uid")) if request.session.get("uid") else None
    if not u:
        raise HTTPException(401, "Sign in with GitHub first")
    return u


def my_city(user: User, db: Session) -> City:
    c = db.scalar(select(City).where(City.user_id == user.id))
    if not c:
        raise HTTPException(404, "Analyze your GitHub profile first")
    return c


@router.get("/health")
def health():
    return {"ok": True, "generation_version": gen.GEN_VERSION}


# ---------- auth (scope: read:user only; public data)
@router.get("/auth/github/login")
def login(request: Request, response: Response):
    if not settings.github_client_id:
        raise HTTPException(503, "GitHub OAuth is not configured on this server")
    state = secrets.token_urlsafe(16)
    request.session["state"] = state
    response.headers["Cache-Control"] = "no-store"
    return RedirectResponse("https://github.com/login/oauth/authorize?" + urlencode(
        {"client_id": settings.github_client_id, "scope": "read:user", "state": state}),
        headers={"Cache-Control": "no-store"})


@router.get("/auth/github/callback")
async def callback(request: Request, code: str, state: str, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    if state != request.session.pop("state", None):
        raise HTTPException(400, "Invalid OAuth state")
    async with httpx.AsyncClient(timeout=20) as h:
        t = (await h.post("https://github.com/login/oauth/access_token", headers={"Accept": "application/json"},
                          data={"client_id": settings.github_client_id, "client_secret": settings.github_client_secret, "code": code})).json()
        tok = t.get("access_token")
        if not tok:
            raise HTTPException(400, "GitHub did not return a token")
        me = (await h.get("https://api.github.com/user", headers={"Authorization": f"Bearer {tok}"})).json()
    u = db.scalar(select(User).where(User.github_id == me["id"])) or User(github_id=me["id"], login=me["login"])
    u.login, u.name, u.avatar_url, u.token_enc = me["login"], me.get("name"), me.get("avatar_url"), security.encrypt(tok)
    db.add(u)
    db.commit()
    request.session["uid"] = u.id
    return RedirectResponse(settings.frontend_url + "/studio", headers={"Cache-Control": "no-store"})


@router.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.scalar(select(City).where(City.user_id == user.id))
    return {"login": user.login, "name": user.name, "avatar": user.avatar_url, "has_city": bool(c), "balances": svc.balances(db, user.id)}


# ---------- analysis
class SyncIn(BaseModel):
    auto_build: bool = True


@router.post("/me/sync")
async def sync(body: SyncIn = SyncIn(), user: User = Depends(current_user), db: Session = Depends(get_db)):
    client = GitHubClient(security.decrypt(user.token_enc))
    try:
        snap = await collect_snapshot(client, user.login, is_self=True, force=True)
    except Exception as e:  # network / permissions: report, never fabricate
        raise HTTPException(502, f"Could not read GitHub data: {type(e).__name__}")
    finally:
        await client.close()
    an = analyse(snap)
    db.add(Snapshot(user_id=user.id, data=snap, analysis=an))
    granted = svc.sync_grants(db, user.id, snap)
    row = db.scalar(select(City).where(City.user_id == user.id))
    if not row:
        seed = gen.seed_from(user.login)
        row = City(user_id=user.id, username=user.login, name=f"{user.name or user.login}'s DevTown"[:80], seed=seed,
                   gen_version=gen.GEN_VERSION, version=1, data=svc.new_city_data(snap, an, seed, body.auto_build))
        db.add(row)
    else:  # never regenerate over user edits; only widen unlocks and level
        d = dict(row.data)
        d["unlocks"], d["level"] = sorted(set(d["unlocks"]) | set(an["unlocks"])), max(d.get("level", 1), an["activity"]["level"])
        row.data = d
        row.version += 1
    db.commit()
    return {"granted_entries": granted, "level": row.data["level"], "balances": svc.balances(db, user.id),
            "auto_build": row.data.get("auto_build", True), "built_structures": len(row.data.get("items", [])),
            "deferred_buildings": len(row.data.get("deferred", [])), "analysis": _public(an)}


def _public(an):
    return {k: an[k] for k in ("identity", "activity", "community", "data_quality")} | {"plan": an["plan"][:40], "unlocks": an["unlocks"]}


@router.get("/me/profile")
def profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.scalar(select(Snapshot).where(Snapshot.user_id == user.id).order_by(Snapshot.id.desc()))
    # Apply updated, saturating reward rules to cached evidence when users return.
    # This tops up existing accounts without requiring another GitHub request.
    if s and svc.sync_grants(db, user.id, s.data):
        db.commit()
    return {"balances": svc.balances(db, user.id), "analysis": _public(s.analysis) if s else None,
            "fetched_at": s.data["fetched_at"] if s else None}


class LightingIn(BaseModel):
    mode: str = "auto"
    timezone: str = "UTC"
    scheduled_auto_build: bool = False


@router.patch("/me/lighting")
def update_lighting(b: LightingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if b.mode not in MODES:
        raise HTTPException(422, "Lighting mode must be auto, day, dusk, or night")
    row = my_city(user, db)
    data = dict(row.data)
    lighting = {"mode": "auto" if b.scheduled_auto_build else b.mode, "timezone": b.timezone[:80],
                "scheduled_auto_build": b.scheduled_auto_build}
    if data.get("lighting") == lighting:
        return lighting
    data["lighting"] = lighting
    row.data = data
    row.version += 1
    db.commit()
    return data["lighting"]


@router.get("/me/lighting")
def get_lighting(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return my_city(user, db).data.get("lighting", dict(DEFAULT_PREFERENCES))


# ---------- cities (public read)
@router.get("/demo/profile")
def demo_profile():
    return {"analysis": _public(svc.demo_city()["analysis"]), "balances": {"energy": 0, "coins": 0, "materials": 0, "reputation": 0}}


@router.get("/catalogue")
def catalogue(request: Request, db: Session = Depends(get_db)):
    uid = request.session.get("uid")
    row = db.scalar(select(City).where(City.user_id == uid)) if uid else None
    return svc.catalogue_payload(row.data["unlocks"] if row else svc.demo_city()["data"]["unlocks"])


def _load(username: str, db: Session) -> dict:
    if username.lower() == "demo":
        c = svc.demo_city()
        return {**c, **c["data"]}
    row = db.scalar(select(City).where(City.username.ilike(username)))
    if not row:
        raise HTTPException(404, "No DevTown city for this user yet")
    return svc.city_dict(row)


@router.get("/cities/{username}")
async def city(username: str, db: Session = Depends(get_db)):
    if username.lower() == "demo":
        return svc.view_payload(_load(username, db))
    row = db.scalar(select(City).where(City.username.ilike(username)))
    if not row:
        # Create and cache a public town on first lookup when a GitHub token is
        # available from a connected account or server seed configuration.
        # End the initial read transaction first so a concurrent showcase seed
        # committed during GitHub ingestion is visible to this request.
        db.rollback()
        try:
            await sc.seed_city(db, username, public_lookup=True)
        except sc.SeedError as e:
            if "did not return an id" in str(e):
                raise HTTPException(404, f"Could not find a public GitHub profile for @{username}")
            raise HTTPException(503, str(e))
        except Exception as e:
            raise HTTPException(502, f"Could not load @{username}: {type(e).__name__}")
        db.expire_all()
        row = db.scalar(select(City).where(City.username.ilike(username)))
        if not row:
            # A showcase background seed can race this request. Re-run the
            # idempotent upsert once after refreshing the session state.
            db.rollback()
            try:
                await sc.seed_city(db, username, public_lookup=True)
            except Exception as e:
                raise HTTPException(502, f"Could not load @{username}: {type(e).__name__}")
            db.expire_all()
            row = db.scalar(select(City).where(City.username.ilike(username)))
        if not row:
            raise HTTPException(503, f"Town for @{username} is still being prepared. Refresh this page shortly.")
    return svc.view_payload(svc.city_dict(row))


# ---------- edits
class PlaceIn(BaseModel):
    type: str
    x: int
    z: int
    rot: int = 0


class MoveIn(BaseModel):
    x: int
    z: int
    rot: int = 0


class ExpandIn(BaseModel):
    cx: int
    cz: int


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


def _after_edit(bg: BackgroundTasks, row: City):
    bg.add_task(_rerender, row.id)


def _rerender(city_id: int):
    with SessionLocal() as db:
        row = db.get(City, city_id)
        if row:
            svc.banner_png(db, row)


def _edit(fn, db, row, bg):
    try:
        r = fn()
    except svc.EditError as e:
        db.rollback()
        raise HTTPException(409, str(e))
    db.commit()
    _after_edit(bg, row)
    return r


@router.post("/me/city/items")
def add_item(b: PlaceIn, bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = my_city(user, db)
    item = _edit(lambda: svc.place(db, row, user.id, b.type, b.x, b.z, b.rot), db, row, bg)
    return {"item": item, "version": row.version, "balances": svc.balances(db, user.id)}


@router.patch("/me/city/items/{item_id}")
def move_item(item_id: int, b: MoveIn, bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = my_city(user, db)
    _edit(lambda: svc.move(db, row, item_id, b.x, b.z, b.rot), db, row, bg)
    return {"version": row.version}


@router.delete("/me/city/items/{item_id}")
def del_item(item_id: int, bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = my_city(user, db)
    _edit(lambda: svc.remove(db, row, user.id, item_id), db, row, bg)
    return {"version": row.version, "balances": svc.balances(db, user.id)}


@router.post("/me/city/expand")
def expand(b: ExpandIn, bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = my_city(user, db)
    _edit(lambda: svc.expand(db, row, user.id, b.cx, b.cz), db, row, bg)
    from ..economy.rewards import expansion_cost
    return {"version": row.version, "balances": svc.balances(db, user.id), "next_cost": expansion_cost(len(row.data["unlocked"]))}


@router.get("/me/city/expansion")
def expansion(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from ..economy.rewards import expansion_cost
    return expansion_cost(len(my_city(user, db).data["unlocked"]))


@router.post("/me/city/auto-build")
def auto_build_city(bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = my_city(user, db)
    s = db.scalar(select(Snapshot).where(Snapshot.user_id == user.id).order_by(Snapshot.id.desc()))
    plan = s.analysis["plan"] if s else []
    result = svc.auto_build(db, row, user.id, plan)
    db.commit()
    _after_edit(bg, row)
    return {"version": row.version, **result}


@router.patch("/me/city")
def rename(b: RenameIn, bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = my_city(user, db)
    row.name = b.name.strip()
    row.version += 1
    db.commit()
    _after_edit(bg, row)
    return {"name": row.name, "version": row.version}


# ---------- banner
@router.get("/banners/{username}.png")
async def banner(username: str, request: Request, v: int | None = None, db: Session = Depends(get_db)):
    if username.lower() == "demo":
        mode = request.query_params.get("mode", "day")
        if mode not in ("day", "dusk", "night"):
            mode = "day"
        png = await run_in_threadpool(lambda: render_banner(svc.city_dict_from_demo(), mode))
        ver = banner_revision(1, mode)
    else:
        row = db.scalar(select(City).where(City.username.ilike(username)))
        if not row and username.lower() == sc.HOMEPAGE_PROFILE:
            try:
                await sc.seed_city(db, sc.HOMEPAGE_PROFILE, public_lookup=True)
                row = db.scalar(select(City).where(City.username.ilike(sc.HOMEPAGE_PROFILE)))
            except Exception as e:
                print(f"[homepage] could not seed featured profile: {type(e).__name__}: {e}", flush=True)
        if not row:  # keep README embeds from showing a broken image
            png = await run_in_threadpool(lambda: render_banner({"username": username, "name": "DevTown", "level": 1, "seed": gen.seed_from(username),
                                                                 "unlocked": gen.STARTER_CHUNKS, "items": []}))
            return Response(png, media_type="image/png", status_code=404, headers={"Cache-Control": "public, max-age=60"})
        requested_mode = request.query_params.get("mode")
        mode = requested_mode if requested_mode in ("day", "dusk", "night") else resolve_mode(row.data.get("lighting"))
        png = await run_in_threadpool(svc.banner_png, db, row, False, mode)
        ver = banner_revision(row.version, mode)
    legacy_version = v == (1 if username.lower() == "demo" else row.version)
    immutable = v == ver or (legacy_version and "mode" not in request.query_params)
    cache = "public, max-age=31536000, immutable" if immutable else "public, max-age=300, stale-while-revalidate=86400"
    return Response(png, media_type="image/png", headers={"Cache-Control": cache, "ETag": f'"{ver}"',
                                                          "Content-Disposition": f'inline; filename="devtown-{username}.png"'})


@router.get("/me/banner")
def banner_info(user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = my_city(user, db)
    base = settings.public_base_url.rstrip("/")
    preference = row.data.get("lighting", dict(DEFAULT_PREFERENCES))
    mode = resolve_mode(preference)
    revision = banner_revision(row.version, mode)
    url = f"{base}/api/banners/{user.login}.png"
    versioned_url = f"{url}?mode={mode}&v={revision}"
    markdown = f"[![My DevTown]({versioned_url})]({base}/@{user.login})"
    return {"version": revision, "image_url": url, "versioned_url": versioned_url, "profile_url": f"{base}/@{user.login}",
            "markdown": markdown, "width": 1734, "height": 574, "display_width": 514, "display_height": 170,
            "lighting": preference, "resolved_mode": mode}


@router.post("/me/banner/regenerate")
async def banner_regen(user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = my_city(user, db)
    await run_in_threadpool(svc.banner_png, db, row, True)
    return banner_info(user, db)



# ---------- showcase (rotating cities generated from public GitHub profiles)
@router.get("/showcase")
def showcase_status(db: Session = Depends(get_db)):
    return sc.status(db)


@router.get("/world")
def community_world(db: Session = Depends(get_db)):
    """Compact public map data for towns owned by authenticated platform users."""
    rows = db.execute(select(City).order_by(City.username)).scalars().all()
    towns = []
    total_land = total_structures = 0
    for city_row in rows:
        data = city_row.data
        chunks = data.get("unlocked") or [[0, 0]]
        min_cx = min(c[0] for c in chunks); max_cx = max(c[0] for c in chunks)
        min_cz = min(c[1] for c in chunks); max_cz = max(c[1] for c in chunks)
        origin_x, origin_z = min_cx * gen.CHUNK, min_cz * gen.CHUNK
        width, depth = (max_cx - min_cx + 1) * gen.CHUNK, (max_cz - min_cz + 1) * gen.CHUNK
        buildings = []
        for item in data.get("items", []):
            b = BUILDINGS.get(item["type"])
            if not b:
                continue
            w, d = (b["d"], b["w"]) if item.get("rot", 0) % 2 else (b["w"], b["d"])
            buildings.append({"x": item["x"] - origin_x, "z": item["z"] - origin_z,
                              "w": w, "d": d, "color": b["color"]})
        total_land += len(chunks); total_structures += len(buildings)
        towns.append({"username": city_row.username, "name": city_row.name, "level": data.get("level", 1),
                      "land_count": len(chunks), "structures": len(buildings), "width": width, "depth": depth,
                      "buildings": buildings, "city": svc.view_payload(svc.city_dict(city_row))})
    return {"town_count": len(towns), "land_count": total_land, "structure_count": total_structures, "towns": towns}


async def _seed_all(force: bool):
    for login in sc.SHOWCASE:
        with SessionLocal() as db:
            try:
                await sc.seed_city(db, login, force=force, public_lookup=True)
            except Exception as e:  # one failure must not stop the rotation
                print(f"[showcase] seed {login} failed: {type(e).__name__}: {e}", flush=True)


@router.post("/showcase/seed")
def showcase_seed(bg: BackgroundTasks, force: bool = False):
    bg.add_task(_seed_all, force)
    return {"started": True, "usernames": sc.SHOWCASE}
