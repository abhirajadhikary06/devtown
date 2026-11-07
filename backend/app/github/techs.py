import json
import re
from functools import lru_cache
from pathlib import Path


@lru_cache
def catalogue():
    return json.loads((Path(__file__).parent.parent / "data" / "technologies.json").read_text())


def _has_token(text: str, token: str) -> bool:
    return re.search(r'(?<![\w@./-])' + re.escape(token) + r'(?![\w-])', text) is not None


def detect(repos: list[dict]) -> list[dict]:
    """repos: [{name, topics, root_files, manifests:{file:text}}]. Evidence is read from repository
    topics, dependency manifests and root file names. Everything found is 'verified' (we saw the evidence)."""
    found: dict[str, dict] = {}
    for r in repos:
        topics = {t.lower() for t in r.get("topics", [])}
        files = {f.lower() for f in r.get("root_files", [])}
        text = "\n".join(r.get("manifests", {}).values()).lower()
        for t in catalogue():
            ev = []
            if topics & set(t.get("topics", [])):
                ev.append("topic")
            if files & set(t.get("files", [])):
                ev.append("file")
            if any(_has_token(text, tok) for tok in t.get("tokens", [])):
                ev.append("manifest")
            if ev:
                e = found.setdefault(t["id"], {"id": t["id"], "name": t["name"], "category": t["category"],
                                                "facility": t["facility"], "status": "verified",
                                                "repos": [], "evidence": set()})
                e["repos"].append(r["name"])
                e["evidence"].update(ev)
    out = []
    for e in found.values():
        e["evidence"] = sorted(e["evidence"])
        e["repos"] = e["repos"][:8]
        out.append(e)
    return sorted(out, key=lambda e: (-len(e["repos"]), e["id"]))
