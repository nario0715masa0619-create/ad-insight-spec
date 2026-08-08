"""add invite-only monitor beta access tables

Revision ID: f3a1c9d2e8b0
Revises: d04670158813
Create Date: 2026-08-07 00:00:00.000000

Adds the minimal schema for invite-only monitor beta access:
- monitor_companies: the tenant unit that a monthly analysis quota is
  attached to (company-level, not per-user; see
  docs/MONITOR_BETA_OPERATION.md for why).
- monitor_users: invited accounts. There is no self-signup path anywhere
  in the app, so every row here was created by an admin (API or
  scripts/manage_monitor_accounts.py).
- monitor_sessions: server-held login sessions (DB-backed rather than a
  signed token so a user/session can be revoked immediately by deleting
  the row, without needing a signing-key rotation story for a 3-5
  company beta).

Also adds nullable `ad_insights.company_id` / `ad_insights.created_by_user_id`
so existing analyses funnel through the same table without a backfill;
existing rows keep company_id=NULL, which simply means no beta company will
see them in their scoped list (no data loss, just correctly excluded from a
scope that didn't exist yet).

Also adds `credit_usage_logs` and renames `monitor_companies.monthly_analysis_limit`
to `monthly_credit_limit`: the monthly quota moved from "N analyses" to "N credits",
with each analysis mode costing 1/2/3 credits (see app/services/credit_pricing.py).
Usage is computed by summing credit_usage_logs rows for the current month rather
than maintaining a running counter, the same pattern already used for AdInsight-based
counting, so there's no separate aggregate to keep in sync. This migration is still
unreleased (no production deploy has applied it yet), so the rename is folded into
the same revision instead of adding a follow-up one.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a1c9d2e8b0'
down_revision: Union[str, Sequence[str], None] = 'd04670158813'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'monitor_companies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('monthly_credit_limit', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_index(op.f('ix_monitor_companies_slug'), 'monitor_companies', ['slug'], unique=True)

    op.create_table(
        'monitor_users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=200), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['monitor_companies.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    op.create_index(op.f('ix_monitor_users_company_id'), 'monitor_users', ['company_id'], unique=False)
    op.create_index(op.f('ix_monitor_users_email'), 'monitor_users', ['email'], unique=True)

    op.create_table(
        'monitor_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['monitor_users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
    )
    op.create_index(op.f('ix_monitor_sessions_user_id'), 'monitor_sessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_monitor_sessions_token'), 'monitor_sessions', ['token'], unique=True)

    with op.batch_alter_table('ad_insights') as batch_op:
        batch_op.add_column(sa.Column('company_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('created_by_user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_ad_insights_company_id', 'monitor_companies', ['company_id'], ['id']
        )
        batch_op.create_foreign_key(
            'fk_ad_insights_created_by_user_id', 'monitor_users', ['created_by_user_id'], ['id']
        )
    op.create_index(op.f('ix_ad_insights_company_id'), 'ad_insights', ['company_id'], unique=False)

    op.create_table(
        'credit_usage_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.String(length=100), nullable=True),
        sa.Column('asset_version', sa.Integer(), nullable=True),
        sa.Column('credit_cost', sa.Integer(), nullable=False),
        sa.Column('analysis_type', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['monitor_companies.id']),
        sa.ForeignKeyConstraint(['user_id'], ['monitor_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_credit_usage_logs_company_id'), 'credit_usage_logs', ['company_id'], unique=False)
    op.create_index(op.f('ix_credit_usage_logs_asset_id'), 'credit_usage_logs', ['asset_id'], unique=False)
    op.create_index(op.f('ix_credit_usage_logs_created_at'), 'credit_usage_logs', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_credit_usage_logs_created_at'), table_name='credit_usage_logs')
    op.drop_index(op.f('ix_credit_usage_logs_asset_id'), table_name='credit_usage_logs')
    op.drop_index(op.f('ix_credit_usage_logs_company_id'), table_name='credit_usage_logs')
    op.drop_table('credit_usage_logs')

    op.drop_index(op.f('ix_ad_insights_company_id'), table_name='ad_insights')
    with op.batch_alter_table('ad_insights') as batch_op:
        batch_op.drop_constraint('fk_ad_insights_created_by_user_id', type_='foreignkey')
        batch_op.drop_constraint('fk_ad_insights_company_id', type_='foreignkey')
        batch_op.drop_column('created_by_user_id')
        batch_op.drop_column('company_id')

    op.drop_index(op.f('ix_monitor_sessions_token'), table_name='monitor_sessions')
    op.drop_index(op.f('ix_monitor_sessions_user_id'), table_name='monitor_sessions')
    op.drop_table('monitor_sessions')

    op.drop_index(op.f('ix_monitor_users_email'), table_name='monitor_users')
    op.drop_index(op.f('ix_monitor_users_company_id'), table_name='monitor_users')
    op.drop_table('monitor_users')

    op.drop_index(op.f('ix_monitor_companies_slug'), table_name='monitor_companies')
    op.drop_table('monitor_companies')
