"""Add latency metrics, rating, and summary to call_logs

Revision ID: c3d4e5f6a7b8
Revises: b2a3c4d5e6f7
Create Date: 2026-02-01

Adds performance metrics, call rating, and LLM-generated summary fields to call_logs table.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2a3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add latency metrics, rating, and summary columns to call_logs."""
    # Performance metrics
    op.add_column(
        "call_logs",
        sa.Column("stt_latency_p50_ms", sa.Float(), nullable=True),
    )
    op.add_column(
        "call_logs",
        sa.Column("llm_latency_p50_ms", sa.Float(), nullable=True),
    )
    op.add_column(
        "call_logs",
        sa.Column("tts_latency_p50_ms", sa.Float(), nullable=True),
    )
    op.add_column(
        "call_logs",
        sa.Column("barge_in_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "call_logs",
        sa.Column("total_turns", sa.Integer(), nullable=False, server_default="0"),
    )

    # Call rating and feedback
    op.add_column(
        "call_logs",
        sa.Column("call_rating", sa.Integer(), nullable=True),
    )
    op.add_column(
        "call_logs",
        sa.Column("caller_feedback", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "call_logs",
        sa.Column(
            "rating_method",
            sa.Enum("dtmf", "admin", "auto", name="ratingmethod"),
            nullable=True,
        ),
    )

    # Call summary
    op.add_column(
        "call_logs",
        sa.Column("call_summary", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "call_logs",
        sa.Column(
            "call_category",
            sa.Enum("booking", "inquiry", "complaint", "spam", "other", name="callcategory"),
            nullable=True,
        ),
    )

    # Add check constraint for call_rating (1-5)
    # Note: SQLite doesn't support adding constraints to existing tables well,
    # so we skip this for SQLite compatibility
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_call_rating_range",
            "call_logs",
            "call_rating >= 1 AND call_rating <= 5",
        )


def downgrade() -> None:
    """Remove latency metrics, rating, and summary columns from call_logs."""
    # Drop check constraint
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("ck_call_rating_range", "call_logs", type_="check")

    # Drop columns (in reverse order of creation)
    op.drop_column("call_logs", "call_category")
    op.drop_column("call_logs", "call_summary")
    op.drop_column("call_logs", "rating_method")
    op.drop_column("call_logs", "caller_feedback")
    op.drop_column("call_logs", "call_rating")
    op.drop_column("call_logs", "total_turns")
    op.drop_column("call_logs", "barge_in_count")
    op.drop_column("call_logs", "tts_latency_p50_ms")
    op.drop_column("call_logs", "llm_latency_p50_ms")
    op.drop_column("call_logs", "stt_latency_p50_ms")

    # Drop enums - only on PostgreSQL
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS callcategory")
        op.execute("DROP TYPE IF EXISTS ratingmethod")
