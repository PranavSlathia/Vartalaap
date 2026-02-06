"""add voice/rag profile columns to businesses

Revision ID: 5f7a9c1d2e3f
Revises: 3a61101b3832
Create Date: 2026-02-06 22:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5f7a9c1d2e3f"
down_revision: Union[str, Sequence[str], None] = "3a61101b3832"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("businesses", sa.Column("voice_profile_json", sa.String(), nullable=True))
    op.add_column("businesses", sa.Column("rag_profile_json", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("businesses", "rag_profile_json")
    op.drop_column("businesses", "voice_profile_json")
