"""ORM models for the offer processing pipeline.

Additive parallel path — no changes to existing projects/cases system.

Hierarchy:
    OfferRequest   — one AI-driven pricing request submitted by the Qt client
        OfferJob       — one execution attempt (re-created on retry)
            AgentRun   — one call to an AI provider

Supporting tables:
    OutboxEvent          — transactional outbox for reliable SSE/event delivery
    OrganizationAiBudget — per-org token/cost limits for cost governance
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import Identity

_JSONB = JSON().with_variant(JSONB(), "postgresql")

from app.db.base import Base
from app.models.domain import TimestampMixin


# ---------------------------------------------------------------------------
# OfferRequest — the business entity submitted by the Qt client
# ---------------------------------------------------------------------------

class OfferRequest(TimestampMixin, Base):
    """A single AI pricing request submitted by the Qt client.

    Lifecycle: submitted → queued → processing → needs_review → completed
                                               → needs_more_info → queued
                                               → failed
    Any non-terminal state → cancelled.
    """
    __tablename__ = "offer_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'submitted','queued','processing',"
            "'needs_more_info','needs_review','completed','failed','cancelled')",
            name="ck_offer_requests_status",
        ),
        UniqueConstraint("organization_id", "idempotency_key", name="uq_offer_requests_idempotency"),
        Index("idx_offer_requests_org_status", "organization_id", "status"),
        Index("idx_offer_requests_org_created", "organization_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[str | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL")
    )
    submitted_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    work_type_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters: Mapped[dict | None] = mapped_column(_JSONB)
    photo_ids: Mapped[list | None] = mapped_column(_JSONB)

    status: Mapped[str] = mapped_column(String(32), default="submitted", nullable=False)

    auto_send: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_review_bypass: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    needs_more_info_payload: Mapped[dict | None] = mapped_column(_JSONB)
    result_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # Qt client version that submitted this request — for backward-compat tracking
    client_version: Mapped[str | None] = mapped_column(String(32))

    jobs: Mapped[list["OfferJob"]] = relationship(
        back_populates="offer_request",
        cascade="all, delete-orphan",
        order_by="OfferJob.created_at",
    )


# ---------------------------------------------------------------------------
# OfferJob — one execution attempt for an OfferRequest
# ---------------------------------------------------------------------------

class OfferJob(TimestampMixin, Base):
    """Execution layer: one job per processing attempt.

    A new OfferJob is created for each retry so attempt history is preserved.
    """
    __tablename__ = "offer_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','completed','failed','cancelled')",
            name="ck_offer_jobs_status",
        ),
        UniqueConstraint("idempotency_key", name="uq_offer_jobs_idempotency"),
        Index("idx_offer_jobs_request_status", "offer_request_id", "status"),
        Index("idx_offer_jobs_org_status", "organization_id", "status"),
        Index("idx_offer_jobs_next_retry", "next_retry_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    offer_request_id: Mapped[str] = mapped_column(
        ForeignKey("offer_requests.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)

    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_detail: Mapped[str | None] = mapped_column(Text)
    # Consecutive failures with the same error_code.
    # When >= POISON_THRESHOLD the worker skips remaining retries.
    error_repeat_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    worker_id: Mapped[str | None] = mapped_column(String(128))
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Fencing token: incremented on each mark_job_running; Phase-3 persist
    # checks WHERE lease_version = :expected to abort stale-worker writes.
    lease_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    offer_request: Mapped["OfferRequest"] = relationship(back_populates="jobs")
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="offer_job",
        cascade="all, delete-orphan",
        order_by="AgentRun.created_at",
    )


# ---------------------------------------------------------------------------
# AgentRun — one call to an AI provider
# ---------------------------------------------------------------------------

class AgentRun(Base):
    """Immutable record of a single AI provider invocation.

    Security invariant: the agent receives ONLY input_snapshot_key (a frozen,
    organization-anonymized copy of the offer data). No organization names,
    customer PII, or cross-tenant data ever reaches the agent.
    """
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    offer_job_id: Mapped[str] = mapped_column(
        ForeignKey("offer_jobs.id", ondelete="CASCADE"), nullable=False
    )
    offer_request_id: Mapped[str] = mapped_column(
        ForeignKey("offer_requests.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )

    # Frozen input — agent ONLY receives this key, never raw tenant data
    input_snapshot_key: Mapped[str | None] = mapped_column(String(512))
    input_snapshot_hash: Mapped[str | None] = mapped_column(String(64))

    # Version context — what versions were active when this run happened
    snapshot_version_context: Mapped[dict | None] = mapped_column(_JSONB)

    # Provider info
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_model: Mapped[str | None] = mapped_column(String(128))
    agent_model_build: Mapped[str | None] = mapped_column(String(128))

    # Token accounting (for cost control)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))

    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(32))

    raw_output: Mapped[dict | None] = mapped_column(_JSONB)
    parsed_output: Mapped[dict | None] = mapped_column(_JSONB)
    validation_errors: Mapped[list | None] = mapped_column(_JSONB)
    error_detail: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    offer_job: Mapped["OfferJob"] = relationship(back_populates="agent_runs")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_agent_runs_status",
        ),
        CheckConstraint(
            "outcome IN ('offer_generated','insufficient_data','error','cancelled')",
            name="ck_agent_runs_outcome",
        ),
        # One job → at most one agent run (idempotent persist guard)
        UniqueConstraint("offer_job_id", name="uq_agent_runs_offer_job"),
        Index("idx_agent_runs_job", "offer_job_id"),
        Index("idx_agent_runs_request", "offer_request_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# OutboxEvent — transactional outbox for reliable SSE / event delivery
# ---------------------------------------------------------------------------

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

    published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# AiBudgetReservation — per-job reservation tracking for crash-safe release
# ---------------------------------------------------------------------------

class AiBudgetReservation(Base):
    """Tracks one token reservation for a single offer job.

    Status machine:
        reserved → consumed   (AI completed, record_actual() called)
        reserved → released   (controlled failure, release() called)
        reserved → expired    (sweeper found stale reservation after crash)

    UNIQUE(offer_job_id) prevents double-reservation of the same job.
    The sweeper recovers tokens for any row still 'reserved' after
    RESERVATION_EXPIRY_MINUTES.
    """
    __tablename__ = "ai_budget_reservations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('reserved','consumed','released','expired')",
            name="ck_ai_budget_res_status",
        ),
        UniqueConstraint("offer_job_id", name="uq_ai_budget_res_job"),
        Index("idx_ai_budget_res_stale", "status", "reserved_at"),
        Index("idx_ai_budget_res_org", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    offer_job_id: Mapped[str] = mapped_column(
        ForeignKey("offer_jobs.id", ondelete="CASCADE"), nullable=False
    )
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="reserved", nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# OrganizationAiBudget — cost governance per tenant
# ---------------------------------------------------------------------------

class OrganizationAiBudget(TimestampMixin, Base):
    """Per-organization AI budget limits.

    The daily_tokens_used counter is incremented atomically (UPDATE ... WHERE
    daily_tokens_used + :estimate <= daily_token_limit) before any AI call.
    This prevents race conditions where two concurrent requests both pass a
    read-then-check pattern.
    """
    __tablename__ = "organization_ai_budgets"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_org_ai_budgets_org"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )

    # Hard limits — enforced before inference
    daily_token_limit: Mapped[int] = mapped_column(Integer, default=200_000, nullable=False)
    monthly_cost_limit_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("500.00"), nullable=False
    )

    # Soft alert threshold (0–100)
    alert_threshold_pct: Mapped[int] = mapped_column(Integer, default=80, nullable=False)

    # Rolling counters (reset by scheduled task)
    daily_tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    monthly_cost_used_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False
    )
    daily_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # If False, budget exhaustion only triggers an alert (warn mode)
    is_hard_limit: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
