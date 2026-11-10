import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class MasterCV(Base):
    __tablename__ = "master_cvs"
    __table_args__ = (
        UniqueConstraint("user_id", "slot", name="uq_master_cv_user_slot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    versions: Mapped[list["CVVersion"]] = relationship(
        back_populates="master_cv", cascade="all, delete-orphan",
        order_by="CVVersion.version",
    )


class CVVersion(Base):
    __tablename__ = "cv_versions"
    __table_args__ = (
        UniqueConstraint("master_cv_id", "version", name="uq_cv_version_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    master_cv_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("master_cvs.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_sections: Mapped[dict[str, list[str]]] = mapped_column(
        JSON, nullable=False
    )
    review_flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_history: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)

    master_cv: Mapped[MasterCV] = relationship(back_populates="versions")
    generated_documents: Mapped[list["GeneratedCV"]] = relationship(
        cascade="all, delete-orphan", back_populates="source_version"
    )
