"""ORM modely modulu cases: klient, zakázka a historie jejích stavů."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.base import Base
from app.platform.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.modules.analysis.public import AnalysisJob, AnalysisResult
    from app.modules.quoting.public import ProjectFinalProposal, ProjectProposalDraft, QuoteVariant
    from app.modules.exports.public import ProjectExport
    from app.modules.media.public import ProjectPhoto
    from app.modules.identity.public import Organization, User


class Client(TimestampMixin, Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)

    organization: Mapped["Organization"] = relationship(back_populates="clients")
    projects: Mapped[list["Project"]] = relationship(back_populates="client")


class Project(TimestampMixin, Base):
    """A case (zakázka) moving through the estimation workflow.

    Status state machine
    --------------------
    draft          → intake | cancelled
    intake         → analyzing | draft | cancelled
    analyzing      → proposal_ready | quote_ready | draft | cancelled
    proposal_ready → quote_ready | draft | cancelled
    quote_ready    → sent | draft | cancelled
    sent           → archived | draft | cancelled
    archived       terminal — work accepted / completed
    cancelled      terminal — explicitly abandoned

    Locking: cases in {analyzing, proposal_ready, quote_ready, sent} are locked —
    photo uploads and parameter edits are rejected until back in draft.
    """
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'draft','intake','analyzing','proposal_ready',"
            "'quote_ready','sent','archived','cancelled')",
            name="ck_projects_status",
        ),
        Index("idx_projects_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"))
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), default="draft", nullable=False)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_changed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    property_type: Mapped[str | None] = mapped_column(String(64))
    repair_scope: Mapped[str | None] = mapped_column(String(64))
    location_lat: Mapped[float | None] = mapped_column(Float)
    location_lng: Mapped[float | None] = mapped_column(Float)
    address_label: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(32), default="mobile", nullable=False, server_default="mobile")
    reference_expectations_json: Mapped[str | None] = mapped_column(Text)

    organization: Mapped["Organization"] = relationship(back_populates="projects")
    client: Mapped["Client | None"] = relationship(back_populates="projects")
    created_by_user: Mapped["User"] = relationship(back_populates="created_projects", foreign_keys=[created_by_user_id])
    photos: Mapped[list["ProjectPhoto"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    quote_variants: Mapped[list["QuoteVariant"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    proposal_draft: Mapped["ProjectProposalDraft | None"] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False,
    )
    exports: Mapped[list["ProjectExport"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    final_proposals: Mapped[list["ProjectFinalProposal"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    status_history: Mapped[list["ProjectStatusHistory"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectStatusHistory.transitioned_at",
    )


class ProjectStatusHistory(Base):
    """Immutable log of every Project status transition.

    Written by the transition engine; never updated or deleted (audit trail).
    """
    __tablename__ = "project_status_history"
    __table_args__ = (
        Index("idx_psh_project_transitioned", "project_id", "transitioned_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(64))          # NULL for the initial draft entry
    to_status: Mapped[str] = mapped_column(String(64), nullable=False)
    transitioned_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(String(255))              # optional human note
    transitioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="status_history")
    transitioned_by_user: Mapped["User | None"] = relationship()
