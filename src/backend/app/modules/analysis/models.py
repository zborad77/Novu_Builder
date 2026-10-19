"""ORM modely modulu analysis: analytické joby a jejich výsledky."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.base import Base

if TYPE_CHECKING:
    from app.modules.quoting.public import QuoteVariant
    from app.modules.cases.public import Project
    from app.modules.identity.public import User


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'canceled', 'dead_letter')",
            name="ck_analysis_jobs_status",
        ),
        Index(
            "idx_analysis_jobs_project_status_created_id",
            "project_id",
            "status",
            "created_at",
            "id",
        ),
        Index(
            "idx_analysis_jobs_project_created_id",
            "project_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_work_type_code: Mapped[str | None] = mapped_column(String(64))
    analysis_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="SET NULL")
    )
    resolved_analysis_profile_code: Mapped[str | None] = mapped_column(String(64))
    resolved_analysis_profile_version: Mapped[int | None] = mapped_column(Integer)
    requested_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    parent_job_id: Mapped[str | None] = mapped_column(String(64))   # set when this is a retry
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(128))
    worker_id: Mapped[str | None] = mapped_column(String(255))
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_traceback: Mapped[str | None] = mapped_column(Text)       # full traceback
    input_payload: Mapped[str | None] = mapped_column(Text)         # JSON: co šlo do AI
    input_payload_storage_key: Mapped[str | None] = mapped_column(String(512))
    output_summary: Mapped[str | None] = mapped_column(Text)        # JSON: co přišlo zpět
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="analysis_jobs")
    requested_by_user: Mapped["User | None"] = relationship(back_populates="analysis_jobs")
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(back_populates="analysis_job")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    __table_args__ = (
        Index(
            "idx_analysis_results_project_created_id",
            "project_id",
            "created_at",
            "id",
        ),
        Index(
            "idx_analysis_results_job_created_id",
            "analysis_job_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    analysis_job_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="SET NULL"))
    resolved_work_type_code: Mapped[str | None] = mapped_column(String(64))
    analysis_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("catalog_analysis_profiles.id", ondelete="SET NULL")
    )
    resolved_analysis_profile_code: Mapped[str | None] = mapped_column(String(64))
    resolved_analysis_profile_version: Mapped[int | None] = mapped_column(Integer)
    reference_photo_id: Mapped[str | None] = mapped_column(ForeignKey("project_photos.id", ondelete="SET NULL"))
    object_type: Mapped[str | None] = mapped_column(String(64))
    surface_condition: Mapped[str | None] = mapped_column(String(64))
    recommended_scope: Mapped[str | None] = mapped_column(String(64))
    estimated_quantity: Mapped[float | None] = mapped_column(Float)
    estimated_unit: Mapped[str | None] = mapped_column(String(32))
    estimated_area_sqm: Mapped[float | None] = mapped_column(Float)
    area_confidence: Mapped[float | None] = mapped_column(Float)
    selected_repair_polygon_json: Mapped[str | None] = mapped_column(Text)
    manual_area_sqm: Mapped[float | None] = mapped_column(Float)
    final_area_source: Mapped[str] = mapped_column(String(32), default="ai", nullable=False)
    mask_polygon_json: Mapped[str | None] = mapped_column(Text)
    materials_suggestion_json: Mapped[str | None] = mapped_column(Text)
    workflow_suggestion_json: Mapped[str | None] = mapped_column(Text)
    estimated_duration_days: Mapped[float | None] = mapped_column(Float)
    labor_hours_total: Mapped[float | None] = mapped_column(Float)
    model_name: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="analysis_results")
    analysis_job: Mapped["AnalysisJob | None"] = relationship(back_populates="analysis_results")
    quote_variants: Mapped[list["QuoteVariant"]] = relationship(back_populates="analysis_result")
