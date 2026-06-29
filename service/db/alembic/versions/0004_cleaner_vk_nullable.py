"""Make cleaner.vk_user_id nullable for consent withdrawal

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-29
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Разрешает NULL в cleaner.vk_user_id для поддержки отзыва согласия."""
    op.alter_column("cleaner", "vk_user_id", nullable=True)


def downgrade() -> None:
    op.alter_column("cleaner", "vk_user_id", nullable=False)
