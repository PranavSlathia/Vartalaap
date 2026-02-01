"""Add multi-business and knowledge base tables

Revision ID: b2a3c4d5e6f7
Revises: cafe78f9263c
Create Date: 2026-02-01

Adds:
- businesses: Multi-tenant business configuration
- business_phone_numbers: Phone-to-business mapping for call routing
- knowledge_items: Knowledge base items for RAG retrieval
"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2a3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "cafe78f9263c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create multi-business and knowledge base tables."""
    # Create businesses table
    op.create_table(
        "businesses",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column(
            "type",
            sa.Enum("restaurant", "clinic", "salon", "other", name="businesstype"),
            nullable=False,
        ),
        sa.Column(
            "timezone", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum("active", "suspended", "onboarding", name="businessstatus"),
            nullable=False,
        ),
        sa.Column(
            "phone_numbers_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column(
            "operating_hours_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column(
            "reservation_rules_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column(
            "greeting_text", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True
        ),
        sa.Column(
            "menu_summary", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True
        ),
        sa.Column(
            "admin_password_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_businesses_status"), "businesses", ["status"], unique=False
    )

    # Create business_phone_numbers table
    op.create_table(
        "business_phone_numbers",
        sa.Column(
            "phone_number",
            sqlmodel.sql.sqltypes.AutoString(length=20),
            nullable=False,
        ),
        sa.Column(
            "business_id", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False
        ),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
        ),
        sa.PrimaryKeyConstraint("phone_number"),
    )
    op.create_index(
        op.f("ix_business_phone_numbers_business_id"),
        "business_phone_numbers",
        ["business_id"],
        unique=False,
    )

    # Create knowledge_items table
    op.create_table(
        "knowledge_items",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "business_id", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False
        ),
        sa.Column(
            "category",
            sa.Enum("menu_item", "faq", "policy", "announcement", name="knowledgecategory"),
            nullable=False,
        ),
        sa.Column(
            "title", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False
        ),
        sa.Column(
            "title_hindi",
            sqlmodel.sql.sqltypes.AutoString(length=200),
            nullable=True,
        ),
        sa.Column(
            "content", sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=False
        ),
        sa.Column(
            "content_hindi",
            sqlmodel.sql.sqltypes.AutoString(length=2000),
            nullable=True,
        ),
        sa.Column(
            "metadata_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column(
            "embedding_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_knowledge_items_business_id"),
        "knowledge_items",
        ["business_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_items_category"),
        "knowledge_items",
        ["category"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_items_is_active"),
        "knowledge_items",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    """Drop multi-business and knowledge base tables."""
    # Drop knowledge_items
    op.drop_index(op.f("ix_knowledge_items_is_active"), table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_category"), table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_business_id"), table_name="knowledge_items")
    op.drop_table("knowledge_items")

    # Drop business_phone_numbers
    op.drop_index(
        op.f("ix_business_phone_numbers_business_id"),
        table_name="business_phone_numbers",
    )
    op.drop_table("business_phone_numbers")

    # Drop businesses
    op.drop_index(op.f("ix_businesses_status"), table_name="businesses")
    op.drop_table("businesses")

    # Drop enums - only on PostgreSQL (SQLite doesn't have types)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS knowledgecategory")
        op.execute("DROP TYPE IF EXISTS businessstatus")
        op.execute("DROP TYPE IF EXISTS businesstype")
