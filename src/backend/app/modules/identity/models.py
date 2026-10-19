"""ORM modely modulu identity: organizace (tenant), uživatelé, session a tokeny."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modules.identity.token_limits import JTI_MAX_LENGTH
from app.platform.db.base import Base
from app.platform.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.modules.analysis.public import AnalysisJob
    from app.modules.catalog.public import MaterialCatalog, PricingProfile, Supplier
    from app.modules.cases.public import Client, Project


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    ico: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    default_currency: Mapped[str] = mapped_column(String(8), default="CZK", nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    clients: Mapped[list["Client"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    projects: Mapped[list["Project"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    pricing_profiles: Mapped[list["PricingProfile"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    material_catalog: Mapped[list["MaterialCatalog"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    suppliers: Mapped[list["Supplier"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Mirrors app.modules.identity.rbac.ALL_ROLES; added by migration 20261017_0057.
        CheckConstraint(
            "role IN ('superadmin', 'admin', 'manager', 'technician')",
            name="ck_users_role_valid",
        ),
        # The role string alone never grants platform administration.
        CheckConstraint(
            "role <> 'superadmin' OR is_superadmin",
            name="ck_users_superadmin_requires_flag",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tokens_valid_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="users")
    created_projects: Mapped[list["Project"]] = relationship(
        back_populates="created_by_user",
        foreign_keys="Project.created_by_user_id",
    )
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(back_populates="requested_by_user")


class RevokedToken(Base):
    """Blocklist for revoked JWT tokens. Checked on every authenticated request."""
    __tablename__ = "revoked_tokens"
    __table_args__ = (
        Index("ix_revoked_tokens_expires_at", "expires_at"),
    )

    jti: Mapped[str] = mapped_column(String(JTI_MAX_LENGTH), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserSession(Base):
    """Persisted login session metadata for per-session revocation and auditability."""
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_user_created_at", "user_id", "created_at"),
        Index("ix_user_sessions_refresh_expires_at", "refresh_expires_at"),
        Index("ix_user_sessions_revoked_at", "revoked_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    access_jti: Mapped[str] = mapped_column(String(JTI_MAX_LENGTH), unique=True, nullable=False)
    refresh_jti: Mapped[str] = mapped_column(String(JTI_MAX_LENGTH), unique=True, nullable=False)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship()


class RolePermission(Base):
    """DB-backed role → capability mapping for granular RBAC (C8).

    Seeded with defaults on first migration. Superadmin always has all
    capabilities regardless of this table (enforced in deps.py).
    """
    __tablename__ = "role_permissions"

    role: Mapped[str] = mapped_column(String(64), primary_key=True)
    capability: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PasswordResetToken(Base):
    """Single-use token for the email-based password reset flow (C7).

    Created by POST /auth/forgot-password; consumed by POST /auth/reset-password.
    The raw token must never be persisted: the token column stores a SHA-256
    digest, and expired or already-used tokens must never be accepted.
    """
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("ix_password_reset_tokens_expires_at", "expires_at"),
        Index(
            "uq_password_reset_tokens_user_id_unused",
            "user_id",
            unique=True,
            postgresql_where=text("used_at IS NULL"),
            sqlite_where=text("used_at IS NULL"),
        ),
    )

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship()
