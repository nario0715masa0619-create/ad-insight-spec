"""add asset_data and evaluation_data columns

Revision ID: a1f7ccac7a04
Revises: 5ce6bc069419
Create Date: 2026-07-09 09:34:41.728843

Adds two nullable JSON columns to `ad_insights` as a forward-compatible
container for the future asset/evaluation split (see
docs/plans/asset_evaluation_split_phase2_tasks.md). No column has a default,
so every existing row gets NULL for both, and nothing in the write path
populates them yet (dual-write is a separate future phase). This migration
does not change any existing column or constraint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f7ccac7a04'
down_revision: Union[str, Sequence[str], None] = '5ce6bc069419'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('ad_insights', sa.Column('asset_data', sa.JSON(), nullable=True))
    op.add_column('ad_insights', sa.Column('evaluation_data', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('ad_insights', 'evaluation_data')
    op.drop_column('ad_insights', 'asset_data')
