"""Lo stato della proiezione Neo4j di un cliente: fin dove, da chi, se guasta.

Una riga per cliente in `graph_projection_state` (migrazione 0019):

- `watermark`: l'id piu' alto di `graph_outbox` applicato per il cliente. Lo
  avanza il worker nella transazione in cui segna la riga processata, e solo
  in avanti: le righe si applicano in ordine di id, ma una riga ritentata puo'
  arrivare dopo una piu' recente;
- `projector_version`: la versione piu' vecchia che ha scritto il grafo. Il
  worker non la sovrascrive; solo una ricostruzione completa la porta avanti;
- `corrupt_since` / `corrupt_reason`: la riconciliazione ha trovato il grafo
  diverso da Postgres. Resta finche' un confronto pulito non lo smentisce.

Le funzioni ricevono la connessione: il worker scrive dentro la sua
transazione, la riconciliazione come delir_migrator, il gateway legge con la
DSN del worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, text

from backend.memory.knowledge_graph.projector import PROJECTOR_VERSION

_READ = text(
    "SELECT watermark, projector_version, corrupt_since, corrupt_reason, verified_at "
    "FROM graph_projection_state WHERE client_id = CAST(:cl AS uuid)"
)

_ADVANCE = text(
    "INSERT INTO graph_projection_state (client_id, watermark, projector_version) "
    "VALUES (CAST(:cl AS uuid), :wm, :v) "
    "ON CONFLICT (client_id) DO UPDATE SET "
    "  watermark = GREATEST(graph_projection_state.watermark, EXCLUDED.watermark), "
    "  updated_at = now()"
)

_MARK_CORRUPT = text(
    "INSERT INTO graph_projection_state "
    "  (client_id, projector_version, corrupt_since, corrupt_reason) "
    "VALUES (CAST(:cl AS uuid), :v, now(), :reason) "
    "ON CONFLICT (client_id) DO UPDATE SET "
    "  corrupt_since = COALESCE(graph_projection_state.corrupt_since, now()), "
    "  corrupt_reason = EXCLUDED.corrupt_reason, "
    "  updated_at = now()"
)

_MARK_VERIFIED = text(
    "INSERT INTO graph_projection_state (client_id, projector_version, verified_at) "
    "VALUES (CAST(:cl AS uuid), :v, now()) "
    "ON CONFLICT (client_id) DO UPDATE SET "
    "  corrupt_since = NULL, corrupt_reason = NULL, verified_at = now(), "
    "  projector_version = CASE WHEN :rebuilt THEN EXCLUDED.projector_version "
    "                           ELSE graph_projection_state.projector_version END, "
    "  updated_at = now()"
)


@dataclass(frozen=True)
class ProjectionState:
    watermark: int
    projector_version: str
    corrupt_since: datetime | None
    corrupt_reason: str | None
    verified_at: datetime | None

    @property
    def corrupt(self) -> bool:
        return self.corrupt_since is not None


def read(conn: Connection, client_id: str) -> ProjectionState | None:
    """Lo stato del cliente, o None se il suo grafo non ha mai ricevuto niente."""
    row = conn.execute(_READ, {"cl": str(client_id)}).one_or_none()
    if row is None:
        return None
    return ProjectionState(
        watermark=int(row.watermark),
        projector_version=str(row.projector_version),
        corrupt_since=row.corrupt_since,
        corrupt_reason=row.corrupt_reason,
        verified_at=row.verified_at,
    )


def advance_watermark(conn: Connection, client_id: str, outbox_id: int) -> None:
    """Il grafo del cliente comprende la riga `outbox_id` di `graph_outbox`."""
    conn.execute(_ADVANCE, {"cl": str(client_id), "wm": int(outbox_id), "v": PROJECTOR_VERSION})


def mark_corrupt(conn: Connection, client_id: str, reason: str) -> None:
    """La riconciliazione ha trovato il grafo diverso da Postgres.

    `corrupt_since` resta quello della prima volta: un grafo guasto da tre
    giorni non diventa guasto da adesso perche' lo si e' ricontrollato.
    """
    conn.execute(_MARK_CORRUPT, {"cl": str(client_id), "v": PROJECTOR_VERSION, "reason": reason})


def mark_verified(conn: Connection, client_id: str, *, rebuilt: bool) -> None:
    """Un confronto pulito: il grafo coincide con Postgres.

    `rebuilt`: il grafo e' appena stato riscritto tutto dal projector in uso,
    quindi la sua versione e' quella. Un confronto senza ricostruzione non la
    cambia: dice che i dati coincidono, non chi li ha scritti.
    """
    conn.execute(
        _MARK_VERIFIED, {"cl": str(client_id), "v": PROJECTOR_VERSION, "rebuilt": rebuilt}
    )
