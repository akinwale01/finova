from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import relationship, validates

from app.database.connection import Base


class User(Base):
    """
    Represents a Finova user.

    A user can own:
        - Financial accounts
        - Investment portfolios
        - Scheduled transactions
        - Other financial records through their owned entities

    Authentication:
        - email identifies the user
        - password_hash stores ONLY the securely hashed password

    Important:
        Passwords must NEVER be stored directly in this table.

    Deletion policy:
        Users are never hard-deleted from this table. Deactivate
        an account with is_active=False instead. This preserves
        financial history on owned accounts, portfolios, and
        transactions, and avoids foreign-key conflicts with
        records (e.g. Transaction) that intentionally do not
        cascade-delete.

        If a hard "erase my data" flow is ever required (e.g.
        GDPR/CCPA), implement it as an explicit admin operation
        that walks dependent tables in the correct order. It
        must not be an implicit ORM cascade on this model.
    """

    __tablename__ = "users"

    # =========================================================
    # PRIMARY KEY
    # =========================================================

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    # =========================================================
    # AUTHENTICATION
    # =========================================================

    # Always stored lowercase + trimmed (see normalize_email
    # below) so plain equality queries stay consistent with the
    # case-insensitive unique index.
    email = Column(
        String(320),
        nullable=False,
    )

    password_hash = Column(
        String(255),
        nullable=False,
    )

    # =========================================================
    # ACCOUNT STATUS
    # =========================================================

    # Allows Finova to disable an account without deleting the
    # user's financial history. This is the intended way to
    # remove a user's access -- never hard-delete the row.
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )

    # Set when the user successfully verifies their email.
    email_verified_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Last successful authentication.
    #
    # Useful for:
    # - security monitoring
    # - account activity
    # - future security features (e.g. "new device" alerts)
    last_login_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =========================================================
    # PASSWORD RESET / RECOVERY
    # =========================================================

    # Hash of the current password-reset token, if one has been
    # issued and not yet used/expired. Store a HASH of the
    # token here (e.g. sha256), never the raw token -- the same
    # principle as password_hash.
    password_reset_token_hash = Column(
        String(255),
        nullable=True,
    )

    password_reset_expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =========================================================
    # TIMESTAMPS
    # =========================================================

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # =========================================================
    # VALIDATORS
    # =========================================================

    @validates("email")
    def normalize_email(self, key, value):
        """
        Normalize email to lowercase and strip whitespace on
        every write (create AND update).

        The DB index (uq_users_email_lower) already enforces
        case-insensitive uniqueness, but normalizing here means
        application code can safely do:

            db.query(User).filter(User.email == email.lower())

        instead of always wrapping queries in func.lower(...).
        """
        if value is None:
            return value
        return value.strip().lower()

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    # NOTE: No delete cascades here on purpose. Users are
    # deactivated (is_active=False), never hard-deleted, so
    # there is no case where SQLAlchemy should cascade-delete a
    # user's accounts/portfolios/scheduled transactions.
    accounts = relationship(
        "Account",
        back_populates="user",
    )

    portfolios = relationship(
        "Portfolio",
        back_populates="user",
    )

    scheduled_transactions = relationship(
        "ScheduledTransaction",
        back_populates="user",
    )

    # =========================================================
    # DATABASE CONSTRAINTS / INDEXES
    # =========================================================

    __table_args__ = (
        # PostgreSQL expression index.
        #
        # This makes email uniqueness case-insensitive:
        #
        # John@example.com
        # john@example.com
        #
        # are treated as the same account. Combined with the
        # normalize_email validator above, plain equality
        # queries also stay correct.
        Index(
            "uq_users_email_lower",
            func.lower(email),
            unique=True,
        ),
    )