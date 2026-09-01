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


def purge_client(client_id: str) -> int:
    """Rimuove da Neo4j tutti i nodi di un cliente (INV-10). Ritorna i nodi cancellati."""
    driver = get_driver()
    if driver is None:
        return 0
    with driver.session() as session:
        result = session.run(
            "MATCH (n {client_id: $cid}) DETACH DELETE n RETURN count(n) AS n",
            cid=str(client_id),
        )
        return int(result.single()["n"])
