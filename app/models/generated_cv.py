import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, LargeBinary, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.master_cv import CVVersion


class GeneratedCV(Base):
    __tablename__ = "generated_cvs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cv_versions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    job_title: Mapped[str] = mapped_column(String(200))
    job_description: Mapped[str] = mapped_column(Text)
    selection_explanation: Mapped[str] = mapped_column(Text)
    matched_keywords: Mapped[list[str]] = mapped_column(JSON)
    comparison: Mapped[list[str]] = mapped_column(JSON)
    content_blocks: Mapped[list[list[str]]] = mapped_column(JSON)
    review_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pdf_content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    docx_content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source_version: Mapped[CVVersion] = relationship(
        back_populates="generated_documents"
    )
