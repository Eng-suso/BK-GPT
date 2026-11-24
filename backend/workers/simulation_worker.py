"""Il giro periodico della coda delle simulazioni (P0.3).

Ogni richiesta di run lancia gia' un drenaggio (BackgroundTask). Questo giro
copre cio' che nessuna richiesta sveglia: run rimessi in coda dopo il crash di
un processo, run in attesa quando un altro processo libera un posto. Tiene al
massimo ``simulation_max_concurrent_runs`` drenaggi propri; la presa esclusiva
su Postgres impedisce comunque di superare il limite del deploy.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from collections.abc import Awaitable, Callable

from sqlalchemy.exc import SQLAlchemyError

from backend.settings import settings

logger = logging.getLogger(__name__)

_EVERY_SECONDS = 10.0
# B6: una richiesta di run sveglia il giro subito invece di lasciarlo dormire
# fino a 10 s; il giro riempie i posti liberi del motore con i suoi drenaggi.
# L'evento nasce con il giro, nel suo event loop; senza giro (test, worker
# spento) svegliare non fa nulla e i run partono dal drenaggio della richiesta.
_wake: asyncio.Event | None = None


def wake_simulation_worker() -> None:
    """Il giro della coda riparte adesso (nello stesso processo): ci sono run nuovi."""
    if _wake is not None:
        _wake.set()


async def run_simulation_queue(every: float = _EVERY_SECONDS) -> None:
    if "pytest" in sys.modules:  # i test drenano la coda a mano, come per gli altri worker
        return
    if not settings.simulation_worker_in_process:
        logger.info("giro della coda simulazioni spento (simulation_worker_in_process=False)")
        return
    from backend.simulation.service import drain_simulation_queue, new_worker_id

    await serve_simulation_queue(drain_simulation_queue, new_worker_id, every)


async def serve_simulation_queue(
    drain: Callable[[str], Awaitable[int]], new_worker_id: Callable[[], str], every: float
) -> None:
    """Tiene ``simulation_max_concurrent_runs`` drenaggi, ogni ``every`` secondi o al risveglio."""
    global _wake
    wake = _wake = asyncio.Event()
    drains: set[asyncio.Task] = set()
    try:
        while True:
            wake.clear()
            drains = {task for task in drains if not task.done()}
            for _ in range(max(0, settings.simulation_max_concurrent_runs - len(drains))):
                drains.add(asyncio.create_task(_drain(drain, new_worker_id())))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(wake.wait(), every)
    except asyncio.CancelledError:
        for task in drains:
            task.cancel()
        await asyncio.gather(*drains, return_exceptions=True)
        raise


async def _drain(drain, worker_id: str) -> None:
    try:
        done = await drain(worker_id)
        if done:
            logger.info("coda simulazioni: %d run eseguiti da %s", done, worker_id)
    except asyncio.CancelledError:
        raise
    except (SQLAlchemyError, OSError):  # database o rete: il giro dopo riprova
        logger.exception("coda simulazioni: drenaggio fallito")
