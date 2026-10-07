"""Se il grafo di un cliente si puo' leggere: fresco, indietro, o non si sa.

Neo4j e' una proiezione di Postgres. Una proiezione indietro non e' un grafo
che sa meno: e' un grafo che puo' dire il falso - un arco cancellato che c'e'
ancora, un arco nuovo che non c'e'. Prima il gateway lo serviva lo stesso,
con un avviso accanto, e chi lo leggeva (l'agente) non aveva modo di pesarlo.

Qui la domanda ha tre risposte, e la terza conta quanto le altre:

- `FRESH`: la coda di proiezione di quel cliente e' sana, il grafo si legge;
- `STALE`: righe in dead-letter, bloccate, una pendente oltre la soglia, o un
  grafo scritto da un projector diverso da quello in uso;
- `CORRUPT`: la riconciliazione (`scripts/kg_reproject.py`) ha trovato il
  grafo diverso da Postgres. Non e' un ritardo che la coda recupera: resta
  finche' un confronto pulito non lo smentisce;
- `UNKNOWN`: non si puo' verificare (DSN del worker assente, coda o stato
  illeggibili).

Lo stato per cliente (watermark, versione del projector, guasto) sta in
`graph_projection_state`: vedi `knowledge_graph.projection_state`.

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
    CORRUPT = "corrupt"
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
    from backend.memory.knowledge_graph.projector import PROJECTOR_VERSION
    from backend.workers import graph_worker

    try:
        stats: dict[str, Any] = dict(graph_worker.queue_stats(client_id))
        state = graph_worker.client_projection_state(client_id)
    except Exception as exc:  # noqa: BLE001 - lo stato si dichiara sconosciuto, non si indovina
        logger.warning("stato della proiezione non leggibile per il cliente %s: %s", client_id, exc)
        return ProjectionReport(
            ProjectionHealth.UNKNOWN, reason="coda o stato della proiezione non leggibili"
        )

    if state is not None:
        stats["watermark"] = state.watermark
        stats["projector_version"] = state.projector_version
        if state.corrupt:
            return ProjectionReport(
                ProjectionHealth.CORRUPT,
                stats=stats,
                reason=(
                    "la riconciliazione ha trovato il grafo diverso da Postgres "
                    f"({state.corrupt_reason}): va ricostruito con scripts/kg_reproject.py --apply"
                ),
            )
        if state.projector_version != PROJECTOR_VERSION:
            return ProjectionReport(
                ProjectionHealth.STALE,
                stats=stats,
                reason=(
                    f"grafo scritto dal projector {state.projector_version}, quello in uso e' "
                    f"{PROJECTOR_VERSION}: va ricostruito con scripts/kg_reproject.py --apply"
                ),
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
