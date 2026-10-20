"""ORM modely modulu media: fotografie zakázky a značky (markery) na nich."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.base import Base

if TYPE_CHECKING:
    from app.modules.cases.public import Project


class ProjectPhoto(Base):
    __tablename__ = "project_photos"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'pending_delete', 'purge_pending', 'deleted')",
            name="ck_project_photos_status",
        ),
        CheckConstraint(
            "processing_status IN ('uploaded', 'processing', 'ready', 'failed')",
            name="ck_project_photos_processing_status",
        ),
        Index("idx_project_photos_project_id", "project_id"),
        Index(
            "idx_project_photos_project_sort_created",
            "project_id",
            "sort_order",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, server_default=text("'active'"))
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    preview_storage_key: Mapped[str | None] = mapped_column(String(512))
    ai_input_storage_key: Mapped[str | None] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    preview_file_size: Mapped[int | None] = mapped_column(Integer)
    preview_width: Mapped[int | None] = mapped_column(Integer)
    preview_height: Mapped[int | None] = mapped_column(Integer)
    ai_input_file_size: Mapped[int | None] = mapped_column(Integer)
    ai_input_width: Mapped[int | None] = mapped_column(Integer)
    ai_input_height: Mapped[int | None] = mapped_column(Integer)
    processing_status: Mapped[str] = mapped_column(String(64), default="ready", nullable=False)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exif_lat: Mapped[float | None] = mapped_column(Float)
    exif_lng: Mapped[float | None] = mapped_column(Float)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_analysis_reference: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    # Soft delete (20261017_0058): a pending_delete photo stays restorable until
    # PHOTO_DELETE_RETENTION_HOURS after deleted_at, then the worker purges storage.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Set by the server from the authenticated uploader (20261017_0059). NULL for
    # photos uploaded before then or whose author account was removed; such
    # photos are managed by managers/company admins only.
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    project: Mapped["Project"] = relationship(back_populates="photos")


class Marker(Base):
    """User/AI annotation on a project photo or case (normalized 0-1 coordinates).

    marker_source controls mutability:
      'user' — created by a human operator, editable
      'ai'   — written by the analysis pipeline, immutable / append-only
    Who exactly created it (role, superadmin) is derivable from created_by → users.
    """
    __tablename__ = "markers"
    __table_args__ = (
        CheckConstraint(
            "marker_type IN ('defect', 'note', 'ai_detection', 'measurement')",
            name="ck_markers_marker_type",
        ),
        CheckConstraint(
            "marker_source IN ('user', 'ai')",
            name="ck_markers_marker_source",
        ),
        Index("idx_markers_case_id", "case_id"),
        Index("idx_markers_image_id", "image_id"),
        Index("idx_markers_case_type", "case_id", "marker_type"),
        Index("idx_markers_case_source", "case_id", "marker_source"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    image_id: Mapped[str | None] = mapped_column(ForeignKey("project_photos.id", ondelete="SET NULL"))
    marker_type: Mapped[str] = mapped_column(String(32), nullable=False)
    marker_source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="user")
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[float | None] = mapped_column(Float)
    height: Mapped[float | None] = mapped_column(Float)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str | None] = mapped_column(String(32))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
