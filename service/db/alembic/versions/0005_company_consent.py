"""Add consent fields to company; make company.vk_user_id nullable

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Добавляет поля согласия УК и делает vk_user_id nullable для поддержки отзыва согласия."""
    op.add_column("company", sa.Column("consent_given_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("company", sa.Column("consent_version", sa.Text(), nullable=True))
    op.alter_column("company", "vk_user_id", nullable=True)


def downgrade() -> None:
    op.alter_column("company", "vk_user_id", nullable=False)
    op.drop_column("company", "consent_version")
    op.drop_column("company", "consent_given_at")
