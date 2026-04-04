"""Create payments table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-02

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the payment_status enum type (non-native, stored as VARCHAR)
    op.execute(
        "CREATE TYPE payment_status AS ENUM "
        "('pending', 'approved', 'rejected', 'refunded', 'in_process')"
    )

    op.create_table(
        "payments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analyses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="ARS"),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "rejected",
                "refunded",
                "in_process",
                name="payment_status",
                native_enum=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("mercadopago_payment_id", sa.String(64), nullable=True, unique=True),
        sa.Column("mercadopago_preference_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_analysis_id", "payments", ["analysis_id"])
    op.create_index(
        "ix_payments_preference_id", "payments", ["mercadopago_preference_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_payments_preference_id", table_name="payments")
    op.drop_index("ix_payments_analysis_id", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_table("payments")
    op.execute("DROP TYPE IF EXISTS payment_status")
