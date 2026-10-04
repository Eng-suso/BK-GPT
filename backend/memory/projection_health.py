"""Se il grafo di un cliente si puo' leggere: fresco, indietro, o non si sa.

Neo4j e' una proiezione di Postgres. Una proiezione indietro non e' un grafo
che sa meno: e' un grafo che puo' dire il falso - un arco cancellato che c'e'
ancora, un arco nuovo che non c'e'. Prima il gateway lo serviva lo stesso,
con un avviso accanto, e chi lo leggeva (l'agente) non aveva modo di pesarlo.

Qui la domanda ha tre risposte, e la terza conta quanto le altre:

- `FRESH`: la coda di proiezione di quel cliente e' sana, il grafo si legge;
- `STALE`: righe in dead-letter, bloccate, o una pendente oltre la soglia;
- `UNKNOWN`: non si puo' verificare (DSN del worker assente, coda illeggibile).

`UNKNOWN` non e' `FRESH`. Chi legge decide cosa fare di uno stato non
verificato, ma non lo scambia mai per uno verificato: il gateway, in entrambi
i casi, ripiega su Postgres.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from backend.settings import settings

logger = logging.getLogger(__name__)


class ProjectionHealth(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProjectionReport:
    """Lo stato della proiezione di un cliente e da cosa lo si e' dedotto."""

    health: ProjectionHealth
    # Le statistiche della coda, quando si sono potute leggere.
    stats: dict[str, Any] | None = None
    # Perche' non e' `FRESH`, in una frase per i log e per chi legge l'esito.
    reason: str | None = None

    @property
    def readable(self) -> bool:
        """Il grafo si puo' servire cosi' com'e'."""
        return self.health is ProjectionHealth.FRESH


# Una lettura sulle code a ogni retrieve; la risposta non cambia alla velocita'
# delle chiamate.
_TTL_S = 5.0
_cache: dict[str, tuple[float, ProjectionReport]] = {}
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def projection_report(client_id: str) -> ProjectionReport:
    """Lo stato della proiezione Neo4j di un cliente.

    Indietro vuol dire: righe in dead-letter (archi che non arriveranno finche'
    qualcuno non ripara, `scripts/kg_reproject.py`), righe bloccate, o una riga
    pendente piu' vecchia di `graph_staleness_warn_seconds`. Il numero di
    pendenti da solo no: una coda con lavoro fresco e' una coda che funziona.
    """
    if not settings.canonical_worker_url:
        # Il gateway gira come delir_app, che su graph_outbox puo' solo
        # scrivere: senza il DSN del worker la coda non si legge.
        return ProjectionReport(
            ProjectionHealth.UNKNOWN, reason="coda di proiezione non leggibile: manca il DSN del worker"
        )

    now = time.monotonic()
    with _lock:
        hit = _cache.get(client_id)
    if hit and now - hit[0] < _TTL_S:
        return hit[1]

    report = _measure(client_id)
    with _lock:
        _cache[client_id] = (now, report)
    return report


def _measure(client_id: str) -> ProjectionReport:
    from backend.workers import graph_worker

    try:
        stats = dict(graph_worker.queue_stats(client_id))
    except Exception as exc:  # noqa: BLE001 - lo stato si dichiara sconosciuto, non si indovina
        logger.warning("stato della proiezione non leggibile per il cliente %s: %s", client_id, exc)
        return ProjectionReport(
            ProjectionHealth.UNKNOWN, reason="coda di proiezione non leggibile"
        )

    if stats["dead_letter"] > 0:
        reason = f"{stats['dead_letter']} righe in dead-letter: non arriveranno senza riparazione"
    elif stats["stuck"] > 0:
        reason = f"{stats['stuck']} righe bloccate dopo troppi tentativi"
    elif stats["oldest_pending_age_s"] > settings.graph_staleness_warn_seconds:
        reason = f"una riga aspetta da {stats['oldest_pending_age_s']} s"
    else:
        return ProjectionReport(ProjectionHealth.FRESH, stats=stats)
    return ProjectionReport(ProjectionHealth.STALE, stats=stats, reason=reason)
