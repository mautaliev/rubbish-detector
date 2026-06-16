"""Initial schema: company, cleaner, report

Revision ID: 0001
Revises:
Create Date: 2026-06-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute("CREATE TYPE model_version AS ENUM ('single_class', 'multi_class')")

    op.create_table(
        "company",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("vk_user_id", sa.BigInteger(), nullable=False),
        sa.Column("invite_code", sa.Text(), nullable=False),
        sa.Column(
            "default_model",
            postgresql.ENUM("single_class", "multi_class", name="model_version", create_type=False),
            nullable=False,
            server_default="single_class",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("invite_code"),
    )

    op.create_table(
        "cleaner",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("company.id"), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("vk_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("vk_user_id"),
    )

    op.create_table(
        "report",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("cleaner_id", sa.BigInteger(), sa.ForeignKey("cleaner.id"), nullable=False),
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("company.id"), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "model_version",
            postgresql.ENUM("single_class", "multi_class", name="model_version", create_type=False),
            nullable=False,
        ),
        sa.Column("photos", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_clean", sa.Boolean(), nullable=False),
        sa.Column("photos_count", sa.Integer(), nullable=False),
        sa.Column("objects_count", sa.Integer(), nullable=False),
        sa.Column("notified_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_index("idx_report_company_created", "report", ["company_id", "created_at"])
    op.create_index("idx_report_cleaner_created", "report", ["cleaner_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_report_cleaner_created", table_name="report")
    op.drop_index("idx_report_company_created", table_name="report")
    op.drop_table("report")
    op.drop_table("cleaner")
    op.drop_table("company")
    op.execute("DROP TYPE model_version")
