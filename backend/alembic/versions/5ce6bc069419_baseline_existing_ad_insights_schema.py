"""baseline existing ad_insights schema

Revision ID: 5ce6bc069419
Revises:
Create Date: 2026-07-09 09:33:50.195135

This migration reproduces the `ad_insights` table exactly as it is created
today by `Base.metadata.create_all()` (see app/main.py). It exists so that
Alembic has a starting point (revision history root) to build on.

- Fresh/local/test DBs: this migration actually creates the table when
  running `alembic upgrade head` against an empty database.
- The existing production DB (created via `create_all`, never via Alembic)
  already has this exact table. It must NOT be re-created there. Instead,
  production should be marked as already being at this revision via
  `alembic stamp 5ce6bc069419` before running any later migration
  (see docs/DEPLOYMENT.md).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ce6bc069419'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ad_insights',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.String(length=100), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('format', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('spec_data', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', 'version', name='uq_asset_id_version'),
    )
    op.create_index(op.f('ix_ad_insights_id'), 'ad_insights', ['id'], unique=False)
    op.create_index(op.f('ix_ad_insights_asset_id'), 'ad_insights', ['asset_id'], unique=False)
    op.create_index(op.f('ix_ad_insights_format'), 'ad_insights', ['format'], unique=False)
    op.create_index(op.f('ix_ad_insights_created_at'), 'ad_insights', ['created_at'], unique=False)
    op.create_index(op.f('ix_ad_insights_is_deleted'), 'ad_insights', ['is_deleted'], unique=False)
    op.create_index('idx_asset_id_created', 'ad_insights', ['asset_id', 'created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_asset_id_created', table_name='ad_insights')
    op.drop_index(op.f('ix_ad_insights_is_deleted'), table_name='ad_insights')
    op.drop_index(op.f('ix_ad_insights_created_at'), table_name='ad_insights')
    op.drop_index(op.f('ix_ad_insights_format'), table_name='ad_insights')
    op.drop_index(op.f('ix_ad_insights_asset_id'), table_name='ad_insights')
    op.drop_index(op.f('ix_ad_insights_id'), table_name='ad_insights')
    op.drop_table('ad_insights')
