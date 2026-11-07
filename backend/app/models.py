from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

Json = JSON().with_variant(JSONB(), "postgresql")
now = lambda: datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    github_id: Mapped[int] = mapped_column(Integer, unique=True)
    login: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    token_enc: Mapped[str | None] = mapped_column(Text)       # Fernet-encrypted OAuth token
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Snapshot(Base):
    __tablename__ = "snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    data: Mapped[dict] = mapped_column(Json)
    analysis: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class City(Base):
    __tablename__ = "cities"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    seed: Mapped[int] = mapped_column(Integer)
    gen_version: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)   # bumped on every meaningful change (banner cache key)
    data: Mapped[dict] = mapped_column(Json)                   # {unlocked, items, next_id, unlocks, level, deferred}
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Banner(Base):
    __tablename__ = "banners"
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    png: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Ledger(Base):
    """Append-only resource transaction ledger. Balance = SUM(amount) per resource."""
    __tablename__ = "ledger"
    __table_args__ = (UniqueConstraint("user_id", "idem_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resource: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(120))
    idem_key: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
