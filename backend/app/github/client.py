import asyncio
import time

import httpx

API = "https://api.github.com"


class RateLimited(Exception):
    def __init__(self, reset=None):
        super().__init__("GitHub rate limit reached")
        self.reset = reset


class GitHubClient:
    # Process-local response cache: useful across repeated profile searches and
    # refreshes while keeping authenticated responses scoped to their token.
    _profile_cache: dict[tuple[str, str], tuple[float, dict]] = {}
    PROFILE_TTL = 300
    def __init__(self, token: str | None = None, transport=None, retries: int = 3):
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "devtown"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        self.authenticated = bool(token)
        self.http = httpx.AsyncClient(base_url=API, headers=h, timeout=30, transport=transport)
        self.retries = retries

    async def close(self):
        await self.http.aclose()

    def _check(self, r: httpx.Response):
        if r.status_code in (403, 429) and r.headers.get("x-ratelimit-remaining") == "0":
            raise RateLimited(r.headers.get("x-ratelimit-reset"))
        r.raise_for_status()

    async def _with_retries(self, method, *args, **kwargs) -> httpx.Response:
        """Retry on transient 5xx / transport errors with exponential backoff.
        GitHub returns 502/504 for expensive GraphQL queries under load; a couple of
        retries with backoff makes ingestion reliable. The README previously noted the
        absence of backoff as a known gap."""
        backoff = 1.0
        for attempt in range(self.retries + 1):
            try:
                r = await method(*args, **kwargs)
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
                await asyncio.sleep(backoff); backoff *= 2; continue
            if r.status_code >= 500 and attempt < self.retries:
                await asyncio.sleep(backoff); backoff *= 2; continue
            return r
        return r  # all retries exhausted; _check() will raise on the 5xx

    async def rest(self, path: str, **params):
        if path.startswith("/users/") and path.count("/") == 2 and not params:
            key = (self.http.headers.get("Authorization", "public"), path.lower())
            cached = self._profile_cache.get(key)
            if cached and cached[0] > time.monotonic():
                return cached[1]
        r = await self._with_retries(self.http.get, path, params=params)
        self._check(r)
        result = r.json()
        if path.startswith("/users/") and path.count("/") == 2 and not params:
            self._profile_cache[key] = (time.monotonic() + self.PROFILE_TTL, result)
        return result

    async def graphql(self, query: str, variables: dict | None = None):
        """Returns (data, errors). Partial data is kept: fields GitHub refuses come back as errors, not exceptions."""
        if not self.authenticated:
            raise PermissionError("GitHub GraphQL requires a token")
        r = await self._with_retries(self.http.post, "/graphql", json={"query": query, "variables": variables or {}})
        self._check(r)
        j = r.json()
        return j.get("data") or {}, j.get("errors") or []
