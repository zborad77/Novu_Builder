"""ORM model transakčního outboxu – sdílená infrastruktura událostí (SSE, timeline, offers)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    JSON,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import Identity

from app.platform.db.base import Base

# Stejný typ jako v app/modules/offers/models.py: JSONB na PostgreSQL, JSON jinde.
_JSONB = JSON().with_variant(JSONB(), "postgresql")


class OutboxEvent(Base):
    """Transactional outbox entry.

    Written in the SAME transaction as the state change that triggered it.
    A background publisher reads unpublished events and pushes them to Redis
    pub/sub. This guarantees at-least-once SSE delivery across worker restarts.

    Consumers (SSE stream) must deduplicate by event_id.
    """
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("idx_outbox_events_unpublished", "published", "created_at"),
        Index("idx_outbox_events_aggregate", "aggregate_type", "aggregate_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Monotonic sequence — included in every SSE frame as the event ID.
    # Qt client sends Last-Event-ID: {seq} on reconnect to replay missed events.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)

    payload: Mapped[dict] = mapped_column(_JSONB, nullable=False)

    published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default=text("false"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# N9: indexy, které vytvářejí migrace (produkční schéma), deklarované i v ORM,
# aby create_all (testy, dev) a autogenerate odpovídaly migracím.
Index("idx_outbox_events_seq", OutboxEvent.seq, unique=True)
