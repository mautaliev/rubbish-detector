"""Add phone and status fields to company

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("company", sa.Column("phone", sa.Text(), nullable=True))
    op.add_column(
        "company",
        sa.Column("status", sa.SmallInteger(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_company_status", "company", "status IN (0, 1, 2)"
    )


def downgrade() -> None:
    op.drop_constraint("ck_company_status", "company", type_="check")
    op.drop_column("company", "status")
    op.drop_column("company", "phone")
