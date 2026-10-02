"""GR-13 — cancellare un processo cancella la sua evidenza, e un processo
ricreato con lo stesso nome parte vuoto (docs/graph-rag-remediation.md).

Il difetto: l'id workspace di un processo e' lo slug del nome, reso unico solo
contro il database workspace di adesso. Cancellato "Ciclo passivo", lo slug
`ciclo-passivo` tornava libero; ricreandolo, `scope.resolve` restituiva il
vecchio processo canonical e con lui claim, fonti, chunk ed episodi - dati che
l'utente aveva cancellato.

Il percorso e' quello vero: tool dell'agente -> coda di ingestion -> worker ->
Neo4j, e `workspace_database.delete_process` come lo chiama la route.

Servono le DSN canonical + workspace + NEO4J_PASSWORD.
"""

from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings

_NEEDED = (
    settings.workspace_database_url,
    settings.canonical_migrator_url,
    settings.canonical_database_url,
    settings.canonical_worker_url,
    settings.neo4j_password,
)
if not all(_NEEDED):
    pytest.skip(
        "servono WORKSPACE_DATABASE_URL + le DSN canonical + NEO4J_PASSWORD",
        allow_module_level=True,
    )

from backend import workspace_database as wd  # noqa: E402
from backend.memory import gateway  # noqa: E402
from backend.memory import scope as canonical_scope  # noqa: E402
from backend.memory.episodic import episodic_store  # noqa: E402
from backend.memory.knowledge_graph import neo4j_store  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)

SENTINEL = "codice fornitore ZX-4471"
INTERVIEW = {
    "title": "Intervista Paola Rinaldi - Contabilita' fornitori",
    "participants": ["Paola Rinaldi"],
    "entities": ["Paola Rinaldi", "Contabilita' fornitori", "Fattura passiva"],
    "raw_content": (
        f"Ogni fattura passiva arriva con il {SENTINEL}. Paola Rinaldi la registra "
        "solo dopo il visto del responsabile acquisti, che pero' spesso e' in ferie: "
        "in quel caso la fattura resta ferma anche due settimane."
    ),
}


def _save_interview(project_id: str, process_id: str) -> None:
    from backend.toolsets.process_memory import manage_process_evidence

    manage_process_evidence.invoke(
        {
            "operation": "save_interview",
            "project_id": project_id,
            "process_id": process_id,
            "title": INTERVIEW["title"],
            "raw_content": INTERVIEW["raw_content"],
            "summary": INTERVIEW["title"],
            "participants": INTERVIEW["participants"],
            "entities": INTERVIEW["entities"],
        }
    )


def _drain(landed, *, tries: int = 40, delay: float = 0.5) -> bool:
    from backend.workers.graph_worker import drain_once as drain_graph
    from backend.workers.ingest_worker import drain_once as drain_ingest

    for _ in range(tries):
        drain_ingest(limit=50)
        drain_graph(limit=500)
        if landed():
            return True
        time.sleep(delay)
    return False


def _count(sql: str, **params) -> int:
    with MIGRATOR.begin() as conn:
        conn.execute(text("SELECT set_config('app.current_consultant_id', :c, true)"),
                     {"c": settings.default_consultant_id})
        conn.execute(text("SELECT set_config('app.current_client_id', :c, true)"),
                     {"c": params.pop("client", "")})
        return int(conn.execute(text(sql), params).scalar_one())


def _neo4j_nodes(**props) -> int:
    key, value = next(iter(props.items()))
    with neo4j_store.get_driver().session() as neo:
        return neo.run(f"MATCH (n {{{key}: $v}}) RETURN count(n) AS c", v=value).single()["c"]


@pytest.fixture()
def workspace():
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
    suffix = uuid.uuid4().hex[:8]
    client = wd.create_client(name=f"Rinaldi Srl {suffix}")
    project = wd.create_project(client_id=client["id"], name=f"Ciclo passivo {suffix}")
    other = wd.create_project(client_id=client["id"], name=f"Tesoreria {suffix}")
    process_name = f"Registrazione fatture passive {suffix}"
    try:
        yield {"client": client, "project": project, "other": other, "process_name": process_name}
    finally:
        canonical_client = canonical_scope.resolve_client_id(project["id"])
        with episodic_store.episodic_connection() as session:
            session.execute(text("DELETE FROM episodes WHERE project = ANY(:p)"),
                            {"p": [project["id"], other["id"]]})
        reset_current_tenant_id(token)
        if canonical_client:
            with MIGRATOR.begin() as conn:
                conn.execute(text("DELETE FROM client WHERE id = :i"), {"i": canonical_client})
            neo4j_store.purge_client(canonical_client)


def test_deleted_process_evidence_does_not_come_back(workspace):
    project_id = workspace["project"]["id"]
    first = wd.create_process(project_id=project_id, name=workspace["process_name"])
    old = canonical_scope.resolve(project_id, first["id"])
    _save_interview(project_id, first["id"])
    assert _drain(lambda: _count(
        "SELECT count(*) FROM kg_source WHERE process_id = CAST(:p AS uuid)",
        p=old.process_id, client=old.client_id,
    ) > 0 and _neo4j_nodes(process_id=old.process_id) > 0)
    assert episodic_store.list_episode_memory(project=project_id, process_id=first["id"])

    wd.delete_process(first["id"])
    assert _drain(lambda: _neo4j_nodes(process_id=old.process_id) == 0)

    # nel canonical non resta niente del processo
    for table in ("kg_source", "kg_claim", "kg_entity", "kg_relation", "kg_ingest_queue"):
        assert _count(
            f"SELECT count(*) FROM {table} WHERE process_id = CAST(:p AS uuid)",
            p=old.process_id, client=old.client_id,
        ) == 0, table
    assert _count(
        "SELECT count(*) FROM process WHERE id = CAST(:p AS uuid)", p=old.process_id
    ) == 0
    # e nessuna evidenza del processo e' scivolata a livello di progetto (FK SET NULL)
    assert _count(
        "SELECT count(*) FROM kg_chunk WHERE project_id = CAST(:pj AS uuid) "
        "AND content LIKE :s", pj=old.project_id, s=f"%{SENTINEL}%", client=old.client_id,
    ) == 0

    # ricreato con lo stesso nome: lo slug si riusa - e' il caso del bug
    second = wd.create_process(project_id=project_id, name=workspace["process_name"])
    assert second["id"] == first["id"]
    new = canonical_scope.resolve(project_id, second["id"])
    assert new.process_id != old.process_id

    assert episodic_store.list_episode_memory(
        project=project_id, process_id=second["id"], status="any"
    ) == []
    out = gateway.graph_retrieve(
        consultant_id=new.consultant_id, client_id=new.client_id,
        query=f"fattura {SENTINEL} Paola Rinaldi", entity_names=["Paola Rinaldi"],
        scope_project_id=new.project_id, scope_process_id=new.process_id,
    )
    assert out["matches"] == [], out
    assert not any(SENTINEL in c["content"] for c in out["chunks"]), out["chunks"]


def test_deleted_project_evidence_is_gone(workspace):
    project_id = workspace["project"]["id"]
    process = wd.create_process(project_id=project_id, name=workspace["process_name"])
    scope_ids = canonical_scope.resolve(project_id, process["id"])
    _save_interview(project_id, process["id"])
    assert _drain(lambda: _neo4j_nodes(project_id=scope_ids.project_id) > 0)

    wd.delete_project(project_id)
    assert _drain(lambda: _neo4j_nodes(project_id=scope_ids.project_id) == 0)
    assert _count(
        "SELECT count(*) FROM kg_source WHERE project_id = CAST(:pj AS uuid)",
        pj=scope_ids.project_id, client=scope_ids.client_id,
    ) == 0
    assert episodic_store.list_episode_memory(project=project_id, status="any") == []


def test_a_stale_slug_mapping_is_not_inherited_by_another_project(workspace):
    """Difesa in profondita': se una riga canonical porta lo slug ma appartiene a
    un altro progetto (cancellazione di prima di questo fix, o un database
    workspace diverso sullo stesso canonical), `resolve` non la riusa."""
    first_project = workspace["project"]["id"]
    other_project = workspace["other"]["id"]
    process = wd.create_process(project_id=first_project, name=workspace["process_name"])
    old = canonical_scope.resolve(first_project, process["id"])
    # cancellazione "alla vecchia": solo il workspace, il canonical resta
    with wd.workspace_connection() as session:
        session.delete(session.get(wd.WorkspaceProcess, process["id"]))

    again = wd.create_process(project_id=other_project, name=workspace["process_name"])
    assert again["id"] == process["id"]
    new = canonical_scope.resolve(other_project, again["id"])

    assert new.process_id != old.process_id
    assert new.project_id != old.project_id


def test_deleting_a_process_leaves_alone_a_slug_mapped_to_another_project(workspace):
    """Cancellare e' irreversibile: se lo slug porta ancora al processo canonical
    di un altro progetto, quell'evidenza non e' di questo processo e resta."""
    first_project = workspace["project"]["id"]
    other_project = workspace["other"]["id"]
    process = wd.create_process(project_id=first_project, name=workspace["process_name"])
    old = canonical_scope.resolve(first_project, process["id"])
    # cancellazione "alla vecchia": solo il workspace, il canonical resta
    with wd.workspace_connection() as session:
        session.delete(session.get(wd.WorkspaceProcess, process["id"]))

    # stesso slug in un altro progetto, cancellato prima che `resolve` lo stacchi
    again = wd.create_process(project_id=other_project, name=workspace["process_name"])
    assert again["id"] == process["id"]
    wd.delete_process(again["id"])

    assert _count(
        "SELECT count(*) FROM process WHERE id = CAST(:p AS uuid)", p=old.process_id
    ) == 1
