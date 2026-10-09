"""Il giro periodico della coda delle simulazioni (P0.3).

Ogni richiesta di run lancia gia' un drenaggio (BackgroundTask). Questo giro
copre cio' che nessuna richiesta sveglia: run rimessi in coda dopo il crash di
un processo, run in attesa quando un altro processo libera un posto. Tiene al
massimo ``simulation_max_concurrent_runs`` drenaggi propri; la presa esclusiva
su Postgres impedisce comunque di superare il limite del deploy.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from backend.settings import settings

logger = logging.getLogger(__name__)

_EVERY_SECONDS = 10.0


async def run_simulation_queue(every: float = _EVERY_SECONDS) -> None:
    if "pytest" in sys.modules:  # i test drenano la coda a mano, come per gli altri worker
        return
    if not settings.simulation_worker_in_process:
        logger.info("giro della coda simulazioni spento (simulation_worker_in_process=False)")
        return
    from backend.simulation.service import drain_simulation_queue, new_worker_id

    drains: set[asyncio.Task] = set()
    try:
        while True:
            drains = {task for task in drains if not task.done()}
            for _ in range(max(0, settings.simulation_max_concurrent_runs - len(drains))):
                drains.add(asyncio.create_task(_drain(drain_simulation_queue, new_worker_id())))
            await asyncio.sleep(every)
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
    except Exception:  # noqa: BLE001 - un giro storto non ferma la coda
        logger.exception("coda simulazioni: drenaggio fallito")
