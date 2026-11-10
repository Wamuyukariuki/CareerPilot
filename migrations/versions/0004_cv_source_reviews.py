"""Versioned source-linked CV reviews and export revision binding."""
from alembic import op
import sqlalchemy as sa

revision = "0004_cv_reviews"
down_revision = "0003_verified_cvs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cv_versions",
        sa.Column("review_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "cv_versions",
        sa.Column("review_history", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "generated_cvs",
        sa.Column("review_revision", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("generated_cvs", "review_revision")
    op.drop_column("cv_versions", "review_history")
    op.drop_column("cv_versions", "review_revision")
