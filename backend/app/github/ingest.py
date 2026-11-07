"""GitHub ingestion -> normalized Snapshot.

Snapshot = {login, fetched_at, metrics:{key:{v,s}}, languages:{name:bytes}, technologies:[...], notes:[...]}
Every metric is classified: verified (read directly from GitHub), inferred (sampled/approximated), or
unavailable (could not be read: v is None and nothing is rewarded for it). Nothing is ever fabricated.
"""
import re
import time
from datetime import date, datetime, timedelta, timezone

from . import techs
from .client import GitHubClient, RateLimited

MANIFESTS = ["package.json", "requirements.txt", "pyproject.toml", "pom.xml", "build.gradle", "Cargo.toml",
             "go.mod", "Gemfile", "composer.json", "docker-compose.yml"]
MAX_REPOS = 20
MAX_YEARS = 12
_SNAPSHOT_CACHE: dict[tuple[str, str, bool], tuple[float, dict]] = {}
SNAPSHOT_TTL = 300

PROFILE_Q = """
query($login:String!, $prMerged:String!){
  user(login:$login){
    login name createdAt avatarUrl databaseId
    followers{totalCount} organizations{totalCount} starredRepositories{totalCount}
    contributionsCollection{contributionYears}
    prM: pullRequests(states:MERGED){totalCount} prC: pullRequests(states:CLOSED){totalCount} prO: pullRequests(states:OPEN){totalCount}
    iO: issues(states:OPEN){totalCount} iC: issues(states:CLOSED){totalCount}
    issueComments{totalCount} repositoryDiscussions{totalCount} repositoryDiscussionComments{totalCount}
    forksOwned: repositories(isFork:true, ownerAffiliations:OWNER){totalCount}
    repositoriesContributedTo(first:100, includeUserRepositories:false, contributionTypes:[COMMIT,PULL_REQUEST,PULL_REQUEST_REVIEW,ISSUE], orderBy:{field:STARGAZERS, direction:DESC}){
      totalCount nodes{ nameWithOwner owner{login} stargazerCount viewerPermission isArchived } }
    repositories(first:%(n)d, isFork:false, ownerAffiliations:OWNER, orderBy:{field:PUSHED_AT, direction:DESC}){
      totalCount
      nodes{ name isArchived isPrivate stargazerCount forkCount watchers{totalCount} createdAt pushedAt diskUsage
        homepageUrl hasWikiEnabled isSecurityPolicyEnabled licenseInfo{spdxId}
        languages(first:10, orderBy:{field:SIZE, direction:DESC}){edges{size node{name}}}
        repositoryTopics(first:15){nodes{topic{name}}}
        branches: refs(refPrefix:"refs/heads/"){totalCount} tags: refs(refPrefix:"refs/tags/"){totalCount}
        releases{totalCount} latestRelease{tagName} deployments{totalCount}
        root: object(expression:"HEAD:"){... on Tree{entries{name}}}
        gh: object(expression:"HEAD:.github"){... on Tree{entries{name}}}
        wf: object(expression:"HEAD:.github/workflows"){... on Tree{entries{name}}}
        %(manifests)s
      } }
  }
  ext: search(query:$prMerged, type:ISSUE, first:1){issueCount}
}
"""


def build_profile_query():
    # Manifest file *contents* are not read inline — the per-repo blob reads (12 x 40 = 480)
    # pushed the query past GitHub's complexity/time limits, returning 502. Tech detection
    # still works via repository topics + root file names; only dependency-name evidence is dropped.
    return PROFILE_Q % {"n": MAX_REPOS, "manifests": ""}


def year_query(years):
    parts = []
    for y in years:
        parts.append(f'''y{y}: contributionsCollection(from:"{y}-01-01T00:00:00Z", to:"{y}-12-31T23:59:59Z"){{
          totalCommitContributions totalPullRequestReviewContributions restrictedContributionsCount
          contributionCalendar{{weeks{{contributionDays{{date contributionCount}}}}}}
          pullRequestContributionsByRepository(maxRepositories:100){{repository{{nameWithOwner owner{{login}}}} contributions{{totalCount}}}}
          pullRequestReviewContributionsByRepository(maxRepositories:100){{repository{{owner{{login}}}} contributions{{totalCount}}}}
        }}''')
    return "query($login:String!){ user(login:$login){ " + "\n".join(parts) + " } }"


def _streaks(days: set[date], today: date):
    best = cur = run = 0
    prev = None
    for d in sorted(days):
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, run)
        prev = d
    d = today if today in days else today - timedelta(days=1)
    while d in days:
        cur += 1
        d -= timedelta(days=1)
    return best, cur


def _semver_major(tag):
    m = re.match(r"v?(\d+)\.", tag or "")
    return int(m.group(1)) if m else 0


def build_snapshot(login: str, profile: dict | None, years: dict, events: list | None, contributors: dict | None,
                   is_self: bool, now: datetime | None = None, notes: list | None = None) -> dict:
    """Pure function: raw API payloads -> snapshot. `profile` is the GraphQL `user` object (or None)."""
    now = now or datetime.now(timezone.utc)
    M: dict[str, dict] = {}
    notes = list(notes or [])

    def put(k, v, s="verified"):
        M[k] = {"v": v, "s": s if v is not None else "unavailable"}

    def na(*keys):
        for k in keys:
            M[k] = {"v": None, "s": "unavailable"}

    langs: dict[str, int] = {}
    repo_ev = []
    if profile is None:
        notes.append("GitHub profile data could not be read.")
        return {"login": login, "fetched_at": now.isoformat(), "metrics": M, "languages": {}, "technologies": [], "notes": notes}

    # ---- contributions over time
    commits = reviews = restricted = 0
    days: set[date] = set()
    per_repo_pr: dict[str, int] = {}
    ext_reviews = 0
    for y, c in years.items():
        commits += c.get("totalCommitContributions", 0)
        reviews += c.get("totalPullRequestReviewContributions", 0)
        restricted += c.get("restrictedContributionsCount", 0)
        for w in c.get("contributionCalendar", {}).get("weeks", []):
            for d in w["contributionDays"]:
                if d["contributionCount"] > 0:
                    days.add(date.fromisoformat(d["date"]))
        for e in c.get("pullRequestContributionsByRepository", []):
            r = e["repository"]
            if r["owner"]["login"].lower() != login.lower():
                per_repo_pr[r["nameWithOwner"]] = per_repo_pr.get(r["nameWithOwner"], 0) + e["contributions"]["totalCount"]
        for e in c.get("pullRequestReviewContributionsByRepository", []):
            if e["repository"]["owner"]["login"].lower() != login.lower():
                ext_reviews += e["contributions"]["totalCount"]
    have_years = bool(years)
    all_years = profile.get("contributionsCollection", {}).get("contributionYears", [])
    st = "verified" if len(years) >= len(all_years) else "inferred"
    if have_years:
        best, cur = _streaks(days, now.date())
        put("commits.total", commits, st)
        put("commits.private", restricted, "inferred")
        put("days.active", len(days), st)
        put("weeks.active", len({d.isocalendar()[:2] for d in days}), st)
        put("months.active", len({(d.year, d.month) for d in days}), st)
        put("streak.longest", best, st)
        put("streak.current", cur, st)
        put("reviews.given", reviews, st)
        put("external.reviews", ext_reviews, "inferred")
        put("oss.max_repeat", max(per_repo_pr.values(), default=0), "inferred")
    else:
        na("commits.total", "commits.private", "days.active", "weeks.active", "months.active", "streak.longest",
           "streak.current", "reviews.given", "external.reviews", "oss.max_repeat")
    put("history.years", len(all_years))

    # ---- PRs, issues, discussions
    g = lambda k: (profile.get(k) or {}).get("totalCount")
    pm, pc, po = g("prM"), g("prC"), g("prO")
    put("prs.merged", pm); put("prs.closed", pc); put("prs.open", po)
    put("prs.opened_any", sum(x or 0 for x in (pm, pc, po)))
    put("issues.opened", g("iO")); put("issues.closed", g("iC"))
    put("issues.comments", g("issueComments"))
    put("discussions.started", g("repositoryDiscussions")); put("discussions.comments", g("repositoryDiscussionComments"))
    na("reviews.comments", "prs.approved", "commits.signed", "packages.published", "containers.published", "repos.codeql_scanning")
    ext = profile.get("ext") or {}
    put("external.prs_merged", ext.get("issueCount"))

    # ---- external / OSS
    rct = profile.get("repositoriesContributedTo") or {}
    nodes = rct.get("nodes") or []
    sat = "verified" if (rct.get("totalCount") or 0) <= len(nodes) else "inferred"
    owners = {n["owner"]["login"].lower() for n in nodes if n["owner"]["login"].lower() != login.lower()}
    put("external.repos", rct.get("totalCount"))
    put("external.orgs", len(owners), sat)
    put("external.popular", sum(1 for n in nodes if n["stargazerCount"] >= 1000), sat)
    if is_self:
        put("oss.maintained", sum(1 for n in nodes if n.get("viewerPermission") in ("ADMIN", "MAINTAIN", "WRITE")), sat)
    else:
        na("oss.maintained")

    # ---- owned repositories
    rp = profile.get("repositories") or {}
    repos = rp.get("nodes") or []
    sampled = (rp.get("totalCount") or 0) > len(repos)
    rs = "inferred" if sampled else "verified"
    yr = now - timedelta(days=365)
    ages = []
    c = dict.fromkeys(["readme", "licensed", "docs", "wiki", "tests", "ci", "sched", "codeql", "dependabot", "secpol", "coc",
                       "issue_t", "pr_t", "pages", "popular", "large", "active", "archived"], 0)
    stars = forks = watch = rel = dep = tags = branches = semver = 0
    for r in repos:
        root = [e["name"] for e in ((r.get("root") or {}).get("entries") or [])]
        rl = [x.lower() for x in root]
        ghd = [e["name"].lower() for e in ((r.get("gh") or {}).get("entries") or [])]
        wf = [e["name"].lower() for e in ((r.get("wf") or {}).get("entries") or [])]
        mani = {MANIFESTS[i]: (r.get(f"m{i}") or {}).get("text", "") for i in range(len(MANIFESTS)) if r.get(f"m{i}")}
        topics = [t["topic"]["name"] for t in (r.get("repositoryTopics") or {}).get("nodes", [])]
        repo_ev.append({"name": r["name"], "topics": topics, "root_files": root, "manifests": mani})
        for e in (r.get("languages") or {}).get("edges", []):
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
        stars += r["stargazerCount"]; forks += r["forkCount"]; watch += (r.get("watchers") or {}).get("totalCount", 0)
        rel += (r.get("releases") or {}).get("totalCount", 0); dep += (r.get("deployments") or {}).get("totalCount", 0)
        tags += (r.get("tags") or {}).get("totalCount", 0); branches += (r.get("branches") or {}).get("totalCount", 0)
        if _semver_major((r.get("latestRelease") or {}).get("tagName")) >= 1:
            semver += 1
        created = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
        ages.append((now - created).days / 365.25)
        c["readme"] += any(x.startswith("readme") for x in rl)
        c["licensed"] += bool(r.get("licenseInfo")) or any(x.startswith("license") for x in rl)
        c["docs"] += "docs" in rl
        c["wiki"] += bool(r.get("hasWikiEnabled"))
        c["tests"] += any(x in ("test", "tests", "__tests__", "spec") for x in rl)
        c["ci"] += bool(wf)
        c["codeql"] += any("codeql" in x for x in wf)
        c["dependabot"] += any(x.startswith("dependabot") for x in ghd)
        c["secpol"] += bool(r.get("isSecurityPolicyEnabled")) or "security.md" in rl
        c["coc"] += any("code_of_conduct" in x for x in rl + ghd)
        c["issue_t"] += any("issue_template" in x for x in rl + ghd)
        c["pr_t"] += any("pull_request_template" in x for x in rl + ghd)
        c["pages"] += (r["name"].lower().endswith(".github.io")) or bool((r.get("homepageUrl") or "").endswith(".github.io"))
        c["popular"] += r["stargazerCount"] >= 100
        c["large"] += (r.get("diskUsage") or 0) >= 20000
        pushed = datetime.fromisoformat(r["pushedAt"].replace("Z", "+00:00")) if r.get("pushedAt") else None
        c["active"] += bool(pushed and pushed > yr and not r["isArchived"])
        c["archived"] += bool(r["isArchived"])
    put("repos.owned", rp.get("totalCount")); put("repos.forks_owned", g("forksOwned"))
    for k, key in [("archived", "repos.archived"), ("active", "repos.active"), ("large", "repos.large"), ("readme", "repos.with_readme"),
                   ("licensed", "repos.licensed"), ("docs", "repos.with_docs"), ("wiki", "repos.with_wiki"), ("tests", "repos.with_tests"),
                   ("ci", "repos.with_ci"), ("dependabot", "repos.dependabot"), ("secpol", "repos.security_policy"), ("coc", "repos.coc"),
                   ("issue_t", "repos.issue_templates"), ("pr_t", "repos.pr_templates"), ("popular", "repos.popular")]:
        put(key, c[k], rs)
    put("repos.codeql", c["codeql"], "inferred")  # workflow file names only; real alerts need security_events scope
    put("repos.pages", c["pages"], "inferred")
    put("repos.scheduled_ci", None)  # needs workflow file contents; not read
    put("repos.oldest_years", int(max(ages, default=0)), rs)
    put("stars.received", stars, rs); put("forks.received", forks, rs); put("watchers.total", watch, rs)
    put("stars.given", g("starredRepositories"))
    put("releases.total", rel, rs); put("releases.semver_major", semver, "inferred")
    put("deployments.total", dep, rs); put("tags.total", tags, rs); put("branches.total", branches, rs)
    put("followers", g("followers")); put("orgs.member", g("organizations"))

    # ---- contributors (REST, top repos) and recent events (90-day window)
    if contributors is not None:
        uniq = {x.lower() for lst in contributors.values() for x in lst} - {login.lower()}
        put("contributors.external", len(uniq), "inferred")
    else:
        na("contributors.external")
    if events is not None:
        push = [e for e in events if e["type"] == "PushEvent"]
        mk = lambda t: sum(1 for e in events if e["type"] == "CreateEvent" and e.get("payload", {}).get("ref_type") == t)
        put("pushes.recent", len(push), "inferred"); put("branches.recent", mk("branch"), "inferred")
        notes.append("Push and branch activity comes from GitHub's public events feed, which only covers ~90 days.")
    else:
        na("pushes.recent", "branches.recent")
    if not is_self:
        notes.append("Private repositories and maintainer permissions are not visible without the user's own token.")
    return {"login": login, "fetched_at": now.isoformat(), "metrics": M, "languages": langs,
            "technologies": techs.detect(repo_ev), "notes": notes,
            "profile": {"name": profile.get("name"), "avatar": profile.get("avatarUrl"), "created": profile.get("createdAt"),
                        "databaseId": profile.get("databaseId")}}


async def collect_snapshot(client: GitHubClient, login: str, is_self: bool = True, force: bool = False) -> dict:
    cache_key = (client.http.headers.get("Authorization", "public"), login.lower(), is_self)
    cached = _SNAPSHOT_CACHE.get(cache_key)
    if cached and cached[0] > time.monotonic() and not force:
        return cached[1]
    notes: list[str] = []
    try:
        data, errs = await client.graphql(build_profile_query(), {"login": login, "prMerged": f"author:{login} is:pr is:merged -user:{login}"})
    except Exception as exc:
        data, errs = {}, [str(exc)]
    profile = data.get("user")
    if profile is not None and data.get("ext") is not None:
        profile = {**profile, "ext": data["ext"]}
    if errs:
        notes.append(f"GitHub returned {len(errs)} partial error(s); affected metrics are marked unavailable.")
    if not profile:
        # Smaller REST requests recover the useful public profile and language
        # data when GitHub rejects the large GraphQL query as too complex.
        try:
            user = await client.rest(f"/users/{login}")
            # Keep anonymous showcase seeding within GitHub's shared REST rate
            # limit while still sampling enough public projects for a town.
            repo_rows = await client.rest(f"/users/{login}/repos", per_page=6, sort="pushed", direction="desc")
            repos = []
            langs = {}
            for repo in repo_rows:
                lang_data = await client.rest(f"/repos/{login}/{repo['name']}/languages")
                for lang, size in lang_data.items():
                    langs[lang] = langs.get(lang, 0) + size
                repos.append({"name": repo["name"], "isArchived": repo.get("archived", False),
                              "isPrivate": repo.get("private", False), "stargazerCount": repo.get("stargazers_count", 0),
                              "forkCount": repo.get("forks_count", 0), "watchers": {"totalCount": repo.get("watchers_count", 0)},
                              "createdAt": repo["created_at"], "pushedAt": repo.get("pushed_at"), "diskUsage": repo.get("size", 0),
                              "homepageUrl": repo.get("homepage"), "hasWikiEnabled": repo.get("has_wiki", False),
                              "isSecurityPolicyEnabled": False, "licenseInfo": {"spdxId": repo.get("license", {}).get("spdx_id")} if repo.get("license") else None,
                              "languages": {"edges": []}, "repositoryTopics": {"nodes": []}, "branches": {"totalCount": 0},
                              "tags": {"totalCount": 0}, "releases": {"totalCount": 0}, "latestRelease": None,
                              "deployments": {"totalCount": 0}, "root": {"entries": []}, "gh": {"entries": []}, "wf": {"entries": []}})
            profile = {"name": user.get("name"), "avatarUrl": user.get("avatar_url"), "databaseId": user.get("id"),
                       "createdAt": user.get("created_at"), "followers": {"totalCount": user.get("followers", 0)},
                       "organizations": {"totalCount": 0}, "starredRepositories": {"totalCount": 0},
                       "contributionsCollection": {"contributionYears": []}, "repositories": {"totalCount": user.get("public_repos", len(repo_rows)), "nodes": repos},
                       "repositoriesContributedTo": {"totalCount": 0, "nodes": []}, "prM": {}, "prC": {}, "prO": {}, "iO": {}, "iC": {},
                       "issueComments": {}, "repositoryDiscussions": {}, "repositoryDiscussionComments": {}, "forksOwned": {}, "ext": {"issueCount": 0}}
            notes.append("GitHub's detailed query was unavailable; public repositories and languages were read through the REST API. Other metrics remain unavailable.")
            snap = build_snapshot(login, profile, {}, None, None, is_self, notes=notes)
            snap["languages"] = langs
            # The fallback did not read these GraphQL-only fields. Do not let
            # placeholder values in the adapter turn them into claimed zeroes.
            unavailable = ("commits.total", "commits.private", "days.active", "weeks.active", "months.active", "streak.longest",
                           "streak.current", "reviews.given", "external.reviews", "oss.max_repeat", "prs.merged", "prs.closed",
                           "prs.open", "prs.opened_any", "issues.opened", "issues.closed", "issues.comments", "discussions.started",
                           "discussions.comments", "external.prs_merged", "external.repos", "external.orgs", "external.popular",
                           "oss.maintained", "stars.given", "orgs.member", "history.years", "repos.with_readme", "repos.with_docs",
                           "repos.with_tests", "repos.with_ci", "repos.dependabot", "repos.security_policy", "repos.coc",
                           "repos.issue_templates", "repos.pr_templates", "repos.with_wiki", "repos.codeql", "repos.pages",
                           "repos.scheduled_ci", "releases.total", "releases.semver_major", "deployments.total", "tags.total", "branches.total")
            for metric in unavailable:
                snap["metrics"][metric] = {"v": None, "s": "unavailable"}
            _SNAPSHOT_CACHE[cache_key] = (time.monotonic() + SNAPSHOT_TTL, snap)
            return snap
        except Exception as exc:
            notes.append(f"Public REST profile fallback failed: {type(exc).__name__}.")
            return build_snapshot(login, None, {}, None, None, is_self, notes=notes)
    ys = sorted(profile["contributionsCollection"]["contributionYears"], reverse=True)[:MAX_YEARS]
    years: dict = {}
    try:
        if ys:
            d, e = await client.graphql(year_query(ys), {"login": login})
            years = {int(k[1:]): v for k, v in (d.get("user") or {}).items() if v}
            if len(profile["contributionsCollection"]["contributionYears"]) > MAX_YEARS:
                notes.append(f"Only the latest {MAX_YEARS} contribution years were read.")
    except RateLimited:
        notes.append("Rate limit reached while reading contribution history.")
    except Exception:
        # Contribution history is optional; keep the verified profile and
        # repository evidence gathered by the successful primary query.
        notes.append("Contribution history could not be read; other public profile data is still available.")
    events = None
    try:
        events = []
        for p in (1, 2, 3):
            page = await client.rest(f"/users/{login}/events/public", per_page=100, page=p)
            events += page
            if len(page) < 100:
                break
    except Exception:
        events = None
    contributors = None
    try:
        contributors = {}
        top = sorted((profile.get("repositories") or {}).get("nodes") or [], key=lambda r: -r["stargazerCount"])[:5]
        for r in top:
            lst = await client.rest(f"/repos/{login}/{r['name']}/contributors", per_page=100)
            contributors[r["name"]] = [u["login"] for u in lst if u.get("type") == "User"]
    except Exception:
        contributors = contributors or None
    snap = build_snapshot(login, profile, years, events, contributors, is_self, notes=notes)
    _SNAPSHOT_CACHE[cache_key] = (time.monotonic() + SNAPSHOT_TTL, snap)
    return snap
