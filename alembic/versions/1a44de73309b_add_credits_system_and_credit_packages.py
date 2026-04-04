"""add_credits_system_and_credit_packages

Revision ID: 1a44de73309b
Revises: 0005
Create Date: 2026-04-03 02:47:54.623926

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1a44de73309b"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Add credit columns to users table ─────────────────────
    op.add_column(
        "users",
        sa.Column(
            "paid_analyses_credits",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Créditos pagos acumulados (no expiran)",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "total_analyses_used",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Contador total de análisis realizados (gratis + pagos)",
        ),
    )

    # Update comment for free_analyses_count
    op.alter_column(
        "users",
        "free_analyses_count",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default="0",
        comment="Contador de análisis gratuitos usados (máximo: FREE_ANALYSIS_LIMIT)",
    )

    # ── Create credit_packages table ───────────────────────────
    # Enum will be created automatically when the table is created
    credit_package_type_enum = sa.Enum(
        "pack_20",
        "pack_50",
        "pack_100",
        name="credit_package_type",
    )

    op.create_table(
        "credit_packages",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
        ),
        sa.Column(
            "package_type",
            credit_package_type_enum,
            nullable=False,
        ),
        sa.Column(
            "credits_count",
            sa.Integer(),
            nullable=False,
            comment="Number of analysis credits included in this package",
        ),
        sa.Column(
            "price_usd",
            sa.Float(),
            nullable=False,
            comment="Price in USD",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Whether this package is currently available for purchase",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("package_type"),
    )

    # ── Insert default credit packages ─────────────────────────
    op.execute(
        """
        INSERT INTO credit_packages (id, package_type, credits_count, price_usd, is_active, created_at, updated_at)
        VALUES
            ('550e8400-e29b-41d4-a716-446655440101', 'pack_20', 20, 3.00, true, now(), now()),
            ('550e8400-e29b-41d4-a716-446655440102', 'pack_50', 50, 10.00, true, now(), now()),
            ('550e8400-e29b-41d4-a716-446655440103', 'pack_100', 100, 20.00, true, now(), now());
        """
    )

    # ── Add package_type column to payments table ───────────────
    # Reuse the same enum type (already created above)
    op.add_column(
        "payments",
        sa.Column(
            "package_type",
            credit_package_type_enum,
            nullable=True,
            comment="Type of credit package purchased. Null for individual analyses (legacy).",
        ),
    )
    op.create_index(
        "ix_payments_package_type",
        "payments",
        ["package_type"],
    )

    # ── Change default currency from ARS to USD ────────────────
    op.alter_column(
        "payments",
        "currency",
        existing_type=sa.String(3),
        existing_nullable=False,
        server_default="USD",
        comment="Currency code (USD, ARS, etc.)",
    )


def downgrade() -> None:
    # ── Revert currency default ───────────────────────────────
    op.alter_column(
        "payments",
        "currency",
        existing_type=sa.String(3),
        existing_nullable=False,
        server_default="ARS",
        comment=None,
    )

    # ── Remove package_type from payments ───────────────────────
    op.drop_index("ix_payments_package_type", table_name="payments")
    op.drop_column("payments", "package_type")

    # ── Drop credit_packages table ─────────────────────────────
    op.execute("DELETE FROM credit_packages")
    op.drop_table("credit_packages")

    # Drop enum type if it exists
    credit_package_type_enum = sa.Enum(
        "pack_20",
        "pack_50",
        "pack_100",
        name="credit_package_type",
    )
    credit_package_type_enum.drop(op.get_bind(), checkfirst=False)

    # ── Remove credit columns from users ───────────────────────
    op.drop_column("users", "total_analyses_used")
    op.drop_column("users", "paid_analyses_credits")

    # Revert comment for free_analyses_count
    op.alter_column(
        "users",
        "free_analyses_count",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default="0",
        comment=None,
    )
