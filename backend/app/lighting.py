"""Shared local-time lighting schedule for town and banner renders."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MODES = {"auto", "day", "dusk", "night"}
DEFAULT_PREFERENCES = {"mode": "auto", "timezone": "UTC"}


def resolve_mode(preferences: dict | None, now: datetime | None = None) -> str:
    preferences = preferences or DEFAULT_PREFERENCES
    mode = preferences.get("mode", "auto")
    if mode in ("day", "dusk", "night"):
        return mode
    try:
        zone = ZoneInfo(preferences.get("timezone", "UTC"))
    except Exception:
        zone = ZoneInfo("UTC")
    hour = (now or datetime.now(timezone.utc)).astimezone(zone).hour
    if 6 <= hour < 18:
        return "day"
    if 18 <= hour < 21:
        return "dusk"
    return "night"


def banner_revision(city_version: int, mode: str) -> int:
    return city_version * 10 + {"day": 1, "dusk": 2, "night": 3}[mode]
