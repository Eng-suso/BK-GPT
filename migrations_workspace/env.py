"""Alembic environment per il database operativo `workspace`.

Schema semplice (nessuna RLS, nessuna funzione): le migration si appoggiano ai
modelli SQLAlchemy (`metadata.create_all` dentro la revision). Il ruolo
`delir_workspace` possiede il database, quindi puo' fare DDL.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.settings import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _workspace_url() -> str:
    url = settings.workspace_database_url
    if not url:
        raise RuntimeError(
            "workspace_database_url non configurata: serve il DSN del database "
            "operativo (postgresql+psycopg://delir_workspace:...@host:port/workspace)."
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_workspace_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _workspace_url()
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
