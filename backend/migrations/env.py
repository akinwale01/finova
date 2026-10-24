from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import DATABASE_URL
from app.database.connection import Base

# Import models so SQLAlchemy registers their tables
# in Base.metadata before Alembic runs autogenerate.
from app.models.user import User
from app.models.portfolio import Portfolio


# =========================================================
# ALEMBIC CONFIGURATION
# =========================================================

config = context.config


# =========================================================
# LOGGING
# =========================================================

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# =========================================================
# SQLALCHEMY METADATA
# =========================================================

# Alembic uses this metadata to compare the current
# SQLAlchemy models against the PostgreSQL database.
target_metadata = Base.metadata


# =========================================================
# OFFLINE MIGRATIONS
# =========================================================

def run_migrations_offline() -> None:
    """Run migrations in offline mode."""

    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_server_default=False,
    )

    with context.begin_transaction():
        context.run_migrations()
# =========================================================
# ONLINE MIGRATIONS
# =========================================================

def run_migrations_online() -> None:
    """Run migrations in online mode."""

    connectable = create_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_server_default=False,
        )

        with context.begin_transaction():
            context.run_migrations()

# =========================================================
# RUN MIGRATION
# =========================================================

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()