"""Driver Neo4j condiviso (projection grafo tipizzato, INV-8).

Solo la connessione. La proiezione e' in projector.py, il drain in
backend/workers/graph_worker.py. Se `neo4j_password` non e' configurata il
grafo e' disattivato e i chiamanti degradano.
"""

from __future__ import annotations

from functools import lru_cache

from backend.settings import settings


@lru_cache(maxsize=1)
def get_driver():
    if not settings.neo4j_password:
        return None
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.neo4j_url,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    return driver


def is_enabled() -> bool:
    return get_driver() is not None


class Neo4jUnavailable(RuntimeError):
    """Il driver Neo4j non e' configurato/raggiungibile: un'operazione che DEVE
    completare (es. erasure INV-10) non puo' fingere successo."""


def purge_client(client_id: str, *, batch_size: int = 10_000) -> int:
    """Rimuove da Neo4j tutti i nodi di un cliente (INV-10). Ritorna i nodi cancellati.

    Fail closed: se il driver non c'e' solleva `Neo4jUnavailable` invece di
    ritornare 0 — un'erasure non deve essere segnalata completa senza esserlo.
    La DETACH DELETE e' batchata per non aprire una transazione illimitata su
    un cliente grande.
    """
    cid = str(client_id or "").strip()
    if not cid:
        raise ValueError("purge_client richiede un client_id non vuoto")
    driver = get_driver()
    if driver is None:
        raise Neo4jUnavailable(
            "Neo4j non configurato: purge_client non puo' garantire l'erasure"
        )
    size = max(1, int(batch_size))
    deleted = 0
    with driver.session() as session:
        while True:
            removed = session.execute_write(_purge_batch, cid, size)
            deleted += removed
            if removed < size:
                return deleted


def _purge_batch(tx, client_id: str, size: int) -> int:
    result = tx.run(
        "MATCH (n {client_id: $cid}) WITH n LIMIT $lim "
        "DETACH DELETE n RETURN count(n) AS n",
        cid=client_id,
        lim=size,
    )
    return int(result.single()["n"])
