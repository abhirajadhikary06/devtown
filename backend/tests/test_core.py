import io
import os
from datetime import datetime, timezone

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api import services as svc
from app.api.routes import current_user
from app.banner.renderer import render_banner
from app.db import Base, SessionLocal, engine
from app.economy import rewards
from app.github.ingest import build_snapshot
from app.github.techs import detect
from app.main import app
from app.mapping.engine import analyse, val
from app.models import City, Ledger, User
from app.world import generator as gen
from app.world.catalogue import FREE


def test_generation_is_deterministic():
    plan = [{"building": b} for b in ["research_lab", "home", "db_tower", "town_hall"]]
    a = gen.place_starter(7, plan, gen.STARTER_CHUNKS, 0, 5)
    b = gen.place_starter(7, plan, gen.STARTER_CHUNKS, 0, 5)
    c = gen.place_starter(8, plan, gen.STARTER_CHUNKS, 0, 5)
    assert a == b and a[0] != c[0]
    assert gen.generate_chunk(7, 2, -3, False) == gen.generate_chunk(7, 2, -3, False)


def test_no_overlap_and_only_buildable_tiles():
    plan = [{"building": "cloud_district"}] * 4 + [{"building": "home"}] * 10
    items, _, _ = gen.place_starter(3, plan, gen.STARTER_CHUNKS, 0, 10)
    tm = gen.TileMap(3, gen.STARTER_CHUNKS)
    seen = set()
    from app.world.catalogue import footprint
    for it in items:
        for p in footprint(it["type"], it["x"], it["z"], it["rot"])[0]:
            assert p not in seen and tm.at(*p)[1] in (gen.GRASS, gen.SAND)
            seen.add(p)


def test_budgeted_build_preserves_existing_trees():
    tree = {"id": 7, "type": "tree", "x": 1, "z": 1, "rot": 0, "origin": "user"}
    items, spent, _ = gen.place_budgeted(3, [("home", 1)], gen.STARTER_CHUNKS, 100, 100, [tree])
    assert tree in items and spent["coins"] > 0


def test_banner_exact_size():
    items, _, _ = gen.place_starter(1, [{"building": "ai_lab"}, {"building": "home"}], gen.STARTER_CHUNKS, 0, 3)
    png = render_banner({"username": "t", "name": "T Town", "level": 3, "seed": 1, "unlocked": gen.STARTER_CHUNKS, "items": items})
    im = Image.open(io.BytesIO(png))
    assert im.size == (1734, 574) and im.format == "PNG"


def test_followers_do_not_dominate_and_unavailable_not_rewarded():
    snap = {"metrics": {"followers": {"v": 10**7, "s": "verified"}, "commits.signed": {"v": None, "s": "unavailable"}}}
    ents = {e["source"]: e for e in rewards.entitlements(snap)}
    assert ents["metric:followers"]["total"] <= 40
    assert val(snap, "commits.signed") == 0 and "metric:commits.signed" not in ents


def test_grants_are_idempotent_and_never_negative():
    ents = [{"source": "metric:commits.total", "resource": "energy", "total": 50}]
    assert rewards.grant_deltas(ents, {})[0]["amount"] == 50
    assert rewards.grant_deltas(ents, {("metric:commits.total", "energy"): 50}) == []
    ents[0]["total"] = 20  # lower total (e.g. data became unavailable) -> no penalty
    assert rewards.grant_deltas(ents, {("metric:commits.total", "energy"): 50}) == []


def test_reward_recalculation_reduces_old_grants_without_touching_spending(client):
    with SessionLocal() as db:
        user = db.query(User).filter_by(login="alice").one()
        db.add(Ledger(user_id=user.id, resource="coins", amount=400, source="welcome",
                      idem_key="grant:welcome:coins:400:legacy", reason="old rule"))
        db.add(Ledger(user_id=user.id, resource="coins", amount=-25, source="spend",
                      idem_key="spend:test", reason="test build"))
        db.commit()
        snapshot = {"metrics": {"commits.total": {"v": 500, "s": "verified"}}}
        svc.sync_grants(db, user.id, snapshot)
        db.commit()
        assert svc.balances(db, user.id)["coins"] < 630
        assert db.query(Ledger).filter_by(user_id=user.id, idem_key="spend:test").one().amount == -25
        assert db.query(Ledger).filter(Ledger.user_id == user.id, Ledger.idem_key.like("reconcile:%")).count() >= 1


def test_tech_detection_uses_evidence():
    out = detect([{"name": "r", "topics": ["PyTorch"], "root_files": ["Dockerfile"], "manifests": {"requirements.txt": "fastapi==0.1\nredis\n"}}])
    ids = {t["id"] for t in out}
    assert {"pytorch", "docker", "fastapi", "redis"} <= ids and "django" not in ids


def test_snapshot_parser_classifies_and_does_not_fabricate():
    profile = {"name": "A", "createdAt": "2020-01-01T00:00:00Z", "followers": {"totalCount": 3}, "organizations": {"totalCount": 1},
               "starredRepositories": {"totalCount": 9}, "contributionsCollection": {"contributionYears": [2024]},
               "prM": {"totalCount": 4}, "prC": {"totalCount": 1}, "prO": {"totalCount": 0}, "iO": {"totalCount": 2}, "iC": {"totalCount": 1},
               "issueComments": {"totalCount": 5}, "repositoryDiscussions": {"totalCount": 0}, "repositoryDiscussionComments": {"totalCount": 0},
               "forksOwned": {"totalCount": 2}, "ext": {"issueCount": 2},
               "repositoriesContributedTo": {"totalCount": 1, "nodes": [{"nameWithOwner": "o/p", "owner": {"login": "o"}, "stargazerCount": 5000, "viewerPermission": "READ", "isArchived": False}]},
               "repositories": {"totalCount": 1, "nodes": [{"name": "r", "isArchived": False, "isPrivate": False, "stargazerCount": 120, "forkCount": 3,
                                                            "watchers": {"totalCount": 4}, "createdAt": "2019-01-01T00:00:00Z", "pushedAt": "2026-01-01T00:00:00Z", "diskUsage": 100,
                                                            "homepageUrl": None, "hasWikiEnabled": True, "isSecurityPolicyEnabled": False, "licenseInfo": {"spdxId": "MIT"},
                                                            "languages": {"edges": [{"size": 900, "node": {"name": "Python"}}]}, "repositoryTopics": {"nodes": []},
                                                            "branches": {"totalCount": 3}, "tags": {"totalCount": 2}, "releases": {"totalCount": 2}, "latestRelease": {"tagName": "v1.2.0"},
                                                            "deployments": {"totalCount": 0}, "root": {"entries": [{"name": "README.md"}, {"name": "tests"}]},
                                                            "gh": {"entries": [{"name": "dependabot.yml"}]}, "wf": {"entries": [{"name": "ci.yml"}]}}]}}
    years = {2024: {"totalCommitContributions": 10, "totalPullRequestReviewContributions": 2, "restrictedContributionsCount": 1,
                    "contributionCalendar": {"weeks": [{"contributionDays": [{"date": "2024-03-01", "contributionCount": 2}, {"date": "2024-03-02", "contributionCount": 1}]}]},
                    "pullRequestContributionsByRepository": [{"repository": {"nameWithOwner": "o/p", "owner": {"login": "o"}}, "contributions": {"totalCount": 3}}],
                    "pullRequestReviewContributionsByRepository": []}}
    s = build_snapshot("a", profile, years, None, None, is_self=False, now=datetime(2026, 1, 2, tzinfo=timezone.utc))
    m = s["metrics"]
    assert m["commits.total"] == {"v": 10, "s": "verified"} and m["repos.with_tests"]["v"] == 1 and m["repos.dependabot"]["v"] == 1
    assert m["oss.maintained"]["s"] == "unavailable" and m["pushes.recent"]["s"] == "unavailable" and m["commits.signed"]["v"] is None
    assert m["prs.opened_any"]["v"] == 5 and m["oss.max_repeat"]["v"] == 3 and s["languages"] == {"Python": 900}
    assert analyse(s)["plan"]


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with SessionLocal() as db:
        u = User(github_id=1, login="alice", name="Alice")
        db.add(u); db.flush()
        snap = {"metrics": {"commits.total": {"v": 500, "s": "verified"}}, "languages": {"Python": 10}, "technologies": []}
        an = analyse(snap); seed = gen.seed_from("alice")
        db.add(City(user_id=u.id, username="alice", name="Alice Town", seed=seed, gen_version=1, version=1, data=svc.new_city_data(snap, an, seed)))
        svc.sync_grants(db, u.id, snap)
        db.commit(); uid = u.id
    app.dependency_overrides[current_user] = lambda: SessionLocal().get(User, uid)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_public_banner_no_auth_and_cache_headers(client):
    r = client.get("/api/banners/alice.png")
    assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).size == (1734, 574)
    assert "immutable" not in r.headers["cache-control"]
    v = client.get("/api/banners/alice.png?v=1")
    assert "immutable" in v.headers["cache-control"]
    assert client.get("/api/banners/demo.png").status_code == 200
    assert client.get("/api/banners/nobody.png").status_code == 404


def test_build_charges_resources_blocks_collisions_and_bumps_version(client):
    city = client.get("/api/cities/alice").json()
    v0 = city["version"]
    from app.world.generator import TileMap, placement_error
    tm = TileMap(city["seed"], city["unlocked"])
    spot = next((x, z) for x in range(-14, 30) for z in range(-14, 30) if placement_error(tm, city["items"], "home", x, z, 0) is None)
    r = client.post("/api/me/city/items", json={"type": "home", "x": spot[0], "z": spot[1], "rot": 0})
    assert r.status_code == 200 and r.json()["version"] == v0 + 1
    assert client.post("/api/me/city/items", json={"type": "home", "x": spot[0], "z": spot[1], "rot": 0}).status_code == 409
    assert client.post("/api/me/city/items", json={"type": "ai_lab", "x": spot[0], "z": spot[1], "rot": 0}).status_code == 409  # locked
    assert client.get("/api/cities/alice").json()["version"] == v0 + 1
    banner = client.get("/api/me/banner").json()
    assert banner["markdown"].startswith("[![My DevTown](")
    assert banner["markdown"].endswith("/@alice)")
    assert "width=" not in banner["markdown"] and "height=" not in banner["markdown"]


def test_auto_build_replaces_layout_and_uses_available_resources(client):
    before = client.get("/api/cities/alice").json()
    result = client.post("/api/me/city/auto-build")
    assert result.status_code == 200
    after = client.get("/api/cities/alice").json()
    assert after["version"] == before["version"] + 1
    assert all(item["origin"] == "auto" or item["type"] in FREE for item in after["items"])
    assert result.json()["balances"]["coins"] <= 400
    assert result.json()["balances"]["materials"] <= 200


def test_expansion_requires_level_and_resources(client):
    r = client.post("/api/me/city/expand", json={"cx": 2, "cz": 0})
    assert r.status_code in (200, 409)
    assert client.post("/api/me/city/expand", json={"cx": 9, "cz": 9}).status_code == 409
