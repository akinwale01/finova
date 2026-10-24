"""update user account fields

Revision ID: 5d1403c87c0d
Revises: 2da3fcae3b62
Create Date: 2026-08-11 13:08:10.318307

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5d1403c87c0d"
down_revision: Union[str, Sequence[str], None] = "2da3fcae3b62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # =========================================================
    # USER ACCOUNT STATUS
    # =========================================================

    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )

    # =========================================================
    # EMAIL VERIFICATION
    # =========================================================

    op.add_column(
        "users",
        sa.Column(
            "email_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # =========================================================
    # LOGIN TRACKING
    # =========================================================

    op.add_column(
        "users",
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # =========================================================
    # UPDATED TIMESTAMP
    # =========================================================

    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # =========================================================
    # EMAIL INDEX
    # =========================================================
    #
    # The original users.email index was a normal
    # case-sensitive unique index.
    #
    # The User model now uses a PostgreSQL expression index
    # on lower(email), making:
    #
    #   John@example.com
    #   john@example.com
    #
    # represent the same account.
    #

    op.drop_index(
        op.f("ix_users_email"),
        table_name="users",
    )

    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.literal_column("lower(email)")],
        unique=True,
    )

    # =========================================================
    # ACTIVE USER INDEX
    # =========================================================

    op.create_index(
        op.f("ix_users_is_active"),
        "users",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    # Remove case-insensitive email index.
    op.drop_index(
        "uq_users_email_lower",
        table_name="users",
    )

    # Restore original email unique index.
    op.create_index(
        op.f("ix_users_email"),
        "users",
        ["email"],
        unique=True,
    )

    # Remove active-user index.
    op.drop_index(
        op.f("ix_users_is_active"),
        table_name="users",
    )

    # Remove user account fields.
    op.drop_column(
        "users",
        "updated_at",
    )

    op.drop_column(
        "users",
        "last_login_at",
    )

    op.drop_column(
        "users",
        "email_verified_at",
    )

    op.drop_column(
        "users",
        "is_active",
    )
