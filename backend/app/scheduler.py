"""Best-effort in-process schedule for opted-in towns."""
import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .api import services as svc
from .db import SessionLocal
from .lighting import resolve_mode
from .models import City, Snapshot, User

_STARTS = {"day": 6, "dusk": 18, "night": 21}
logger = logging.getLogger(__name__)


def _run_due_transitions() -> int:
    ran = 0
    with SessionLocal() as db:
        rows = db.execute(select(User, City).join(City, City.user_id == User.id)).all()
        for user, city in rows:
            data = dict(city.data)
            lighting = dict(data.get("lighting", {}))
            if not lighting.get("scheduled_auto_build"):
                continue
            try:
                zone = ZoneInfo(lighting.get("timezone", "UTC"))
            except Exception:
                zone = ZoneInfo("UTC")
            local = datetime.now(timezone.utc).astimezone(zone)
            mode = resolve_mode({"mode": "auto", "timezone": lighting.get("timezone", "UTC")}, local)
            if local.hour != _STARTS[mode] or local.minute != 0:
                continue
            marker = f"{local.date().isoformat()}:{mode}"
            if lighting.get("last_scheduled_transition") == marker:
                continue
            snapshot = db.scalar(select(Snapshot).where(Snapshot.user_id == user.id).order_by(Snapshot.id.desc()))
            if not snapshot:
                continue
            lighting["mode"] = "auto"
            lighting["last_scheduled_transition"] = marker
            lighting["scheduled_last_mode"] = mode
            data["lighting"] = lighting
            city.data = data
            city.version += 1
            svc.auto_build(db, city, user.id, snapshot.analysis["plan"])
            ran += 1
        db.commit()
    return ran


async def run():
    while True:
        try:
            await asyncio.to_thread(_run_due_transitions)
        except Exception:
            # A failed tick must not terminate the web process; the next tick retries.
            logger.exception("Scheduled town rebuild tick failed")
        await asyncio.sleep(30)
