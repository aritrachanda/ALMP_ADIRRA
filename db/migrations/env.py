"""Alembic environment for the ADIRRA governance database.

Builds the connection string from ``project.yaml`` (``database:`` section) plus the
``ADM_DB_PASSWORD`` env var (loaded from ``.env``) — no DSN or secret is stored in
alembic.ini, per the repo convention (config in project.yaml, password in .env).

Synchronous psycopg 3 driver. ``target_metadata`` is intentionally ``None`` for now:
the initial migration is authored by hand (raw DDL). Phase 2 introduces the SQLAlchemy
ORM models and wires their metadata here to enable ``--autogenerate``.
"""
from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

import yaml
from alembic import context
from sqlalchemy import engine_from_config, pool

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv always present in this repo
    load_dotenv = None

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ORM metadata for autogenerate (advisory — hand-written migrations remain the source of
# truth for the generated column, partial indexes and CHECK constraints).
try:
    from core.shared.models import Base as _SharedBase

    target_metadata = _SharedBase.metadata
except Exception:
    target_metadata = None

_ROOT = Path(__file__).resolve().parents[2]


def _build_url() -> str:
    """Assemble the Postgres DSN. Delegates to core.glossary_db.db.build_dsn so the
    ADM_DATABASE_URL override (used by tests to target a throwaway database) is honoured
    consistently by both the app and Alembic."""
    try:
        from core.glossary_db.db import build_dsn

        return build_dsn()
    except Exception:
        # Fallback: build directly from project.yaml + .env (keeps Alembic usable even if
        # the package import fails for any reason).
        if load_dotenv is not None:
            load_dotenv(_ROOT / ".env")
        with (_ROOT / "project.yaml").open(encoding="utf-8") as fh:
            project = yaml.safe_load(fh) or {}
        db = project.get("database", {}) or {}
        password = os.environ.get(db.get("password_env", "ADM_DB_PASSWORD"), "adm_local_dev")
        return (f"postgresql+psycopg://{db.get('user','adm')}:{password}"
                f"@{db.get('host','localhost')}:{db.get('port',5432)}/{db.get('name','adm')}")


def run_migrations_offline() -> None:
    context.configure(
        url=_build_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema="public",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _build_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
