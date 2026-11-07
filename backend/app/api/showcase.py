"""Rotating showcase: generate DevTown cities from real public GitHub profiles.

These users never authenticate here; we read their public data with a token
(`GITHUB_SEED_TOKEN`, or a stored login token as fallback) and store a "ghost"
User + City so `/api/cities/{username}` and the `/showcase` page can render them.
Reuses the existing tables, so no migration is needed.
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import security
from ..config import settings
from ..github.client import GitHubClient
from ..github.ingest import collect_snapshot
from ..mapping.engine import analyse
from ..models import City, User
from ..world import generator as gen
from . import services as svc

# Homepage profile, followed by the rotating showcase list.
HOMEPAGE_PROFILE = "torvalds"
SHOWCASE = [HOMEPAGE_PROFILE, "charliermarsh", "karpathy", "peppy", "sindresorhus", "antfu", "gaearon"]


class SeedError(Exception):
    pass


def seed_token(db: Session) -> str | None:
    """Token used to read public profiles: explicit seed token, else any stored login token."""
    if settings.github_seed_token:
        return settings.github_seed_token
    row = db.scalar(select(User).where(User.token_enc.is_not(None)))
    return security.decrypt(row.token_enc) if row else None


def has_seed_token(db: Session) -> bool:
    return bool(settings.github_seed_token) or db.scalar(select(User).where(User.token_enc.is_not(None))) is not None


async def seed_city(db: Session, login: str, force: bool = False, public_lookup: bool = False) -> dict:
    """Ingest one public profile and upsert its city. Idempotent unless `force`."""
    login = login.lower()
    token = seed_token(db)
    if not token and not public_lookup:
        raise SeedError("No GitHub token for seeding: set GITHUB_SEED_TOKEN or log in once.")

    existing = db.scalar(select(City).where(City.username.ilike(login)))
    if existing and not force:
        return {"login": login, "status": "exists", "name": existing.name, "level": existing.data.get("level", 1)}

    client = GitHubClient(token=token)
    try:
        snap = await collect_snapshot(client, login, is_self=False)
    finally:
        await client.close()

    an = analyse(snap)
    prof = snap.get("profile") or {}

    # upsert ghost user (never authenticated; no token stored)
    u = db.scalar(select(User).where(User.login.ilike(login)))
    if not u and prof.get("databaseId"):
        u = db.scalar(select(User).where(User.github_id == prof["databaseId"]))
    if not u:
        gh_id = prof.get("databaseId")
        if not gh_id:
            raise SeedError(f"GitHub did not return an id for {login}")
        u = User(github_id=gh_id, login=login, name=prof.get("name"), avatar_url=prof.get("avatar"))
        db.add(u)
        db.flush()
    else:
        u.name = prof.get("name") or u.name
        u.avatar_url = prof.get("avatar") or u.avatar_url

    seed = gen.seed_from(login)
    if existing:
        # widen unlocks / level only; never overwrite generated starter placement
        d = dict(existing.data)
        d["unlocks"] = sorted(set(d["unlocks"]) | set(an["unlocks"]))
        d["level"] = max(d.get("level", 1), an["activity"]["level"])
        existing.data = d
        existing.version += 1
    else:
        existing = City(user_id=u.id, username=login, name=f"{prof.get('name') or login}'s DevTown"[:80],
                        seed=seed, gen_version=gen.GEN_VERSION, version=1, data=svc.new_city_data(snap, an, seed))
        db.add(existing)
    try:
        db.commit()
    except IntegrityError:  # rare race if another seed task created it first
        db.rollback()
        existing = db.scalar(select(City).where(City.username.ilike(login)))
    return {"login": login, "status": "seeded", "name": existing.name, "level": existing.data.get("level", 1)}


def status(db: Session) -> dict:
    cities = []
    for login in SHOWCASE:
        row = db.scalar(select(City).where(City.username.ilike(login)))
        cities.append({"login": login, "seeded": row is not None,
                        "name": row.name if row else None, "level": row.data.get("level", 1) if row else None})
    return {"usernames": SHOWCASE, "cities": cities, "seed_token_available": has_seed_token(db)}
