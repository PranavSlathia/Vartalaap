"""Add transcript review and improvement suggestion tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-01

Adds tables for the AI-powered transcript analysis system:
- transcript_reviews: QA reviews of call transcripts by AI agents
- improvement_suggestions: Actionable suggestions from reviews
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create transcript_reviews and improvement_suggestions tables."""
    # Create issue_category enum
    issue_category_enum = sa.Enum(
        "knowledge_gap",
        "prompt_weakness",
        "ux_issue",
        "stt_error",
        "tts_issue",
        "config_error",
        name="issuecategory",
    )

    # Create suggestion_status enum
    suggestion_status_enum = sa.Enum(
        "pending",
        "implemented",
        "rejected",
        "deferred",
        name="suggestionstatus",
    )

    # Create transcript_reviews table
    op.create_table(
        "transcript_reviews",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("call_log_id", sa.String(), nullable=False),
        sa.Column("business_id", sa.String(), nullable=False),
        sa.Column("quality_score", sa.Integer(), nullable=False),
        sa.Column("issues_json", sa.String(), nullable=True),
        sa.Column("suggestions_json", sa.String(), nullable=True),
        sa.Column("has_unanswered_query", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("has_knowledge_gap", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("has_prompt_weakness", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("has_ux_issue", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "agent_model",
            sa.String(),
            nullable=False,
            server_default="llama-3.3-70b-versatile",
        ),
        sa.Column("review_latency_ms", sa.Float(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_by", sa.String(), nullable=False, server_default="agent"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["call_log_id"], ["call_logs.id"]),
    )
    # Unique constraint prevents duplicate reviews from concurrent jobs
    op.create_index(
        "ix_transcript_reviews_call_log_id",
        "transcript_reviews",
        ["call_log_id"],
        unique=True,
    )
    op.create_index("ix_transcript_reviews_business_id", "transcript_reviews", ["business_id"])
    op.create_index("ix_transcript_reviews_reviewed_at", "transcript_reviews", ["reviewed_at"])

    # Create improvement_suggestions table
    op.create_table(
        "improvement_suggestions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("review_id", sa.String(), nullable=False),
        sa.Column("business_id", sa.String(), nullable=False),
        sa.Column("category", issue_category_enum, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("status", suggestion_status_enum, nullable=False, server_default="pending"),
        sa.Column("implemented_at", sa.DateTime(), nullable=True),
        sa.Column("implemented_by", sa.String(), nullable=True),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["review_id"], ["transcript_reviews.id"]),
    )
    op.create_index("ix_improvement_suggestions_review_id", "improvement_suggestions", ["review_id"])
    op.create_index("ix_improvement_suggestions_business_id", "improvement_suggestions", ["business_id"])
    op.create_index("ix_improvement_suggestions_status", "improvement_suggestions", ["status"])

    # Add check constraints for PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_quality_score_range",
            "transcript_reviews",
            "quality_score >= 1 AND quality_score <= 5",
        )
        op.create_check_constraint(
            "ck_priority_range",
            "improvement_suggestions",
            "priority >= 1 AND priority <= 5",
        )


def downgrade() -> None:
    """Drop transcript_reviews and improvement_suggestions tables."""
    bind = op.get_bind()

    # Drop check constraints on PostgreSQL
    if bind.dialect.name == "postgresql":
        op.drop_constraint("ck_priority_range", "improvement_suggestions", type_="check")
        op.drop_constraint("ck_quality_score_range", "transcript_reviews", type_="check")

    # Drop indexes and tables
    op.drop_index("ix_improvement_suggestions_status", "improvement_suggestions")
    op.drop_index("ix_improvement_suggestions_business_id", "improvement_suggestions")
    op.drop_index("ix_improvement_suggestions_review_id", "improvement_suggestions")
    op.drop_table("improvement_suggestions")

    op.drop_index("ix_transcript_reviews_reviewed_at", "transcript_reviews")
    op.drop_index("ix_transcript_reviews_business_id", "transcript_reviews")
    op.drop_index("ix_transcript_reviews_call_log_id", "transcript_reviews")
    op.drop_table("transcript_reviews")

    # Drop enums on PostgreSQL
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS suggestionstatus")
        op.execute("DROP TYPE IF EXISTS issuecategory")
