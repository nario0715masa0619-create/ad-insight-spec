"""add asset_version to verification_cases

Revision ID: d04670158813
Revises: 180b9b618513
Create Date: 2026-07-26 00:00:00.000000

Adds `verification_cases.asset_version` so that a case pinned to an
ad_insights analysis (asset_id) also records the exact version that was
presented at the hearing. Without this, if the same asset_id gets
re-analyzed later, `asset_id` alone would silently resolve to whatever is
"latest" at read time instead of what was actually shown to the client.

A CHECK constraint enforces "asset_version is required whenever asset_id is
set" at the DB layer (in addition to Pydantic-level validation in
app/schemas/verification.py), as a safety net for any future write path
that bypasses the API. Existing rows (asset_id set, asset_version NULL, if
any) would violate this constraint going forward — there should be none
yet since this feature has not shipped to production.

Uses batch mode because SQLite cannot add a multi-column CHECK constraint
via plain ALTER TABLE; batch mode falls back to copy-and-recreate on
SQLite and emits plain ALTER TABLE on Postgres.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd04670158813'
down_revision: Union[str, Sequence[str], None] = '180b9b618513'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('verification_cases') as batch_op:
        batch_op.add_column(sa.Column('asset_version', sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            'ck_verification_cases_asset_version_required_with_asset_id',
            'asset_id IS NULL OR asset_version IS NOT NULL',
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('verification_cases') as batch_op:
        batch_op.drop_constraint('ck_verification_cases_asset_version_required_with_asset_id', type_='check')
        batch_op.drop_column('asset_version')
