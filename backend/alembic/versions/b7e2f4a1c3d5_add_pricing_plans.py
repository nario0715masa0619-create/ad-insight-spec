"""add pricing_plans table and company plan association

Revision ID: b7e2f4a1c3d5
Revises: f3a1c9d2e8b0
Create Date: 2026-08-08 00:00:00.000000

Second stage of the credit-based quota work (f3a1c9d2e8b0): externalizes
plan definitions (Starter/Growth/Pro/Monitor/Enterprise-style) into a
`pricing_plans` table instead of hardcoding names/prices/credit grants in
code. `monitor_companies.plan_id` links a company to a plan, and
`monitor_companies.monthly_credit_limit` is loosened from NOT NULL to
nullable: NULL now means "no per-company override, defer to the plan (or
the hardcoded fallback if there's no plan either)" instead of always being
a concrete number. See app/repositories/monitor_repository.py::
resolve_monthly_credit_limit for the override > plan > fallback resolution
order this enables.

This PR (still open/unreleased, same as f3a1c9d2e8b0) has not been applied
to any real database yet, so no backfill of existing monitor_companies rows
is needed for the upgrade path itself — but the downgrade path still
backfills any NULLs to a concrete value before re-adding the NOT NULL
constraint, since a hypothetical future downgrade after real data exists
must not violate it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2f4a1c3d5'
down_revision: Union[str, Sequence[str], None] = 'f3a1c9d2e8b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# resolve_monthly_credit_limit()の最終フォールバックと同じ値。downgrade時に
# NULLをNOT NULLへ戻す際の埋め値として使う（=downgrade後もPR#91相当のデフォルトに一致する）。
_LEGACY_DEFAULT_CREDIT_LIMIT = 100


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pricing_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('monthly_price_jpy', sa.Integer(), nullable=True),
        sa.Column('monthly_credit_limit', sa.Integer(), nullable=False),
        sa.Column('marketing_note', sa.Text(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False),
        sa.Column('effective_from', sa.DateTime(), nullable=True),
        sa.Column('effective_to', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index(op.f('ix_pricing_plans_code'), 'pricing_plans', ['code'], unique=True)

    with op.batch_alter_table('monitor_companies') as batch_op:
        batch_op.add_column(sa.Column('plan_id', sa.Integer(), nullable=True))
        batch_op.alter_column('monthly_credit_limit', existing_type=sa.Integer(), nullable=True)
        batch_op.create_foreign_key(
            'fk_monitor_companies_plan_id', 'pricing_plans', ['plan_id'], ['id']
        )
    op.create_index(op.f('ix_monitor_companies_plan_id'), 'monitor_companies', ['plan_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # NOT NULL制約を復元する前に、NULL(=プラン任せ/フォールバック運用だった会社)を
    # 具体的な数値へ埋め戻す。埋めないとALTER自体が失敗する。
    op.execute(
        f"UPDATE monitor_companies SET monthly_credit_limit = {_LEGACY_DEFAULT_CREDIT_LIMIT} "
        "WHERE monthly_credit_limit IS NULL"
    )

    op.drop_index(op.f('ix_monitor_companies_plan_id'), table_name='monitor_companies')
    with op.batch_alter_table('monitor_companies') as batch_op:
        batch_op.drop_constraint('fk_monitor_companies_plan_id', type_='foreignkey')
        batch_op.alter_column('monthly_credit_limit', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column('plan_id')

    op.drop_index(op.f('ix_pricing_plans_code'), table_name='pricing_plans')
    op.drop_table('pricing_plans')
