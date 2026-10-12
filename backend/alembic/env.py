"""Alembic environment: upgrade/downgrade against DATABASE_URL or PG*."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config
# disable_existing_loggers=False so pytest caplog / app loggers keep working when
# migrate_to_postgis / apply_schema invokes alembic from inside the test process.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = None  # schema lives in SQL files / migration scripts, not ORM models


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        # SQLAlchemy 2 prefers postgresql+psycopg2://
        if url.startswith("postgresql://"):
            return "postgresql+psycopg2://" + url[len("postgresql://") :]
        if url.startswith("postgres://"):
            return "postgresql+psycopg2://" + url[len("postgres://") :]
        return url
    host = os.getenv("PGHOST", "").strip()
    db = os.getenv("PGDATABASE", "").strip()
    if not (host and db):
        raise RuntimeError(
            "Set DATABASE_URL, or PGHOST and PGDATABASE (plus PGUSER/PGPASSWORD), before alembic"
        )
    user = os.getenv("PGUSER", "").strip() or "postgres"
    password = os.getenv("PGPASSWORD", "")
    port = os.getenv("PGPORT", "").strip() or "5432"
    auth = f"{user}:{password}@" if password else f"{user}@"
    return f"postgresql+psycopg2://{auth}{host}:{port}/{db}"


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
