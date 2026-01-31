"""Alembic migration environment configuration.

Configured to:
- Use SQLModel metadata for autogenerate
- Load database URL from environment/config
- Support both sync migrations (default) and async
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Import all models to register them with SQLModel.metadata
from src.db.models import (  # noqa: F401
    AuditLog,
    CallerPreferences,
    CallLog,
    Reservation,
    WhatsappFollowup,
)

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# SQLModel metadata for autogenerate support
target_metadata = SQLModel.metadata


def get_database_url() -> str:
    """Get database URL from environment or config.

    Priority:
    1. Alembic config (from alembic.ini or -x sqlalchemy.url=)
    2. Environment variable DATABASE_URL
    3. Default SQLite path
    """
    # Check if URL is set in alembic config
    url = config.get_main_option("sqlalchemy.url")
    if url and url != "driver://user:pass@localhost/dbname":
        return url

    # Load from our config
    try:
        from src.config import get_settings

        settings = get_settings()
        # Convert async URL to sync for Alembic
        return settings.database_url.replace("+aiosqlite", "")
    except Exception:
        # Fallback for CI/testing
        import os

        return os.environ.get(
            "DATABASE_URL", "sqlite:///./data/vartalaap.db"
        ).replace("+aiosqlite", "")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Improve autogenerate
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Override the sqlalchemy.url in config
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Improve autogenerate
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
