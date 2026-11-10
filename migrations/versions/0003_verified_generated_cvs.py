"""Verify immutable CV sources and retain generated document snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "0003_verified_cvs"
down_revision = "0002_cv_profile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.add_column(
        "cv_versions", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "generated_cvs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_version_id", sa.Uuid(),
            sa.ForeignKey("cv_versions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("job_title", sa.String(200), nullable=False),
        sa.Column("job_description", sa.Text(), nullable=False),
        sa.Column("selection_explanation", sa.Text(), nullable=False),
        sa.Column("matched_keywords", sa.JSON(), nullable=False),
        sa.Column("comparison", sa.JSON(), nullable=False),
        sa.Column("content_blocks", sa.JSON(), nullable=False),
        sa.Column("pdf_content", sa.LargeBinary(), nullable=False),
        sa.Column("docx_content", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_generated_cvs_source_version_id", "generated_cvs", ["source_version_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_generated_cvs_source_version_id", table_name="generated_cvs")
    op.drop_table("generated_cvs")
    op.drop_column("cv_versions", "verified_at")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_table("audit_logs")
