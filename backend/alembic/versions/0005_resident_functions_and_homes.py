"""resident functions (steps on invented actions) and homes

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-28 13:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('custom_actions', sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('custom_actions', sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False))
    op.add_column('custom_actions', sa.Column('version', sa.Integer(), server_default='1', nullable=False))
    op.add_column('custom_actions', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('rooms', sa.Column('furnishings', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))


def downgrade() -> None:
    op.drop_column('rooms', 'furnishings')
    op.drop_column('custom_actions', 'updated_at')
    op.drop_column('custom_actions', 'version')
    op.drop_column('custom_actions', 'state')
    op.drop_column('custom_actions', 'steps')
