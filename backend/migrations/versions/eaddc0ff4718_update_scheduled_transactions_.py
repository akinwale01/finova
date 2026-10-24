"""Update scheduled transactions relationship

Revision ID: eaddc0ff4718
Revises: 28e87c474a91
Create Date: 2026-08-15 22:39:45.229481

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "eaddc0ff4718"
down_revision: Union[str, Sequence[str], None] = "28e87c474a91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # =========================================================
    # SCHEDULED TRANSACTION FIELDS
    # =========================================================

    op.add_column(
        "scheduled_transactions",
        sa.Column(
            "recurrence_end_date",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "scheduled_transactions",
        sa.Column(
            "recurrence_count",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "scheduled_transactions",
        sa.Column(
            "execution_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )

    op.alter_column(
        "scheduled_transactions",
        "execution_mode",
        existing_type=sa.VARCHAR(),
        nullable=False,
    )

    op.alter_column(
        "scheduled_transactions",
        "amount",
        existing_type=sa.NUMERIC(precision=20, scale=8),
        nullable=True,
    )

    # =========================================================
    # NEW RELATIONSHIP: TRANSACTION → SCHEDULED TRANSACTION
    # =========================================================
    #
    # IMPORTANT:
    # Add the new column BEFORE removing the old
    # scheduled_transactions.transaction_id column.
    #
    # This allows us to preserve existing relationships.
    #

    op.add_column(
        "transactions",
        sa.Column(
            "scheduled_transaction_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # ---------------------------------------------------------
    # Migrate existing relationship data.
    #
    # Old:
    #
    # scheduled_transactions.transaction_id
    #
    # New:
    #
    # transactions.scheduled_transaction_id
    #
    # Existing transaction_id values are copied before the old
    # column is removed.
    # ---------------------------------------------------------

    op.execute(
        """
        UPDATE transactions AS t
        SET scheduled_transaction_id = st.id
        FROM scheduled_transactions AS st
        WHERE st.transaction_id = t.id
        """
    )

    # =========================================================
    # NEW TRANSACTION INDEX / FOREIGN KEY
    # =========================================================

    op.create_index(
        "ix_transactions_scheduled_transaction_id",
        "transactions",
        ["scheduled_transaction_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_transactions_scheduled_transaction_id",
        "transactions",
        "scheduled_transactions",
        ["scheduled_transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # =========================================================
    # REMOVE OLD SCHEDULED TRANSACTION RELATIONSHIP
    # =========================================================

    op.drop_constraint(
        "scheduled_transactions_transaction_id_fkey",
        "scheduled_transactions",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_scheduled_transactions_transaction_id",
        table_name="scheduled_transactions",
    )

    op.drop_column(
        "scheduled_transactions",
        "transaction_id",
    )

    # =========================================================
    # SCHEDULED TRANSACTION INDEXES
    # =========================================================

    op.create_index(
        "ix_scheduled_transactions_destination_account_scheduled_date",
        "scheduled_transactions",
        ["destination_account_id", "scheduled_date"],
        unique=False,
    )

    op.create_index(
        "ix_scheduled_transactions_is_recurring",
        "scheduled_transactions",
        ["is_recurring"],
        unique=False,
    )

    op.create_index(
        "ix_scheduled_transactions_portfolio_scheduled_date",
        "scheduled_transactions",
        ["portfolio_id", "scheduled_date"],
        unique=False,
    )

    op.create_index(
        "ix_scheduled_transactions_source_account_scheduled_date",
        "scheduled_transactions",
        ["source_account_id", "scheduled_date"],
        unique=False,
    )

    op.create_index(
        "ix_scheduled_transactions_status_scheduled_date",
        "scheduled_transactions",
        ["status", "scheduled_date"],
        unique=False,
    )

    op.create_index(
        "ix_scheduled_transactions_type_status",
        "scheduled_transactions",
        ["scheduled_type", "status"],
        unique=False,
    )

    op.create_index(
        "ix_scheduled_transactions_user_scheduled_date",
        "scheduled_transactions",
        ["user_id", "scheduled_date"],
        unique=False,
    )

    # =========================================================
    # UPDATE EXISTING FOREIGN KEYS
    # =========================================================
    #
    # The model explicitly uses ON DELETE RESTRICT.
    #
    # Drop the existing constraints and recreate them with the
    # finalized behavior.
    #

    op.drop_constraint(
        "scheduled_transactions_user_id_fkey",
        "scheduled_transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "scheduled_transactions_portfolio_id_fkey",
        "scheduled_transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "scheduled_transactions_asset_id_fkey",
        "scheduled_transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "scheduled_transactions_destination_account_id_fkey",
        "scheduled_transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "scheduled_transactions_source_account_id_fkey",
        "scheduled_transactions",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "fk_scheduled_transactions_asset_id",
        "scheduled_transactions",
        "assets",
        ["asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_scheduled_transactions_source_account_id",
        "scheduled_transactions",
        "accounts",
        ["source_account_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_scheduled_transactions_destination_account_id",
        "scheduled_transactions",
        "accounts",
        ["destination_account_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_scheduled_transactions_user_id",
        "scheduled_transactions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_scheduled_transactions_portfolio_id",
        "scheduled_transactions",
        "portfolios",
        ["portfolio_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Downgrade schema.

    WARNING:
    The new architecture permits one ScheduledTransaction to
    generate multiple Transactions. The old schema only allowed
    one transaction_id per ScheduledTransaction.

    Therefore a downgrade cannot faithfully restore multiple
    generated transactions. This downgrade preserves one
    relationship per scheduled transaction and removes the new
    relationship architecture.
    """

    # =========================================================
    # RESTORE OLD TRANSACTION COLUMN
    # =========================================================

    op.add_column(
        "scheduled_transactions",
        sa.Column(
            "transaction_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # Preserve one transaction relationship where possible.
    #
    # If multiple transactions point to the same schedule,
    # PostgreSQL chooses one deterministically by MIN(id).
    #
    # The new architecture itself is not lost during normal
    # operation; this only matters if this migration is manually
    # downgraded.
    op.execute(
        """
        UPDATE scheduled_transactions AS st
        SET transaction_id = t.id
        FROM transactions AS t
        WHERE t.scheduled_transaction_id = st.id
          AND t.id = (
              SELECT MIN(t2.id)
              FROM transactions AS t2
              WHERE t2.scheduled_transaction_id = st.id
          )
        """
    )

    # =========================================================
    # REMOVE NEW TRANSACTION RELATIONSHIP
    # =========================================================

    op.drop_constraint(
        "fk_transactions_scheduled_transaction_id",
        "transactions",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_transactions_scheduled_transaction_id",
        table_name="transactions",
    )

    op.drop_column(
        "transactions",
        "scheduled_transaction_id",
    )

    # =========================================================
    # REMOVE NEW SCHEDULED TRANSACTION FOREIGN KEYS
    # =========================================================

    op.drop_constraint(
        "fk_scheduled_transactions_asset_id",
        "scheduled_transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_scheduled_transactions_source_account_id",
        "scheduled_transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_scheduled_transactions_destination_account_id",
        "scheduled_transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_scheduled_transactions_user_id",
        "scheduled_transactions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_scheduled_transactions_portfolio_id",
        "scheduled_transactions",
        type_="foreignkey",
    )

    # =========================================================
    # RESTORE OLD FOREIGN KEYS
    # =========================================================

    op.create_foreign_key(
        "scheduled_transactions_user_id_fkey",
        "scheduled_transactions",
        "users",
        ["user_id"],
        ["id"],
    )

    op.create_foreign_key(
        "scheduled_transactions_portfolio_id_fkey",
        "scheduled_transactions",
        "portfolios",
        ["portfolio_id"],
        ["id"],
    )

    op.create_foreign_key(
        "scheduled_transactions_asset_id_fkey",
        "scheduled_transactions",
        "assets",
        ["asset_id"],
        ["id"],
    )

    op.create_foreign_key(
        "scheduled_transactions_destination_account_id_fkey",
        "scheduled_transactions",
        "accounts",
        ["destination_account_id"],
        ["id"],
    )

    op.create_foreign_key(
        "scheduled_transactions_source_account_id_fkey",
        "scheduled_transactions",
        "accounts",
        ["source_account_id"],
        ["id"],
    )

    # =========================================================
    # RESTORE OLD INDEXES
    # =========================================================

    op.drop_index(
        "ix_scheduled_transactions_user_scheduled_date",
        table_name="scheduled_transactions",
    )

    op.drop_index(
        "ix_scheduled_transactions_type_status",
        table_name="scheduled_transactions",
    )

    op.drop_index(
        "ix_scheduled_transactions_status_scheduled_date",
        table_name="scheduled_transactions",
    )

    op.drop_index(
        "ix_scheduled_transactions_source_account_scheduled_date",
        table_name="scheduled_transactions",
    )

    op.drop_index(
        "ix_scheduled_transactions_portfolio_scheduled_date",
        table_name="scheduled_transactions",
    )

    op.drop_index(
        "ix_scheduled_transactions_is_recurring",
        table_name="scheduled_transactions",
    )

    op.drop_index(
        "ix_scheduled_transactions_destination_account_scheduled_date",
        table_name="scheduled_transactions",
    )

    op.create_index(
        "ix_scheduled_transactions_transaction_id",
        "scheduled_transactions",
        ["transaction_id"],
        unique=False,
    )

    # =========================================================
    # REMOVE NEW SCHEDULE FIELDS
    # =========================================================

    op.alter_column(
        "scheduled_transactions",
        "amount",
        existing_type=sa.NUMERIC(precision=20, scale=8),
        nullable=False,
    )

    op.alter_column(
        "scheduled_transactions",
        "execution_mode",
        existing_type=sa.VARCHAR(),
        nullable=True,
    )

    op.drop_column(
        "scheduled_transactions",
        "execution_count",
    )

    op.drop_column(
        "scheduled_transactions",
        "recurrence_count",
    )

    op.drop_column(
        "scheduled_transactions",
        "recurrence_end_date",
    )