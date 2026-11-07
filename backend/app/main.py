from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from .api.routes import router
from .config import settings
from .db import Base, engine


@asynccontextmanager
async def lifespan(app):
    if settings.database_url.startswith("sqlite"):   # dev convenience; production uses `alembic upgrade head`
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title="DevTown", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, https_only=settings.cookie_secure, same_site="lax", max_age=60 * 60 * 24 * 30)
app.include_router(router)
