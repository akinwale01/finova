from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    String,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.connection import Base


class Portfolio(Base):
    """
    Represents an investment portfolio owned by a user.

    A portfolio groups investment holdings together.

    Examples:
        - Long-Term Investments
        - Stock Portfolio
        - Crypto Portfolio
        - Retirement Portfolio
        - Trading Portfolio

    A user can have multiple portfolios.

    Portfolios use soft deletion. Instead of physically deleting
    a portfolio, it is normally deactivated with is_active=False
    so financial history remains preserved.
    """

    __tablename__ = "portfolios"

    # =========================================================
    # TABLE INDEXES / CONSTRAINTS
    # =========================================================

    __table_args__ = (
        # Efficiently retrieve a user's active portfolios.
        Index(
            "ix_portfolios_user_active",
            "user_id",
            "is_active",
        ),

        # Prevent a user from having duplicate active portfolio
        # names, ignoring letter case.
        #
        # Because this is a partial unique index, an inactive
        # portfolio does not prevent the user from reusing its
        # name for a new active portfolio.
        Index(
            "uq_portfolios_user_active_name",
            "user_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )

    # =========================================================
    # PRIMARY KEY
    # =========================================================

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    # =========================================================
    # OWNER
    # =========================================================

    # Every portfolio belongs to exactly one user.
    #
    # ondelete="RESTRICT": mirrors Account.user_id. Users are
    # deactivated, never hard-deleted (see User model docstring),
    # so this is a DB-level backstop against any code path that
    # bypasses the ORM and tries to delete a User row directly.
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # =========================================================
    # PORTFOLIO INFORMATION
    # =========================================================

    # User-defined portfolio name.
    #
    # Examples:
    #   "Long-Term Investments"
    #   "Crypto Portfolio"
    #   "Retirement"
    name = Column(
        String(100),
        nullable=False,
    )

    # =========================================================
    # STATUS / LIFECYCLE
    # =========================================================

    # Portfolios are normally archived/deactivated instead
    # of physically deleted.
    #
    # The server default ensures existing/new database rows
    # receive TRUE when no value is explicitly supplied.
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        index=True,
    )

    # =========================================================
    # TIMESTAMPS
    # =========================================================

    # Time the portfolio was created.
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Time the portfolio was last modified.
    #
    # server_default handles initial creation at the database
    # level, while onupdate updates the value when SQLAlchemy
    # modifies the row.
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    # ---------------------------------------------------------
    # USER
    # ---------------------------------------------------------

    # User who owns this portfolio.
    user = relationship(
        "User",
        back_populates="portfolios",
    )

    # ---------------------------------------------------------
    # HOLDINGS
    # ---------------------------------------------------------

    # Holdings belonging to this portfolio.
    #
    # Holdings are subordinate to a portfolio: if a Portfolio
    # row is physically removed, its holdings should go with it
    # (a holding cannot meaningfully exist without a portfolio).
    # This is intentionally different from Transaction/
    # ScheduledTransaction below, which represent financial
    # history that must survive independently.
    holdings = relationship(
        "Holding",
        back_populates="portfolio",
        cascade="all, delete-orphan",
    )

    # ---------------------------------------------------------
    # TRANSACTIONS
    # ---------------------------------------------------------

    # Historical financial/investment transactions associated
    # with this portfolio.
    #
    # No delete cascade is intentionally configured because
    # financial history must not disappear automatically.
    transactions = relationship(
        "Transaction",
        back_populates="portfolio",
    )

    # ---------------------------------------------------------
    # SCHEDULED TRANSACTIONS
    # ---------------------------------------------------------

    # Future/scheduled financial actions associated with
    # this portfolio.
    #
    # No delete cascade is intentionally configured. Scheduled
    # financial actions should be explicitly cancelled or
    # handled by the application.
    scheduled_transactions = relationship(
        "ScheduledTransaction",
        back_populates="portfolio",
    )