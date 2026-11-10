from logging.config import fileConfig

# Import the models package so every model is registered
# in Base.metadata before Alembic performs autogeneration.
import backend.app.models  # noqa: F401
from alembic import context
from backend.app.core.config import DATABASE_URL
from backend.app.database.connection import Base
from sqlalchemy import create_engine, pool

# =========================================================
# ALEMBIC CONFIGURATION
# =========================================================

config = context.config


# =========================================================
# LOGGING CONFIGURATION
# =========================================================

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# =========================================================
# DATABASE CONFIGURATION
# =========================================================

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not configured. "
        "Check your environment variables before running Alembic."
    )


# =========================================================
# MODEL METADATA
# =========================================================

# Alembic compares this metadata with the existing database
# schema when generating migration revisions.
target_metadata = Base.metadata


# =========================================================
# OFFLINE MIGRATIONS
# =========================================================

def run_migrations_offline() -> None:
    """Run migrations without establishing a database connection."""

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
    """Run migrations using an active database connection."""

    connectable = create_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
        pool_pre_ping=True,
    )

    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_server_default=False,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


# =========================================================
# EXECUTE MIGRATIONS
# =========================================================

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()