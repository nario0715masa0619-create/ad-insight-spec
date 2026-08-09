"""hash monitor session tokens at rest

Revision ID: d3f8a6b2c1e4
Revises: b7e2f4a1c3d5
Create Date: 2026-08-09 00:00:00.000000

Security fix from PR #91 review: monitor_sessions.token used to hold the raw
bearer token in plaintext. If the database were ever exposed (backup leak,
misconfigured replica, etc.), every active session would be immediately
usable by copying the column value straight into an Authorization header —
unlike password_hash, which requires an offline brute force first.

Renames the column to token_hash; going forward it stores
sha256(raw_token).hexdigest() (see app/core/security.py::hash_session_token)
instead of the raw token. The raw token is still generated and returned to
the client at login time — it just isn't persisted anywhere on the server
after that.

This PR is still open/unreleased (same as the two prior revisions in this
chain), so there's no real session data to migrate: any session created
under the old plaintext scheme becomes unmatchable after this migration
(its stored value is a raw token, not a hash, so no incoming request's
hashed token will ever equal it) and simply expires away within the
existing 2-week TTL. That's acceptable pre-release; the migration does not
attempt to hash pre-existing rows in place, since consumers no longer sending
a session_token that hashes to a pre-migration row is the expected outcome,
not a defect.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3f8a6b2c1e4'
down_revision: Union[str, Sequence[str], None] = 'b7e2f4a1c3d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index('ix_monitor_sessions_token', table_name='monitor_sessions')
    with op.batch_alter_table('monitor_sessions') as batch_op:
        batch_op.alter_column(
            'token', new_column_name='token_hash', existing_type=sa.String(length=128)
        )
    op.create_index(
        op.f('ix_monitor_sessions_token_hash'), 'monitor_sessions', ['token_hash'], unique=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_monitor_sessions_token_hash'), table_name='monitor_sessions')
    with op.batch_alter_table('monitor_sessions') as batch_op:
        batch_op.alter_column(
            'token_hash', new_column_name='token', existing_type=sa.String(length=128)
        )
    op.create_index('ix_monitor_sessions_token', 'monitor_sessions', ['token'], unique=True)
