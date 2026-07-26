"""add verification tables

Revision ID: 180b9b618513
Revises: a1f7ccac7a04
Create Date: 2026-07-26 00:00:00.000000

Adds three new tables to support the CampaignPilot verification feature
(recording whether proposals surface genuinely new findings vs what Meta
Ads Manager alone would show, and whether they get executed with results):

- verification_cases: per-client pre-hearing notes and post-presentation
  evaluation. Links loosely to ad_insights.asset_id (no FK constraint,
  since ad_insights is versioned and this is a lightweight reference only).
- verification_suggestion_evaluations: per-proposal awareness/originality
  ratings, child of verification_cases.
- verification_followups: week_2/week_4 execution status and result
  changes, child of verification_suggestion_evaluations.

This migration only creates new tables. It does not touch ad_insights or
any other existing table/column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '180b9b618513'
down_revision: Union[str, Sequence[str], None] = 'a1f7ccac7a04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'verification_cases',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('case_name', sa.String(length=200), nullable=False),
        sa.Column('asset_id', sa.String(length=100), nullable=True),
        sa.Column('pre_hearing_notes', sa.JSON(), nullable=True),
        sa.Column('presentation_evaluation', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
    )
    op.create_index('ix_verification_cases_id', 'verification_cases', ['id'])
    op.create_index('ix_verification_cases_asset_id', 'verification_cases', ['asset_id'])
    op.create_index('ix_verification_cases_created_at', 'verification_cases', ['created_at'])

    op.create_table(
        'verification_suggestion_evaluations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('case_id', sa.Integer(), sa.ForeignKey('verification_cases.id'), nullable=False),
        sa.Column('suggestion_key', sa.String(length=300), nullable=False),
        sa.Column('suggestion_text', sa.Text(), nullable=True),
        sa.Column('awareness_rating', sa.String(length=50), nullable=False),
        sa.Column('originality_rating', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
    )
    op.create_index('ix_verification_suggestion_evaluations_id', 'verification_suggestion_evaluations', ['id'])
    op.create_index('ix_verification_suggestion_evaluations_case_id', 'verification_suggestion_evaluations', ['case_id'])
    op.create_index(
        'idx_verification_suggestion_case',
        'verification_suggestion_evaluations',
        ['case_id', 'created_at'],
    )

    op.create_table(
        'verification_followups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'suggestion_evaluation_id',
            sa.Integer(),
            sa.ForeignKey('verification_suggestion_evaluations.id'),
            nullable=False,
        ),
        sa.Column('checkpoint', sa.String(length=20), nullable=False),
        sa.Column('executed', sa.Boolean(), nullable=True),
        sa.Column('result_change', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('suggestion_evaluation_id', 'checkpoint', name='uq_followup_suggestion_checkpoint'),
    )
    op.create_index('ix_verification_followups_id', 'verification_followups', ['id'])
    op.create_index(
        'ix_verification_followups_suggestion_evaluation_id',
        'verification_followups',
        ['suggestion_evaluation_id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('verification_followups')
    op.drop_table('verification_suggestion_evaluations')
    op.drop_table('verification_cases')
