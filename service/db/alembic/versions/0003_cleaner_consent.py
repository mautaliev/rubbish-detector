"""Add consent fields to cleaner (152-ФЗ)

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляет поля фиксации согласия дворника на обработку ПДн."""
    op.add_column(
        "cleaner",
        sa.Column("consent_given_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "cleaner",
        sa.Column("consent_version", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cleaner", "consent_version")
    op.drop_column("cleaner", "consent_given_at")
