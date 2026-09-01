"""Alembic environment per lo schema canonical DeliR.

Le migration sono scritte a mano con op.execute() (ruoli, RLS, policy, funzioni,
generated columns e pgvector non sono modellati bene da SQLAlchemy autogenerate),
quindi target_metadata resta None e non esiste --autogenerate.

La connessione usa SEMPRE il ruolo delir_migrator (owner dello schema).
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


def _migrator_url() -> str:
    url = settings.canonical_migrator_url
    if not url:
        raise RuntimeError(
            "canonical_migrator_url non configurata: serve il DSN del ruolo "
            "delir_migrator (postgresql+psycopg://delir_migrator:...@host:port/delir)."
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_migrator_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _migrator_url()
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
