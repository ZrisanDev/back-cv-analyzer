"""Add missing payment fields and external_reference.

Revision ID: 0006
Revises: 1a44de73309b
Create Date: 2026-04-05

This migration adds fields to the payments table that were defined in the
Payment model but missing from the database schema:
- external_reference: Stores the Mercado Pago external_reference (user_id or tracking ID)
- status_detail: Stores Mercado Pago status_detail (e.g., accredited, pending_contingency)
- date_approved: Timestamp when payment was approved
- payment_method_id: Payment method used (e.g., credit_card, debit_card)
- payer_email: Email of the payer from Mercado Pago

NOTE: Some columns may already exist in the database (manually added or partially run).
This migration uses op.execute with PostgreSQL-specific checks to avoid errors.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "1a44de73309b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add external_reference column (for tracking and debugging)
    # Check if column exists first using PostgreSQL-specific syntax
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'payments' AND column_name = 'external_reference'
            ) THEN
                ALTER TABLE payments ADD COLUMN external_reference VARCHAR(255);
                CREATE INDEX ix_payments_external_reference ON payments(external_reference);
                COMMENT ON COLUMN payments.external_reference IS 'External reference from Mercado Pago (typically user_id or tracking ID)';
            END IF;
        END $$;
    """)

    # Add status_detail column
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'payments' AND column_name = 'status_detail'
            ) THEN
                ALTER TABLE payments ADD COLUMN status_detail VARCHAR(50);
                COMMENT ON COLUMN payments.status_detail IS 'MercadoPago status detail (e.g., accredited, pending_contingency)';
            END IF;
        END $$;
    """)

    # Add date_approved column
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'payments' AND column_name = 'date_approved'
            ) THEN
                ALTER TABLE payments ADD COLUMN date_approved TIMESTAMP WITH TIME ZONE;
                COMMENT ON COLUMN payments.date_approved IS 'When payment was approved';
            END IF;
        END $$;
    """)

    # Add payment_method_id column
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'payments' AND column_name = 'payment_method_id'
            ) THEN
                ALTER TABLE payments ADD COLUMN payment_method_id VARCHAR(50);
                COMMENT ON COLUMN payments.payment_method_id IS 'MercadoPago payment method used (e.g., credit_card, debit_card)';
            END IF;
        END $$;
    """)

    # Add payer_email column
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'payments' AND column_name = 'payer_email'
            ) THEN
                ALTER TABLE payments ADD COLUMN payer_email VARCHAR(255);
                COMMENT ON COLUMN payments.payer_email IS 'Email of the payer from Mercado Pago';
            END IF;
        END $$;
    """)

    # Remove old analysis_id column if it exists (credit packages don't need it)
    # Check if column exists and drop it
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'payments' AND column_name = 'analysis_id'
            ) THEN
                DROP INDEX IF EXISTS ix_payments_analysis_id;
                ALTER TABLE payments DROP COLUMN IF EXISTS analysis_id;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Drop newly added columns
    op.execute("""
        ALTER TABLE payments DROP COLUMN IF EXISTS payer_email;
    """)
    op.execute("""
        ALTER TABLE payments DROP COLUMN IF EXISTS payment_method_id;
    """)
    op.execute("""
        ALTER TABLE payments DROP COLUMN IF EXISTS date_approved;
    """)
    op.execute("""
        ALTER TABLE payments DROP COLUMN IF EXISTS status_detail;
    """)
    op.execute("""
        DROP INDEX IF EXISTS ix_payments_external_reference;
        ALTER TABLE payments DROP COLUMN IF EXISTS external_reference;
    """)

    # Restore analysis_id column if it was removed
    # This assumes the analyses table still exists
    op.add_column(
        "payments",
        sa.Column(
            "analysis_id",
            sa.UUID(),
            sa.ForeignKey("analyses.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_payments_analysis_id", "payments", ["analysis_id"]
    )
