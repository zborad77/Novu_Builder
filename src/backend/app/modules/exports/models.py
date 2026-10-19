"""ORM model modulu exports: vygenerované exporty a archivy zakázky."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.base import Base

if TYPE_CHECKING:
    from app.modules.cases.models import Project


class ProjectExport(Base):
    __tablename__ = "project_exports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'generating', 'completed', 'failed')",
            name="ck_project_exports_status",
        ),
        Index("idx_project_exports_project_id", "project_id"),
        Index("idx_project_exports_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    export_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="exports")
