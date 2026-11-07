"""Safe, marker-based updates for the configured DevTown README repository."""
import base64
import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)
START = "<!-- DEVTOWN-BANNER:START -->"
END = "<!-- DEVTOWN-BANNER:END -->"


def _block(markdown: str) -> str:
    return f"{START}\n{markdown}\n{END}"


def sync_banner(markdown: str) -> bool:
    if not settings.github_readme_token or not settings.github_readme_repository:
        return False
    repository = settings.github_readme_repository.strip("/")
    if repository.count("/") != 1:
        raise ValueError("GITHUB_README_REPOSITORY must be owner/repository")
    endpoint = f"https://api.github.com/repos/{repository}/contents/README.md"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {settings.github_readme_token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "devtown",
    }
    with httpx.Client(timeout=20, headers=headers) as client:
        response = client.get(endpoint)
        if response.status_code == 404:
            logger.warning("README sync skipped: README.md not found in %s", repository)
            return False
        response.raise_for_status()
        payload = response.json()
        current = base64.b64decode(payload["content"]).decode("utf-8")
        managed = _block(markdown)
        if START in current and END in current:
            before, remainder = current.split(START, 1)
            _, after = remainder.split(END, 1)
            updated = before + managed + after
        else:
            updated = current.rstrip() + "\n\n" + managed + "\n"
        if updated == current:
            return False
        put = client.put(endpoint, json={
            "message": "Update DevTown banner",
            "content": base64.b64encode(updated.encode("utf-8")).decode("ascii"),
            "sha": payload["sha"],
        })
        if put.status_code == 409:
            logger.warning("README sync conflict for %s; leaving user content unchanged", repository)
            return False
        put.raise_for_status()
        return True
