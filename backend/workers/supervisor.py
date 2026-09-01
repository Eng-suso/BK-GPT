"""Supervisore in-process delle code (INV-7).

Quando il canonical e' configurato, l'app FastAPI drena `graph_outbox` +
`mem0_projection_log` in due task di background: la pipeline
canonical -> Neo4j / Mem0 gira senza processi separati.

Per scalare o isolare i worker: `settings.workers_in_process = False` +
`python -m backend.workers.graph_worker` / `.mem0_worker` come service.
`FOR UPDATE SKIP LOCKED` rende sicuro anche farli girare in parallelo
all'app.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable

from backend.settings import settings

logger = logging.getLogger(__name__)

_STATS_EVERY_SECONDS = 120.0
_PRUNE_EVERY_SECONDS = 3600.0


async def _drain_loop(
    name: str,
    drain_once: Callable[[], int],
    stats: Callable[[], dict[str, int]],
    idle_sleep: float,
    prune: Callable[[], int] | None = None,
) -> None:
    loop = asyncio.get_running_loop()
    next_report = loop.time()
    next_prune = loop.time() + _PRUNE_EVERY_SECONDS
    while True:
        try:
            processed = await asyncio.to_thread(drain_once)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — una passata storta non ferma il loop
            logger.exception("%s: passata fallita", name)
            processed = 0

        now = loop.time()
        if now >= next_report:
            next_report = now + _STATS_EVERY_SECONDS
            try:
                s = await asyncio.to_thread(stats)
                if s["stuck"]:
                    logger.warning("%s: %d in coda, %d bloccati (dead-letter)", name, s["pending"], s["stuck"])
                elif s["pending"]:
                    logger.info("%s: %d in coda", name, s["pending"])
            except Exception:  # noqa: BLE001
                logger.debug("%s: queue_stats fallito", name, exc_info=True)

        if prune is not None and now >= next_prune:
            next_prune = now + _PRUNE_EVERY_SECONDS
            try:
                removed = await asyncio.to_thread(prune)
                if removed:
                    logger.info("%s: potate %d righe processate", name, removed)
            except Exception:  # noqa: BLE001
                logger.debug("%s: prune fallito", name, exc_info=True)

        await asyncio.sleep(0.0 if processed else idle_sleep)


async def run_queue_workers() -> None:
    """Avvia i loop di drain e resta finche' non viene cancellato (lifespan)."""
    if "pytest" in sys.modules:  # i test drenano le code a mano
        return
    if not settings.workers_in_process:
        logger.info("worker in-process disattivati (workers_in_process=False)")
        return
    if not settings.canonical_worker_url:
        logger.info("canonical non configurato: worker in-process non avviati")
        return

    from backend.workers import graph_worker, mem0_worker

    tasks = [
        asyncio.create_task(
            _drain_loop(
                "graph_worker", graph_worker.drain_once, graph_worker.queue_stats,
                2.0, graph_worker.prune,
            ),
            name="graph_worker",
        ),
        asyncio.create_task(
            _drain_loop(
                "mem0_worker", mem0_worker.drain_once, mem0_worker.queue_stats,
                3.0, mem0_worker.prune,
            ),
            name="mem0_worker",
        ),
    ]
    logger.info("worker in-process avviati (graph + mem0)")
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
