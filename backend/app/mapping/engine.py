"""GitHub snapshot -> city. Four cooperating engines: identity, activity, community, plan (feeds world gen)."""
import math

from ..world.catalogue import BASE_UNLOCKS, BUILDINGS

LANG_MAP = {"Python": "research_lab", "Jupyter Notebook": "research_lab", "JavaScript": "commercial_tower",
            "TypeScript": "commercial_tower", "Rust": "industrial_complex", "Go": "logistics_hub", "Java": "enterprise_hq",
            "Kotlin": "mobile_campus", "Swift": "mobile_campus", "C": "factory", "C++": "factory", "SQL": "db_tower",
            "PLpgSQL": "db_tower", "TSQL": "db_tower", "Scala": "bigdata_facility", "HTML": "design_studio",
            "CSS": "design_studio", "SCSS": "design_studio", "R": "stats_centre", "PHP": "web_office",
            "Shell": "utility_station", "Dart": "xplat_centre"}


def val(snap, key, default=0):
    m = snap["metrics"].get(key)
    return default if not m or m["s"] == "unavailable" or m["v"] is None else m["v"]


def identity(snap):
    langs = {k: v for k, v in snap.get("languages", {}).items() if v > 0}
    total = sum(langs.values()) or 1
    shares = {k: v / total for k, v in sorted(langs.items(), key=lambda kv: -kv[1])}
    names = list(shares)
    dominant = [n for i, n in enumerate(names[:2]) if i == 0 or shares[n] >= 0.25]
    secondary = [n for n in names if n not in dominant and shares[n] >= 0.04][:6]
    diversity = sum(1 for s in shares.values() if s >= 0.05)
    cat_count: dict[str, int] = {}
    for t in snap.get("technologies", []):
        cat_count[t["category"]] = cat_count.get(t["category"], 0) + len(t["repos"])
    spec = max(cat_count, key=cat_count.get) if cat_count else None
    return {"dominant": dominant, "secondary": secondary, "shares": {k: round(v, 4) for k, v in list(shares.items())[:12]},
            "diversity": diversity, "mixed_district": diversity >= 4, "specialization": spec,
            "tech_facilities": [{"tech": t["name"], "facility": t["facility"], "status": t["status"], "evidence": t["evidence"]}
                                for t in snap.get("technologies", [])]}


def _sat(x, k):  # smooth saturation 0..1
    return 1 - math.exp(-max(x, 0) / k)


def activity(snap):
    v = lambda k: val(snap, k)
    score = (25 * min(1, math.log10(1 + v("commits.total")) / 4) + 15 * min(1, v("days.active") / 500)
             + 15 * min(1, math.log10(1 + v("prs.merged")) / 3) + 15 * min(1, v("external.repos") / 25)
             + 10 * min(1, v("repos.owned") / 40) + 10 * min(1, math.log10(1 + v("stars.received")) / 3.5)
             + 5 * min(1, v("releases.total") / 30) + 5 * min(1, v("history.years") / 8))
    level = 1 + int(score / 100 * 19)  # followers deliberately excluded
    return {"score": round(score, 1), "level": level, "streetlights": min(60, v("weeks.active") // 4),
            "milestone_markers": min(6, 1 + v("tags.total") // 5) if v("tags.total") else 0}


def community(snap):
    v = lambda k: val(snap, k)
    residents = v("contributors.external") + 2 * v("orgs.member") + v("external.repos") // 2
    return {"population": 10 + min(400, residents * 6), "residents_basis": residents,
            "reputation_basis": {"external_prs": v("external.prs_merged"), "stars": v("stars.received")}}


# building, metric, min, per, max copies, priority (lower first). copies = 1 + (v-min)//per, capped.
RULES = [
    ("starter_building", "commits.total", 1, 1, 1, 0),
    ("permit_office", "prs.opened_any", 1, 1, 1, 20), ("project_hall", "prs.merged", 1, 50, 3, 12),
    ("archive_office", "prs.closed", 1, 1, 1, 60), ("inspection_centre", "reviews.given", 1, 40, 2, 25),
    ("service_office", "issues.opened", 1, 1, 1, 45), ("repair_depot", "issues.closed", 1, 30, 2, 50),
    ("noticeboard", "issues.comments", 1, 100, 4, 70), ("town_hall", "discussions.started", 1, 1, 1, 40),
    ("community_centre", "discussions.comments", 1, 1, 1, 55),
    ("bridge_landmark", "external.repos", 1, 1, 1, 8), ("international_district", "external.orgs", 3, 5, 3, 10),
    ("oss_landmark", "external.popular", 1, 3, 3, 9), ("oss_community_centre", "oss.max_repeat", 5, 1, 1, 18),
    ("oss_admin", "oss.maintained", 1, 1, 1, 7), ("consultancy", "external.reviews", 1, 1, 1, 26),
    ("satellite_settlement", "repos.forks_owned", 1, 5, 3, 65), ("railway_station", "external.repos", 5, 10, 2, 30),
    ("neighbourhood_hub", "repos.owned", 3, 8, 4, 14), ("dev_complex", "repos.large", 1, 3, 3, 16),
    ("heritage_structure", "repos.oldest_years", 3, 100, 1, 42), ("historic_hall", "repos.archived", 1, 1, 1, 66),
    ("info_centre", "repos.with_readme", 1, 15, 2, 35), ("public_access_office", "repos.licensed", 1, 1, 1, 48),
    ("tourism_office", "stars.received", 5, 100, 2, 33), ("famous_landmark", "repos.popular", 1, 3, 3, 6),
    ("community_monument", "stars.received", 500, 1000, 1, 5), ("visitor_plaza", "followers", 100, 1000, 1, 80),
    ("grand_opening_plaza", "releases.total", 1, 1, 1, 15), ("milestone_monument", "releases.total", 5, 15, 3, 22),
    ("broadcast_tower", "repos.pages", 1, 1, 1, 38), ("airport_terminal", "deployments.total", 1, 50, 2, 28),
    ("power_plant", "repos.with_ci", 1, 5, 3, 24), ("control_tower", "repos.scheduled_ci", 1, 1, 1, 34),
    ("heritage_landmark", "history.years", 3, 3, 3, 36), ("logistics_depot", "pushes.recent", 1, 40, 3, 32),
    ("library", "repos.with_docs", 1, 1, 1, 44), ("knowledge_archive", "repos.with_wiki", 1, 1, 1, 58),
    ("safety_infra", "repos.with_tests", 1, 5, 3, 27), ("qa_centre", "repos.with_tests", 3, 1, 1, 31),
    ("security_station", "repos.codeql", 1, 1, 1, 37), ("maintenance_facility", "repos.dependabot", 1, 1, 1, 46),
    ("emergency_centre", "repos.security_policy", 1, 1, 1, 52), ("services_centre", "repos.coc", 1, 1, 1, 62),
    ("kiosk", "repos.issue_templates", 1, 1, 1, 72), ("docs_office", "repos.pr_templates", 1, 1, 1, 74),
    ("trust_monument", "commits.signed", 1, 1, 1, 54), ("business_district", "orgs.member", 1, 3, 3, 21),
    ("apartment", "contributors.external", 3, 8, 6, 47),
]

METRIC_LABELS = {"commits.total": "a commit", "prs.opened_any": "a pull request", "prs.merged": "a merged pull request",
                 "prs.closed": "a closed pull request", "reviews.given": "a review", "issues.opened": "an opened issue",
                 "issues.closed": "a closed issue", "issues.comments": "an issue comment", "discussions.started": "a discussion",
                 "discussions.comments": "a discussion comment", "external.repos": "a contribution to another repository",
                 "external.orgs": "3 organizations", "external.popular": "a contribution to a popular repository",
                 "oss.max_repeat": "5 contributions to one external project", "oss.maintained": "maintainer access to a repository",
                 "external.reviews": "a review in another repository", "repos.forks_owned": "a forked repository",
                 "repos.owned": "3 public repositories", "repos.large": "a repository with at least 20 MB of code",
                 "repos.oldest_years": "a repository at least 3 years old", "repos.archived": "an archived repository",
                 "repos.with_readme": "a repository README", "repos.licensed": "a repository license", "stars.received": "5 stars",
                 "repos.popular": "a repository with 100 stars", "orgs.member": "organization membership", "releases.total": "a release",
                 "repos.pages": "a GitHub Pages repository", "deployments.total": "a deployment", "repos.with_ci": "a CI workflow",
                 "repos.scheduled_ci": "a scheduled CI workflow", "history.years": "3 contribution years",
                 "pushes.recent": "a recent public push", "repos.with_docs": "repository documentation", "repos.with_wiki": "an enabled wiki",
                 "repos.with_tests": "tests in a repository", "repos.codeql": "a CodeQL workflow", "repos.dependabot": "Dependabot configuration",
                 "repos.security_policy": "a security policy", "repos.coc": "a code of conduct", "repos.issue_templates": "an issue template",
                 "repos.pr_templates": "a pull request template", "commits.signed": "a signed commit", "contributors.external": "3 external contributors"}


def lock_reason(building: str) -> str:
    for bid, key, minimum, *_ in RULES:
        if bid == building:
            return f"Unlocks with {METRIC_LABELS.get(key, key)} ({key} ≥ {minimum})."
    if building in {b for b in LANG_MAP.values()}:
        return "Unlocks when this language appears in your public repository code."
    return "Unlocks when this technology is detected in a public repository."


def build_plan(snap, ident=None, act=None, com=None):
    ident = ident or identity(snap)
    act = act or activity(snap)
    com = com or community(snap)
    entries, unlocks = [], set(BASE_UNLOCKS)

    def add(b, prio, why, n=1):
        unlocks.add(b)
        entries.extend([{"building": b, "priority": prio, "reason": why}] * n)
    # A starter town has a recognisable neighbourhood even when GitHub hides
    # most activity or the account is new. These are always buildable basics.
    add("workshop", 2, "starter workshop")
    add("utility_station", 3, "starter utility")
    for i, lang in enumerate(ident["dominant"]):
        add(LANG_MAP.get(lang, "workshop"), 1 + i, f"dominant language: {lang}", 2 if i == 0 else 1)
    for lang in ident["secondary"]:
        if lang in LANG_MAP:
            add(LANG_MAP[lang], 56, f"secondary language: {lang}")
    if ident["mixed_district"]:
        add("mixed_plaza", 11, f"{ident['diversity']} languages with >=5% share")
    for t in ident["tech_facilities"]:
        add(t["facility"], 13, f"{t['tech']} detected ({', '.join(t['evidence'])})")
    for b, key, mn, per, mx, prio in RULES:
        v = val(snap, key)
        if v >= mn:
            add(b, prio, f"{key} = {v}", min(mx, 1 + int((v - mn) // per)))
    add("home", 90, "residents", min(8, 2 + com["population"] // 40))
    entries.sort(key=lambda e: (e["priority"], e["building"]))
    return entries, sorted(unlocks)


def analyse(snap):
    ident, act, com = identity(snap), activity(snap), community(snap)
    plan, unlocks = build_plan(snap, ident, act, com)
    unavailable = sorted(k for k, m in snap["metrics"].items() if m["s"] == "unavailable")
    inferred = sorted(k for k, m in snap["metrics"].items() if m["s"] == "inferred")
    return {"identity": ident, "activity": act, "community": com, "plan": plan, "unlocks": unlocks,
            "data_quality": {"unavailable": unavailable, "inferred": inferred, "notes": snap.get("notes", [])}}
