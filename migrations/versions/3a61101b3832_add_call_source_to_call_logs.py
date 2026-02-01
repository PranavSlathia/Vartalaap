"""add_call_source_to_call_logs

Revision ID: 3a61101b3832
Revises: d4e5f6a7b8c9
Create Date: 2026-02-02 00:09:33.891696

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = '3a61101b3832'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add missing columns (some already exist in DB)
    op.add_column('call_logs', sa.Column('caller_feedback', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True))
    op.add_column('call_logs', sa.Column('rating_method', sa.Enum('dtmf', 'admin', 'auto', name='ratingmethod'), nullable=True))
    op.add_column('call_logs', sa.Column('call_summary', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True))
    op.add_column('call_logs', sa.Column('call_category', sa.Enum('booking', 'inquiry', 'complaint', 'spam', 'other', name='callcategory'), nullable=True))
    op.add_column('call_logs', sa.Column('call_source', sa.Enum('phone', 'voice_test', name='callsource'), nullable=False, server_default='phone'))
    op.create_index(op.f('ix_call_logs_call_source'), 'call_logs', ['call_source'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_call_logs_call_source'), table_name='call_logs')
    op.drop_column('call_logs', 'call_source')
    op.drop_column('call_logs', 'call_category')
    op.drop_column('call_logs', 'call_summary')
    op.drop_column('call_logs', 'rating_method')
    op.drop_column('call_logs', 'caller_feedback')
