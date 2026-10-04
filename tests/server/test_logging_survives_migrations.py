"""Le migrazioni allo startup non spengono i log del backend.

Il lifespan dell'app chiama `ensure_schema()`, che esegue Alembic nello stesso
processo. L'`env.py` di Alembic chiamava `fileConfig(...)` con il default
`disable_existing_loggers=True`: ogni logger gia' creato - cioe' quelli di
tutti i moduli del backend importati prima dello startup - veniva spento, e
da li' in poi i loro `logger.warning` non arrivavano da nessuna parte.
"""

from __future__ import annotations

import logging

import pytest

from backend.settings import settings

pytestmark = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)


def test_backend_loggers_still_log_after_the_startup_migrations():
    from backend import local_store

    probe = logging.getLogger("backend.probe_migrazioni")
    root_handlers = list(logging.getLogger().handlers)

    local_store.ensure_schema.cache_clear()
    local_store.ensure_schema()

    assert not probe.disabled
    assert logging.getLogger().handlers == root_handlers
