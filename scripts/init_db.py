#!/usr/bin/env python3
"""Initialize database tables.

For development only. In production, use Alembic migrations:
    alembic upgrade head

Usage:
    python scripts/init_db.py
"""

from sqlmodel import SQLModel

import src.db.models  # noqa: F401 - Register models with SQLModel


def main():
    """Create all database tables using sync engine."""
    from src.db.session import get_sync_engine

    engine = get_sync_engine()
    SQLModel.metadata.create_all(engine)
    print("Database tables created successfully.")


if __name__ == "__main__":
    main()
