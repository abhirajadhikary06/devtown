<!-- DEVTOWN-BANNER:START -->
[![My DevTown](https://git-devtown.netlify.app/api/banners/abhirajadhikary06.png?mode=day&v=7421)](https://git-devtown.netlify.app/@abhirajadhikary06)
<!-- DEVTOWN-BANNER:END -->

# DevTown

**A GitHub-powered voxel city builder that transforms your GitHub activity, repositories, and open-source contributions into a living 3D city.**

DevTown turns your developer profile into a voxel-based city. Every repository, commit, pull request, technology, and collaboration contributes to the development of your virtual town.

Generate a personalized city, customize its layout, explore the community world, and showcase your developer journey through a dynamic README banner.

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js and npm
- Git

### 1. Clone the Repository

```bash
git clone <repository-url>
cd devtown
```

### 2. Start the Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The development environment uses SQLite, with database tables created automatically.

### 3. Start the Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at:

```text
http://localhost:5173
```

Vite proxies `/api` requests to the backend running on port `8000`.

### 4. Explore the Demo

The demo environment works without any additional configuration.

- **Demo City:** `/u/demo`
- **Demo README Banner:** `/api/banners/demo.png`

### 5. Configure GitHub OAuth (Optional)

To enable the **Connect GitHub** functionality:

1. Create a GitHub OAuth App.
2. Configure the authorization callback URL:

   ```text
   http://localhost:5173/api/auth/github/callback
   ```

3. Add the credentials to `backend/.env`:

   ```env
   GITHUB_CLIENT_ID=your_client_id
   GITHUB_CLIENT_SECRET=your_client_secret
   ```

Refer to `backend/.env.example` for the available configuration options.

### 6. Run Tests

```bash
cd backend
pytest
```

---

## Production Deployment

DevTown uses a containerized backend, Neon PostgreSQL for persistence, and Netlify for frontend hosting.

### Deployment Architecture

| Component | Platform / Technology |
|---|---|
| Frontend | Netlify (Vite SPA) |
| Backend | Docker + Render |
| Database | Neon PostgreSQL |
| Database Migrations | Alembic |
| Authentication | GitHub OAuth |

### Backend Deployment

1. Deploy the existing `backend/Dockerfile` using Render.
2. Configure the production environment variables in Render.
3. Set `DATABASE_URL` to Neon's pooled PostgreSQL connection string.

   ```env
   DATABASE_URL=your_neon_pooled_connection_string
   ```

   **Note:** The application reads `DATABASE_URL`, not `NEON_DATABASE_URL`.

4. The existing Dockerfile automatically runs:

   ```bash
   alembic upgrade head
   ```

   before starting Uvicorn.

5. Configure the following production variables:

   ```env
   FRONTEND_URL=https://your-frontend-domain
   PUBLIC_BASE_URL=https://your-frontend-domain
   COOKIE_SECURE=true

   GITHUB_CLIENT_ID=your_client_id
   GITHUB_CLIENT_SECRET=your_client_secret
   DATABASE_URL=your_neon_pooled_connection_string
   ```

### Frontend Deployment

1. Import the `frontend` directory into Netlify as a Vite project.
2. Configure the build and publish settings.
3. Once Render provides the backend URL, add an `/api/*` rewrite to proxy requests to the backend.

   Example:

   ```text
   /api/*  https://your-render-backend.onrender.com/api/:splat  200
   ```

4. Retain the existing SPA fallback configuration in `netlify.toml`.

The API proxy preserves relative API requests and allows GitHub OAuth cookies to work across the frontend and backend deployment.

### GitHub OAuth Callback

Update the callback URL in your production GitHub OAuth App:

```text
https://<api-domain>/api/auth/github/callback
```

### Production Notes

- PostgreSQL is hosted externally on Neon; Docker Compose intentionally does not provision a local database.
- The backend container executes Alembic migrations during startup.
- The frontend must support SPA fallback routing so routes such as `/@username` resolve correctly.
- `PUBLIC_BASE_URL` determines the domain used in the generated README Markdown.

---

## Core Features

### 1. GitHub-Powered City Generation

DevTown analyzes publicly available GitHub profile information and translates developer activity into a personalized voxel city.

The mapping engine considers:

- Programming languages and technologies.
- Commits and contribution consistency.
- Repositories, stars, and forks.
- Pull requests, reviews, and issues.
- Discussions and open-source contributions.
- Releases, documentation, tests, and security-related files.
- Collaboration and other developer activity.

New users receive an automatically generated starter town based on their GitHub profile. Alternatively, they can choose manual setup and construct their city themselves.

### 2. Interactive City Studio

The Studio provides an environment to customize and expand your voxel city.

Supported operations include:

- Building and demolishing structures.
- Rotating buildings before placement.
- Expanding the city.
- Renaming the city.
- Preserving existing layouts across GitHub synchronization.

### 3. Auto Build Town

The **Auto Build town** feature automatically reconstructs the city using the resources currently available.

Its placement strategy:

- Prioritizes the highest affordable population density.
- Uses profile-specific buildings as tie-breakers.
- Preserves existing trees and other free decorations.
- Does not consume energy or reputation.
- Uses relaxed building costs to support smaller accounts.

**Important:** Auto Build deliberately clears the existing layout and rebuilds it from scratch. The operation requires confirmation before execution.

### 4. Scheduled Auto Build

Users can optionally enable Scheduled Auto Build to automatically reconstruct their towns.

The backend checks opted-in towns every 30 seconds and triggers rebuilding at:

| Time | Event |
|---|---|
| 06:00 | Day transition |
| 18:00 | Dusk transition |
| 21:00 | Night transition |

All scheduled transitions follow the user's configured IANA timezone.

Scheduled execution is best-effort. Since scheduling runs in-process, Render restarts or sleeping instances can cause transitions to be skipped. No external cron service is required.

### 5. Community World

The Community world displays saved user cities as individual 3D plots arranged alongside one another.

This creates a shared environment where developers can explore each other's GitHub-powered cities.

### 6. Dynamic Lighting System

DevTown supports four lighting modes:

- **Auto** – Automatically determines lighting based on the user's local timezone.
- **Day** – Daytime lighting.
- **Dusk** – Evening lighting.
- **Night** – Nighttime lighting.

Auto mode uses the following schedule:

| Local Time | Lighting |
|---|---|
| 06:00–18:00 | Day |
| 18:00–21:00 | Dusk |
| 21:00–06:00 | Night |

The user's IANA timezone is stored to ensure accurate local-time transitions.

---

## README Banner

DevTown generates a personalized PNG banner that developers can embed directly into their GitHub profile README.

**Banner specifications**

| Property | Value |
|---|---|
| Endpoint | `GET /api/banners/{username}.png` |
| Image format | PNG |
| Original dimensions | 1734 × 574 px |
| Display dimensions | Approximately 514 × 170 px |
| Accessibility | Public endpoint |
| Rendering | Server-side Pillow isometric renderer |

### Versioned Banner Caching

The banner endpoint supports immutable version-based caching.

```text
/api/banners/{username}.png?v={version}
```

- Versioned requests use immutable caching.
- Requests without a version use `max-age=300`.
- Every city edit increments `city.version`.
- Updated banners are rendered in the background and stored per version.
- Unknown users receive a placeholder PNG with HTTP 404, preventing broken README image embeds.

### Lighting-Aware Banner URLs

Banner responses expose the resolved lighting mode and a mode-specific versioned preview URL.

The generated Markdown includes both the lighting mode and revision.

This ensures:

- Manually selecting Night or Dusk updates the banner immediately.
- Auto mode generates a new URL whenever the local lighting period changes.
- Previously cached banner versions remain immutable.

---

## Architecture

DevTown follows a **Modular Monolith Architecture**, separating core functionality into independent domain modules while maintaining a single backend application.

### Backend Architecture

| Module | Responsibility | Implementation |
|---|---|---|
| GitHub Ingestion | GraphQL and REST data extraction, classification | `github/ingest.py` |
| Technology Catalogue | Technology detection and mapping | `data/technologies.json`, `github/techs.py` |
| Mapping Engine | Identity, activity, community, and building rules | `mapping/engine.py` |
| Economy Engine | Rewards, saturating caps, idempotent ledger deltas | `economy/rewards.py`, `api/services.py` |
| World Generator | Deterministic terrain and starter placement | `world/generator.py` |
| Building Catalogue | Building definitions and costs | `world/catalogue.py` |
| Banner Renderer | Server-side isometric banner generation | `banner/renderer.py` |
| Persistence Layer | Database models, city edits, banner caching | `models.py`, `api/services.py`, `alembic/` |
| Frontend Renderer | Voxel rendering and Studio interface | `CityCanvas.tsx`, `pages/` |

### Frontend

The frontend is built with React, TypeScript, and Vite.

The primary voxel rendering component is:

```text
frontend/src/components/CityCanvas.tsx
```

It handles the interactive city visualization, while the page components provide the surrounding Studio and community interfaces.

---

## World Generation and Persistence

DevTown uses deterministic, chunk-based terrain generation to ensure that cities remain consistent across sessions.

### Persisted City State

The city state is represented by:

- World seed.
- Generation version.
- Claimed terrain chunks.
- Placed building and decoration items.

Terrain is regenerated deterministically using the same login identity, seed, and generation version.

This means:

```text
Same Login + Same Seed + Same Generation Version
                    ↓
             Same Starter City
```

### GitHub Re-Synchronization

Re-syncing GitHub does not overwrite existing user modifications.

Instead, synchronization only expands:

- Unlocks.
- Levels.
- Available resources.

This preserves the user's existing city layout while allowing progression as their GitHub activity evolves.

---

## Known Limitations

The following limitations are important to understand before relying on the implementation in production.

### 1. GitHub API Integration

- Live GitHub ingestion has not yet been executed against the actual API.
- The parser is unit-tested using synthetic payloads.
- The GraphQL query is syntax-balanced but has not been verified against GitHub's actual schema or query-cost limits.
- Field names and query structure may require adjustments during live integration.

### 2. Rendering and Assets

- Buildings currently use procedural instanced boxes rather than GLB/GLTF assets.
- README banners are generated using a Pillow-based isometric renderer.
- The banner renderer approximates the Studio's visual appearance but is not pixel-identical to the WebGL-style Studio renderer.

### 3. Partially Implemented Mapping

The following features have real mapping logic:

- Languages and technologies.
- Commits and contribution consistency.
- Pull requests, reviews, and issues.
- Discussions and open-source contributions.
- Repositories, stars, and forks.
- Releases, documentation, tests, and security files.
- Collaboration.

The following features currently have coarse implementations:

- Branch roads: branches and tags appear as markers, alongside a logistics depot; no actual road network changes.
- Rivers: a single river.
- Parallel routes.
- Connected neighbourhoods.

### 4. GitHub Data Availability

Some metrics are unavailable because they require additional permissions, scopes, or data sources.

These include:

- Signed commits.
- Code-scanning alerts.
- Packages and containers.
- Review comments.
- Approved pull requests.
- Scheduled workflows.
- Maintainer status for non-self lookups.

Unavailable metrics do not contribute rewards.

DevTown currently accesses public GitHub data using the `read:user` scope.

Public GitHub events cover approximately 90 days, meaning push and branch metrics are inferred rather than comprehensively measured.

### 5. Synchronization and Rate Limits

- GitHub synchronization currently executes inline within the request lifecycle.
- Large accounts may require background worker processing.
- Rate-limit backoff is not implemented beyond reporting the relevant errors.

### 6. Studio Interaction

The Studio currently supports:

- Build.
- Demolish.
- Rotate before placing.
- Expand.
- Rename.

Drag-to-move functionality for already placed items is not yet available in the UI.

However, the corresponding backend endpoint exists:

```http
PATCH /me/city/items/{id}
```

### 7. Deployment Verification

The following components have been implemented but have not been fully verified end-to-end:

- GitHub OAuth flow.
- PostgreSQL production configuration.
- Alembic migration workflow.
- Docker-based deployment.

Alembic migrations have been verified against SQLite, but the complete production PostgreSQL deployment path remains untested.

---

## Technology Stack

| Layer | Technologies |
|---|---|
| Frontend | React, TypeScript, Vite |
| 3D Visualization | Voxel-based procedural rendering |
| Backend | Python, FastAPI |
| Database | SQLite (Development), PostgreSQL (Production) |
| ORM / Migrations | SQLAlchemy, Alembic |
| GitHub Integration | GitHub GraphQL API, REST API, OAuth |
| Banner Generation | Pillow |
| Deployment | Docker, Docker Compose, Render, Netlify |
| Database Hosting | Neon PostgreSQL |

---

## Project Structure

```text
devtown/
├── backend/
│   ├── app/
│   │   ├── github/
│   │   ├── mapping/
│   │   ├── economy/
│   │   ├── world/
│   │   ├── banner/
│   │   ├── api/
│   │   ├── data/
│   │   └── main.py
│   ├── alembic/
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   └── pages/
│   ├── package.json
│   └── vite.config.ts
│
├── docker-compose.yml
└── netlify.toml
```

---

## Testing

Backend tests are written using pytest.

Run the test suite:

```bash
cd backend
pytest
```

### License
See the repository's LICENSE file for licensing information.

## License

See the repository's `LICENSE` file for licensing information.
