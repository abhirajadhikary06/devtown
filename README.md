# DevTown

GitHub-powered voxel city builder with a public README banner (1734 × 574 PNG, shown at ~514 × 170).

## Run it

```bash
# backend (SQLite in dev, tables auto-created)
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend (proxies /api to :8000)
cd frontend && npm install && npm run dev      # http://localhost:5173
```

The demo city (`/u/demo`, `/api/banners/demo.png`) works with no configuration.
To enable "Connect GitHub", create a GitHub OAuth App (callback `http://localhost:5173/api/auth/github/callback`)
and set `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` in `backend/.env` (see `.env.example`).
Production: Neon PostgreSQL + `alembic upgrade head` (the backend container runs this on startup), and serve the SPA with a fallback to
`index.html` so `/@username` resolves. Set `PUBLIC_BASE_URL` to your domain; it is used in the copied Markdown.
Tests: `cd backend && pytest`.

### Production deployment

Use Docker Compose to run the backend container. PostgreSQL is hosted by Neon; the Compose file intentionally does
not start a local database service. Configure `backend/.env`'s `DATABASE_URL` with Neon's pooled connection string
(`NEON_DATABASE_URL` is not read by the application).
The existing `backend/Dockerfile` runs `alembic upgrade head` before starting Uvicorn.
Deploy `frontend` as a Vite site on Netlify and proxy `/api/*` to the Render backend so the existing relative API
URLs and GitHub OAuth cookies continue to work. Add the `/api/*` rewrite in Netlify after Render gives you the
backend URL; the committed `netlify.toml` contains the SPA fallback. Set `FRONTEND_URL`, `PUBLIC_BASE_URL`,
`COOKIE_SECURE=true`, and the production secrets in Render. The GitHub OAuth callback must be
`https://<api-domain>/api/auth/github/callback`.

Lighting supports Auto, Day, Dusk, and Night. Auto stores the user's IANA timezone and changes the studio and
banner between day (06:00-18:00), dusk (18:00-21:00), and night. README banner responses expose the resolved lighting mode and a mode-specific versioned preview URL. The copied
Markdown includes that mode and revision, so manually selecting Night or Dusk is reflected immediately, while Auto
gets a new URL whenever the user's local-time lighting period changes.
The Community world renders every saved city as a 3D plot arranged beside the other plots.
After GitHub analysis, new accounts default to an automatically placed starter town based on the profile plan.
Users can choose manual setup instead and place buildings themselves.
In the Studio, **Auto Build town** deliberately clears the current layout and rebuilds it from scratch using the
coins and materials currently available. It favors the highest affordable population density, keeps profile-specific
buildings as tie-breakers, and does not spend energy or reputation. The action is confirmed before it runs.

## Architecture (modular monolith)

| Concern | Where |
|---|---|
| GitHub ingestion (GraphQL + REST), verified/inferred/unavailable classification | `backend/app/github/ingest.py` |
| Technology catalogue (extend by editing JSON) | `backend/app/data/technologies.json`, `github/techs.py` |
| Identity / activity / community engines + building plan rules | `backend/app/mapping/engine.py` |
| Rewards: saturating caps, idempotent ledger deltas | `backend/app/economy/rewards.py`, `api/services.py` |
| Deterministic chunked terrain + starter placement | `backend/app/world/generator.py` |
| Building catalogue (one line per building) | `backend/app/world/catalogue.py` |
| Server-side banner camera | `backend/app/banner/renderer.py` |
| Persistence / edits / banner cache | `models.py`, `api/services.py`, `alembic/` |
| Voxel renderer + studio UI | `frontend/src/components/CityCanvas.tsx`, `pages/` |

Persisted city state = seed + generation version + claimed chunks + placed items. Terrain is regenerated
deterministically (same login + seed + generation version → same starter city). Re-syncing GitHub never overwrites
user edits; it only widens unlocks, level and resources.

## Banner
`GET /api/banners/{username}.png` is public. `?v={version}` is immutable-cached; without it the response is
`max-age=300`. Every edit bumps `city.version` and re-renders in the background; the PNG is stored per version.
Unknown users get a placeholder PNG with status 404 so README embeds never show a broken image.

## Known gaps vs. the spec (read before relying on it)
- **GitHub ingestion has not been run against the live API.** The parser is unit-tested on synthetic payloads; the
  GraphQL query is syntax-balanced but unverified against GitHub's schema/cost limits. Expect to tune field names.
- Buildings are procedural instanced boxes, not GLB/GLTF assets. The banner uses a Pillow isometric renderer rather
  than headless WebGL, so it matches the studio's look but is not pixel-identical.
- Mapped with real logic: languages, technologies, commits/consistency, PRs, reviews, issues, discussions, OSS,
  repos, stars/forks, releases, docs/tests/security files, collaboration. Only coarse versions exist for: branch
  roads (no road network changes; branches/tags only appear as markers and a logistics depot), rivers (one river),
  parallel routes, "connected neighbourhoods".
- Unavailable without extra scopes or data: signed commits, code-scanning alerts, packages/containers, review
  comments, approved PRs, scheduled workflows, maintainer status for non-self lookups. They earn nothing.
- Only public data is read (`read:user` scope). Public events cover ~90 days, so push/branch metrics are "inferred".
- Sync runs inline in the request; move to a worker for large accounts. No rate-limit backoff beyond reporting.
- The studio supports build / demolish / rotate-before-placing / expand / rename. There is no drag-to-move of
  existing items in the UI (the `PATCH /me/city/items/{id}` endpoint exists).
- The OAuth flow, Postgres/Alembic path and Docker files are written but untested end-to-end here (Alembic upgrade was verified on SQLite).
