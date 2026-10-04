"""Cancellare un processo, un progetto o un cliente cancella la sua evidenza (GR-13).

Prima: `workspace_database.delete_process` toglieva la riga workspace e il
modello BPMN, e basta. Nel cervello restava tutto: riga `process` canonical,
claim, entita', fonti e chunk, nodi Neo4j, episodi (le interviste), memorie
Mem0. E siccome l'id workspace di un processo e' lo slug del nome, reso unico
solo contro il database workspace di *adesso*, ricreare un processo con lo
stesso nome riprendeva lo slug, `scope.resolve` restituiva il vecchio processo
canonical, e l'evidenza cancellata tornava in scope. Dati cancellati
dall'utente che ricompaiono.

Qui la cancellazione tocca i quattro posti in cui l'evidenza vive:

    KG canonical   righe kg_* di quel processo/progetto/cliente, fonti e chunk,
                   ingestion ancora in coda (altrimenti la riscriverebbe dopo)
    Neo4j          node_delete / edge_delete nell'outbox, nella stessa
                   transazione (INV-7: Neo4j si tocca solo via worker)
    memorie        semantic_memory / episodic_memory canonical + le loro copie
                   Mem0, con `forget.execute_forget`: lapide prima, delete dopo,
                   quindi anche un delete Mem0 fallito resta fuori dal recall
    episodi        le righe dell'episodic store, che si legano al processo per
                   **slug workspace**: sono l'altro canale da cui l'evidenza
                   tornava

Cancellare la riga `process` canonical da sola sarebbe peggio del bug: le FK
delle righe kg_* verso `process` sono `ON DELETE SET NULL`, e una riga con
`process_id NULL` nel progetto e' evidenza *project-level*, leggibile da tutti
gli altri processi del progetto. Per questo l'evidenza del processo si cancella
esplicitamente, prima della riga.

Entita' condivise. L'entity resolution fonde lo stesso attore visto da due
processi in una riga sola: un'entita' del processo cancellato che ha fonti anche
in un altro processo resta, perde le fonti cancellate e passa al processo di una
fonte che le rimane. Lo stesso vale per `source_ids` di tutte le righe kg_* di
altri processi: le fonti cancellate si tolgono, la riga resta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import create_engine, text

from backend.db import canonical_session
from backend.memory import forget
from backend.memory.knowledge_graph import canonical
from backend.settings import settings

logger = logging.getLogger(__name__)

_NODE_TABLES = {
    "kg_claim": ("Claim", "claim_id"),
    "kg_gap": ("Gap", "gap_id"),
    "kg_contradiction": ("Contradiction", "contradiction_id"),
    "kg_impact": ("Impact", "impact_id"),
    "kg_entity": ("Entity", "entity_id"),
    "kg_evidence": ("Evidence", "evidence_id"),
    "kg_source": ("Source", "source_id"),
}
_SOURCED_TABLES = ("kg_entity", "kg_relation", "kg_claim", "kg_gap", "kg_contradiction", "kg_impact")
_AFFECTING_TABLES = ("kg_gap", "kg_contradiction", "kg_impact")


@dataclass
class EraseReport:
    scope: str
    workspace_id: str
    canonical_id: str | None = None
    rows: dict[str, int] = field(default_factory=dict)
    graph_deletes: int = 0
    memories: dict[str, Any] = field(default_factory=dict)
    episodes: int = 0
    skipped: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "workspace_id": self.workspace_id,
            "canonical_id": self.canonical_id,
            "rows": self.rows,
            "graph_deletes": self.graph_deletes,
            "memories": self.memories,
            "episodes": self.episodes,
            "skipped": self.skipped,
        }


# --------------------------------------------------------------------------- #
# pezzi comuni
# --------------------------------------------------------------------------- #

def _consultant() -> str:
    return settings.default_consultant_id


def _lookup(table: str, workspace_id: str) -> Any | None:
    """La riga canonical mappata da un id workspace, senza crearla (a
    differenza di `scope.resolve`)."""
    columns = {"client": "id", "project": "id, client_id", "process": "id, client_id, project_id"}
    with canonical_session(_consultant()) as session:
        return session.execute(
            text(
                f"SELECT {columns[table]} "
                f"FROM {table} WHERE consultant_id = :c AND workspace_id = :w"
            ),
            {"c": _consultant(), "w": workspace_id},
        ).first()


def _project_workspace_id(canonical_project_id: str) -> str | None:
    """L'id workspace del progetto canonical, per verificare a chi appartiene un processo."""
    with canonical_session(_consultant()) as session:
        return session.execute(
            text(
                "SELECT workspace_id FROM project "
                "WHERE consultant_id = :c AND id = CAST(:p AS uuid)"
            ),
            {"c": _consultant(), "p": canonical_project_id},
        ).scalar_one_or_none()


def _emit_node_delete(session, client_id: str, label: str, id_prop: str, node_id: str) -> None:
    canonical._emit(
        session,
        aggregate_type=label.lower(),
        aggregate_id=node_id,
        consultant_id=_consultant(),
        client_id=client_id,
        op="delete",
        payload={"kind": "node_delete", "label": label, "id_prop": id_prop, "id_value": node_id},
    )


def _emit_relation_delete(session, client_id: str, row: Any) -> None:
    canonical._emit(
        session,
        aggregate_type="relation",
        aggregate_id=str(row.id),
        consultant_id=_consultant(),
        client_id=client_id,
        op="delete",
        payload={
            "kind": "edge_delete",
            "label": row.relation,
            "source": {"label": "Entity", "id_prop": "entity_id",
                       "id_value": str(row.source_entity_id)},
            "target": {"label": "Entity", "id_prop": "entity_id",
                       "id_value": str(row.target_entity_id)},
        },
    )


def _mem0_ids(memory_ids: list[str]) -> dict[str, list[str]]:
    """memory_id canonical -> id Mem0 gia' applicati. Il log lo legge solo
    `delir_worker`: senza quella DSN si torna vuoto e resta la lapide per testo."""
    if not memory_ids or not settings.canonical_worker_url:
        return {}
    engine = create_engine(settings.canonical_worker_url, future=True)
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    "SELECT memory_id, mem0_memory_id FROM mem0_projection_log "
                    "WHERE memory_id = ANY(CAST(:ids AS uuid[])) AND mem0_memory_id IS NOT NULL"
                ),
                {"ids": memory_ids},
            ).all()
    finally:
        engine.dispose()
    out: dict[str, list[str]] = {}
    for row in rows:
        out.setdefault(str(row.memory_id), []).append(str(row.mem0_memory_id))
    return out


def _forget_memories(client_id: str, where: str, params: dict[str, Any], reason: str) -> dict:
    """Memorie semantiche ed episodiche che cadono nello scope: lapide + delete
    Mem0 (`forget.execute_forget`), poi via le righe canonical."""
    with canonical_session(_consultant(), client_id) as session:
        semantic = session.execute(
            text(f"SELECT id, statement AS text FROM semantic_memory WHERE {where}"), params
        ).all()
        episodic = session.execute(
            text(
                "SELECT id, coalesce(nullif(summary, ''), title) AS text "
                f"FROM episodic_memory WHERE {where}"
            ),
            params,
        ).all()
    rows = [*semantic, *episodic]
    if not rows:
        return {"canonical": 0}
    mem0 = _mem0_ids([str(r.id) for r in rows])
    targets: list[dict[str, Any]] = []
    for row in rows:
        ids = mem0.get(str(row.id)) or [None]
        targets.extend({"memory_id": mid, "statement": row.text or ""} for mid in ids)
    outcome = forget.execute_forget(
        consultant_id=_consultant(),
        mem0_user_id=settings.mem0_user_id,
        targets=targets,
        reason=reason,
        client_id=client_id,
    )
    if outcome.get("status") != "ok":
        # La lapide e' gia' scritta: il recall le filtra comunque. Un delete Mem0
        # mancato e' spazio non recuperato, non un dato che torna.
        logger.warning("erase: memorie Mem0 non tutte eliminate (%s)", outcome)
    with canonical_session(_consultant(), client_id) as session:
        for table in ("semantic_memory", "episodic_memory"):
            session.execute(text(f"DELETE FROM {table} WHERE {where}"), params)
    return {
        "canonical": len(rows),
        "mem0_deleted": len(outcome.get("deleted") or []),
        "mem0_failed": len(outcome.get("failed") or []),
        "status": outcome.get("status"),
    }


def _delete_episodes(*, project: str, process_id: str | None = None) -> int:
    """Righe dell'episodic store: si legano al processo per slug workspace, e
    con lo slug riusato tornerebbero nel processo nuovo."""
    from backend.memory.episodic import episodic_store

    deleted = 0
    while True:
        batch = episodic_store.list_episode_memory(
            project=project, process_id=process_id, status="any", limit=100
        )
        if not batch:
            return deleted
        for episode in batch:
            result = episodic_store.delete_episode_memory(
                episode["episode_id"], confirm_destructive_action=True, delete_raw_source=True
            )
            if result.get("status") != "deleted":
                raise RuntimeError(f"episodio {episode['episode_id']} non eliminato: {result}")
            deleted += 1


# --------------------------------------------------------------------------- #
# processo
# --------------------------------------------------------------------------- #

def erase_process(workspace_project_id: str, workspace_process_id: str) -> EraseReport:
    report = EraseReport(scope="process", workspace_id=workspace_process_id)
    report.episodes = _delete_episodes(project=workspace_project_id, process_id=workspace_process_id)
    if not settings.canonical_database_url:
        report.skipped = "canonical non configurato"
        return report
    row = _lookup("process", workspace_process_id)
    if row is None:
        report.skipped = "processo mai materializzato nel canonical"
        return report
    process_id, client_id = str(row.id), str(row.client_id)
    report.canonical_id = process_id
    # Lo slug da solo non basta: se la riga canonical che lo porta e' di un
    # altro progetto (un database workspace diverso sullo stesso canonical, o
    # una cancellazione di prima di GR-13 non ancora staccata da `scope`),
    # l'evidenza non e' di questo processo. Cancellare e' irreversibile: nel
    # dubbio si lascia, e il report lo dice.
    if _project_workspace_id(str(row.project_id)) != workspace_project_id:
        report.skipped = "lo slug e' mappato al processo di un altro progetto"
        return report

    report.memories = _forget_memories(
        client_id, "process_id = CAST(:p AS uuid)", {"p": process_id},
        reason=f"processo eliminato: {workspace_process_id}",
    )
    report.rows, report.graph_deletes = _erase_process_kg(process_id, client_id)
    with canonical_session(_consultant()) as session:
        session.execute(text("DELETE FROM process WHERE id = CAST(:p AS uuid)"), {"p": process_id})
        _emit_node_delete(session, client_id, "Process", "process_id", process_id)
    report.graph_deletes += 1
    report.rows["process"] = 1
    return report


def _erase_process_kg(process_id: str, client_id: str) -> tuple[dict[str, int], int]:
    p = {"p": process_id}
    rows: dict[str, int] = {}
    graph = 0
    with canonical_session(_consultant(), client_id) as session:
        sources = [str(r.id) for r in session.execute(
            text("SELECT id FROM kg_source WHERE process_id = CAST(:p AS uuid)"), p
        )]
        claims = [str(r.id) for r in session.execute(
            text("SELECT id FROM kg_claim WHERE process_id = CAST(:p AS uuid)"), p
        )]
        sp = {**p, "src": sources, "claims": claims}

        # l'ingestion in coda riscriverebbe l'evidenza dopo la cancellazione
        rows["kg_ingest_queue"] = session.execute(
            text("DELETE FROM kg_ingest_queue WHERE process_id = CAST(:p AS uuid)"), p
        ).rowcount

        # una contraddizione con un lato cancellato non e' piu' una contraddizione,
        # e le sue `conflicting_statements` citano testo cancellato
        for table, extra in (
            ("kg_contradiction", " OR conflicting_claim_ids && CAST(:claims AS uuid[])"),
            ("kg_claim", ""), ("kg_gap", ""), ("kg_impact", ""),
        ):
            label, id_prop = _NODE_TABLES[table]
            deleted = session.execute(
                text(f"DELETE FROM {table} WHERE process_id = CAST(:p AS uuid){extra} RETURNING id"),
                sp,
            ).all()
            for r in deleted:
                _emit_node_delete(session, client_id, label, id_prop, str(r.id))
            rows[table] = len(deleted)
            graph += len(deleted)

        # entita': si tengono solo quelle con fonti in un altro processo
        owned = session.execute(
            text("SELECT id, source_ids FROM kg_entity WHERE process_id = CAST(:p AS uuid)"), p
        ).all()
        drop, keep = [], []
        for r in owned:
            others = [str(s) for s in (r.source_ids or ()) if str(s) not in set(sources)]
            (keep if others else drop).append((str(r.id), others))
        for entity_id, others in keep:
            session.execute(
                text(
                    "UPDATE kg_entity SET source_ids = CAST(:o AS uuid[]), process_id = ("
                    "  SELECT process_id FROM kg_source WHERE id = ANY(CAST(:o AS uuid[])) "
                    "  AND process_id IS NOT NULL LIMIT 1) "
                    "WHERE id = CAST(:e AS uuid)"
                ),
                {"o": others, "e": entity_id},
            )

        # relazioni del processo fra entita' che restano: arco da togliere a mano
        # (quelle verso entita' cancellate spariscono con il DETACH DELETE)
        dropped = {e for e, _ in drop}
        relations = session.execute(
            text(
                "DELETE FROM kg_relation WHERE process_id = CAST(:p AS uuid) "
                "RETURNING id, relation, source_entity_id, target_entity_id"
            ),
            p,
        ).all()
        for r in relations:
            if str(r.source_entity_id) not in dropped and str(r.target_entity_id) not in dropped:
                _emit_relation_delete(session, client_id, r)
                graph += 1
        rows["kg_relation"] = len(relations)

        if drop:
            session.execute(
                text("DELETE FROM kg_entity WHERE id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": list(dropped)},
            )
            for entity_id in dropped:
                _emit_node_delete(session, client_id, "Entity", "entity_id", entity_id)
        rows["kg_entity"] = len(drop)
        rows["kg_entity_kept"] = len(keep)
        graph += len(drop)

        # righe di altri processi: via le fonti cancellate e il processo dai colpiti
        if sources:
            for table in _SOURCED_TABLES:
                session.execute(
                    text(
                        f"UPDATE {table} SET source_ids = ARRAY("
                        "  SELECT unnest(source_ids) EXCEPT SELECT unnest(CAST(:src AS uuid[]))) "
                        "WHERE source_ids && CAST(:src AS uuid[])"
                    ),
                    sp,
                )
        for table in _AFFECTING_TABLES:
            session.execute(
                text(
                    f"UPDATE {table} SET affected_process_ids = "
                    "  array_remove(affected_process_ids, CAST(:p AS uuid)) "
                    "WHERE CAST(:p AS uuid) = ANY(affected_process_ids)"
                ),
                p,
            )

        # le porzioni dei file vanno via in cascata con la fonte: in Neo4j no
        evidence = session.execute(
            text(
                "SELECT e.id FROM kg_evidence e JOIN kg_source s ON s.id = e.source_id "
                "WHERE s.process_id = CAST(:p AS uuid)"
            ),
            p,
        ).all()
        for r in evidence:
            _emit_node_delete(session, client_id, "Evidence", "evidence_id", str(r.id))
        rows["kg_evidence"] = len(evidence)
        for source_id in sources:
            _emit_node_delete(session, client_id, "Source", "source_id", source_id)
        graph += len(evidence) + len(sources)

        rows["kg_source"] = session.execute(
            text("DELETE FROM kg_source WHERE process_id = CAST(:p AS uuid)"), p
        ).rowcount  # kg_chunk e kg_evidence vanno via in cascata
    return rows, graph


# --------------------------------------------------------------------------- #
# progetto e cliente
# --------------------------------------------------------------------------- #

def erase_project(workspace_project_id: str) -> EraseReport:
    report = EraseReport(scope="project", workspace_id=workspace_project_id)
    report.episodes = _delete_episodes(project=workspace_project_id)
    if not settings.canonical_database_url:
        report.skipped = "canonical non configurato"
        return report
    row = _lookup("project", workspace_project_id)
    if row is None:
        report.skipped = "progetto mai materializzato nel canonical"
        return report
    project_id, client_id = str(row.id), str(row.client_id)
    report.canonical_id = project_id
    report.memories = _forget_memories(
        client_id, "project_id = CAST(:pj AS uuid)", {"pj": project_id},
        reason=f"progetto eliminato: {workspace_project_id}",
    )
    report.graph_deletes = _erase_scope_rows(
        client_id, "project_id = CAST(:pj AS uuid)", {"pj": project_id}, report.rows
    )
    with canonical_session(_consultant()) as session:
        # tutto il resto (kg_*, fonti, chunk, processi) va via in cascata
        report.rows["project"] = session.execute(
            text("DELETE FROM project WHERE id = CAST(:pj AS uuid)"), {"pj": project_id}
        ).rowcount
    return report


def _erase_scope_rows(client_id: str, where: str, params: dict[str, Any], rows: dict) -> int:
    """Per progetto e cliente la cascata delle FK cancella le righe Postgres; qui
    si accodano i delete Neo4j dei loro nodi e si svuota l'ingestion in coda."""
    graph = 0
    with canonical_session(_consultant(), client_id) as session:
        rows["kg_ingest_queue"] = session.execute(
            text(f"DELETE FROM kg_ingest_queue WHERE {where}"), params
        ).rowcount
        for table, (label, id_prop) in (*_NODE_TABLES.items(), ("process", ("Process", "process_id"))):
            ids = [str(r.id) for r in session.execute(
                text(f"SELECT id FROM {table} WHERE {where}"), params
            )]
            for node_id in ids:
                _emit_node_delete(session, client_id, label, id_prop, node_id)
            rows[table] = len(ids)
            graph += len(ids)
    return graph


def erase_client_sources(client_name: str, workspace_source_ids: list[str]) -> EraseReport:
    """Le fonti caricate per tutto il cliente (P1.16) escono dal grafo.

    Non stanno sotto nessun progetto, quindi `erase_project` non le vede; e la
    cancellazione del cliente canonical salta quando un altro cliente workspace
    porta lo stesso nome. Qui si tolgono una per una, per id workspace.
    """
    from backend.memory.scope import _slug

    workspace_id = f"client:{_slug(client_name)}"
    report = EraseReport(scope="client_sources", workspace_id=workspace_id)
    if not settings.canonical_database_url:
        report.skipped = "canonical non configurato"
        return report
    row = _lookup("client", workspace_id)
    if row is None:
        report.skipped = "cliente mai materializzato nel canonical"
        return report
    report.canonical_id = str(row.id)
    report.graph_deletes = canonical.erase_workspace_sources(
        _consultant(), str(row.id), workspace_source_ids
    )
    return report


def erase_client(client_name: str, workspace_project_ids: list[str]) -> list[EraseReport]:
    """Ogni progetto del cliente, poi il cliente canonical se non gli resta
    niente. Il cliente canonical e' identificato dal nome (`client:<slug>`,
    `scope.resolve`): se un altro progetto workspace ancora vivo usa lo stesso
    nome di cliente, quel cliente canonical e' anche suo e non si tocca."""
    from backend.memory.scope import _slug

    reports = [erase_project(pid) for pid in workspace_project_ids]
    if not settings.canonical_database_url or not client_name.strip():
        return reports
    workspace_id = f"client:{_slug(client_name)}"
    report = EraseReport(scope="client", workspace_id=workspace_id)
    row = _lookup("client", workspace_id)
    if row is None:
        report.skipped = "cliente mai materializzato nel canonical"
        return [*reports, report]
    client_id = str(row.id)
    report.canonical_id = client_id
    with canonical_session(_consultant(), client_id) as session:
        remaining = session.execute(
            text("SELECT count(*) FROM project WHERE client_id = CAST(:cl AS uuid)"),
            {"cl": client_id},
        ).scalar_one()
    if remaining:
        report.skipped = f"il cliente canonical ha ancora {remaining} progetti di altri clienti workspace"
        return [*reports, report]
    report.memories = _forget_memories(
        client_id, "client_id = CAST(:cl AS uuid)", {"cl": client_id},
        reason=f"cliente eliminato: {client_name}",
    )
    report.graph_deletes = _erase_scope_rows(
        client_id, "client_id = CAST(:cl AS uuid)", {"cl": client_id}, report.rows
    )
    with canonical_session(_consultant()) as session:
        report.rows["client"] = session.execute(
            text("DELETE FROM client WHERE id = CAST(:cl AS uuid)"), {"cl": client_id}
        ).rowcount
    return [*reports, report]
