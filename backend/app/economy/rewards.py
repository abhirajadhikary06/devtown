"""Resource economy. Entitlements are saturating functions of lifetime totals (so raw volume cannot run away),
granted to an append-only ledger as idempotent deltas. Activity never decays; inactivity is never penalized."""
import math

from ..mapping.engine import val

# (metric, resource, cap, scale): entitlement = cap * (1 - exp(-value/scale))
RULES = [
    ("commits.total", "energy", 400, 1500), ("days.active", "energy", 300, 400), ("streak.longest", "energy", 60, 60),
    ("weeks.active", "energy", 120, 150), ("pushes.recent", "energy", 20, 100),
    # Small, gradual construction income from ordinary profile activity.
    ("commits.total", "coins", 180, 1000), ("days.active", "coins", 120, 250),
    ("prs.merged", "coins", 200, 50),
    ("repos.owned", "materials", 300, 20), ("prs.merged", "materials", 400, 150), ("releases.total", "materials", 200, 30),
    ("repos.with_ci", "materials", 80, 10), ("repos.large", "materials", 100, 5), ("repos.with_tests", "materials", 60, 8),
    ("external.prs_merged", "reputation", 500, 50), ("external.repos", "reputation", 200, 15),
    ("external.orgs", "reputation", 120, 6), ("stars.received", "reputation", 300, 500),
    ("reviews.given", "reputation", 120, 60), ("followers", "reputation", 40, 2000),  # followers: tiny cap by design
]
# achievements -> coins (one-off, each counted once)
ACHIEVEMENTS = [
    ("first_commit", "commits.total", 1, 50), ("commits_100", "commits.total", 100, 100), ("commits_1000", "commits.total", 1000, 250),
    ("first_pr_merged", "prs.merged", 1, 80), ("prs_50", "prs.merged", 50, 200), ("first_external", "external.prs_merged", 1, 150),
    ("external_10", "external.prs_merged", 10, 300), ("first_release", "releases.total", 1, 120), ("releases_10", "releases.total", 10, 200),
    ("first_review", "reviews.given", 1, 60), ("streak_30", "streak.longest", 30, 150), ("stars_100", "stars.received", 100, 250),
    ("repos_10", "repos.owned", 10, 100), ("history_5y", "history.years", 5, 150), ("maintainer", "oss.maintained", 1, 300),
]


def entitlements(snap) -> list[dict]:
    out = []
    for metric, res, cap, scale in RULES:
        v = val(snap, metric)
        if v > 0:
            out.append({"source": f"metric:{metric}", "resource": res, "total": int(cap * (1 - math.exp(-v / scale)))})
    for aid, metric, thr, coins in ACHIEVEMENTS:
        if val(snap, metric) >= thr:
            out.append({"source": f"achievement:{aid}", "resource": "coins", "total": coins})
    # every resource needs a modest baseline so a brand-new city can build immediately
    # Enough for several starter structures without making costs meaningless.
    out.append({"source": "welcome", "resource": "coins", "total": 400})
    out.append({"source": "welcome", "resource": "materials", "total": 200})
    return out


def grant_deltas(ents: list[dict], granted: dict[tuple[str, str], int]) -> list[dict]:
    """granted: {(source, resource): already granted}. Returns ledger rows to insert (never negative)."""
    rows = []
    for e in ents:
        d = e["total"] - granted.get((e["source"], e["resource"]), 0)
        if d > 0:
            rows.append({"source": e["source"], "resource": e["resource"], "amount": d,
                         "idem_key": f"grant:{e['source']}:{e['resource']}:{e['total']}", "reason": "activity sync"})
    return rows


def expansion_cost(n_unlocked: int) -> dict:
    n = max(1, n_unlocked - 8)
    return {"coins": 100 * n, "materials": 60 * n, "min_level": 1 + (n - 1) * 2}
