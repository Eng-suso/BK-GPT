"""GR-02 / GR-03 — il budget dell'espansione k-hop (docs/graph-rag-remediation.md).

Tre proprieta' che `graph_retrieve` deve avere e che prima non aveva:

- GR-03: in una lettura scoped il `limit` si spende solo su triple leggibili.
  Prima Neo4j espandeva client-wide e l'idratazione scartava dopo: con 30 vicini
  in un altro processo e 10 nel proprio, `limit=10` poteva tornare 0 triple.
- GR-02 (budget per seed): un seed con molti vicini non affama gli altri. Con
  due seed nella query, entrambi devono arrivare nel contesto.
- GR-02 (degree cap): l'espansione non attraversa un hub. Un nodo con centinaia
  di archi come nodo *intermedio* moltiplica i path; come estremo va bene.

Servono le DSN canonical + NEO4J_PASSWORD (`cd ops && docker compose up -d`).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings

_NEEDED = (
    settings.canonical_migrator_url,
    settings.canonical_database_url,
    settings.canonical_worker_url,
    settings.neo4j_password,
)
if not all(_NEEDED):
    pytest.skip(
        "servono CANONICAL_MIGRATOR_URL / CANONICAL_DATABASE_URL / "
        "CANONICAL_WORKER_URL / NEO4J_PASSWORD",
        allow_module_level=True,
    )

from backend.memory import gateway  # noqa: E402
from backend.memory.knowledge_graph import canonical, neo4j_store  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)


def _ctx(conn, consultant_id, client_id=None):
    conn.execute(
        text("SELECT set_config('app.current_consultant_id', :v, true)"),
        {"v": str(consultant_id)},
    )
    conn.execute(
        text("SELECT set_config('app.current_client_id', :v, true)"),
        {"v": str(client_id) if client_id else ""},
    )


@pytest.fixture()
def world():
    consultant, client, project = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    process_a, process_b = uuid.uuid4(), uuid.uuid4()
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("INSERT INTO consultant (id, email, display_name) VALUES (:i,:e,'budget')"),
            {"i": consultant, "e": f"{consultant}@t.local"},
        )
        _ctx(conn, consultant)
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i,:c,'Acme')"),
            {"i": client, "c": consultant},
        )
        _ctx(conn, consultant, client)
        conn.execute(
            text(
                "INSERT INTO project (id, client_id, consultant_id, name) "
                "VALUES (:i,:cl,:c,'P')"
            ),
            {"i": project, "cl": client, "c": consultant},
        )
        for pid, name in ((process_a, "Acquisti"), (process_b, "Manutenzione")):
            conn.execute(
                text(
                    "INSERT INTO process (id, project_id, client_id, consultant_id, name) "
                    "VALUES (:i,:p,:cl,:c,:n)"
                ),
                {"i": pid, "p": project, "cl": client, "c": consultant, "n": name},
            )
    yield {
        "consultant": str(consultant),
        "client": str(client),
        "project": str(project),
        "a": str(process_a),
        "b": str(process_b),
    }
    with MIGRATOR.begin() as conn:
        conn.execute(text("DELETE FROM consultant WHERE id = :i"), {"i": consultant})
    neo4j_store.purge_client(str(client))


def _entity(w, name: str, process: str) -> str:
    return canonical.write_entity(
        w["consultant"], w["client"], "role", name,
        project_id=w["project"], process_id=process,
    )


def _relate(w, source: str, target: str, process: str) -> None:
    canonical.write_relation(
        w["consultant"], w["client"], source, "works_with", target,
        project_id=w["project"], process_id=process,
    )


def _edges_projected(client: str) -> int:
    with neo4j_store.get_driver().session() as neo:
        return neo.run(
            "MATCH ()-[r:WORKS_WITH {client_id: $cid}]->() RETURN count(r) AS c",
            cid=client,
        ).single()["c"]


def _project(w, wait_projected, expected_edges: int) -> None:
    assert wait_projected(lambda: _edges_projected(w["client"]) >= expected_edges)


def _retrieve(w, names: list[str], **kwargs):
    return gateway.graph_retrieve(
        consultant_id=w["consultant"],
        client_id=w["client"],
        entity_names=names,
        scope_project_id=w["project"],
        scope_process_id=w["a"],
        **kwargs,
    )


def test_scoped_limit_is_spent_only_on_readable_triples(world, wait_projected):
    """GR-03: 30 vicini nel processo B scritti per primi, 10 nel processo A.
    Una lettura scoped su A con `limit=10` deve tornarne 10, tutti di A."""
    w = world
    seed = _entity(w, "Fornitore principale", w["a"])
    for i in range(30):
        _relate(w, seed, _entity(w, f"Tecnico manutenzione {i}", w["b"]), w["b"])
    in_scope = {f"Buyer acquisti {i}" for i in range(10)}
    for name in sorted(in_scope):
        _relate(w, seed, _entity(w, name, w["a"]), w["a"])
    _project(w, wait_projected, 40)

    out = _retrieve(w, ["Fornitore principale"], max_hops=1, limit=10)

    assert out["status"] == "ok", out
    assert out["count"] == 10, out
    targets = {m["target"] for m in out["matches"]}
    assert targets == in_scope
    assert out["truncated"] is False


def test_every_seed_gets_budget(world, wait_projected):
    """GR-02: il seed con 50 vicini non affama quello con 3."""
    w = world
    big = _entity(w, "Ufficio acquisti", w["a"])
    small = _entity(w, "Controllo di gestione", w["a"])
    for i in range(50):
        _relate(w, big, _entity(w, f"Richiedente {i}", w["a"]), w["a"])
    small_targets = {f"Analista {i}" for i in range(3)}
    for name in sorted(small_targets):
        _relate(w, small, _entity(w, name, w["a"]), w["a"])
    _project(w, wait_projected, 53)

    out = _retrieve(w, ["Ufficio acquisti", "Controllo di gestione"], max_hops=1, limit=10)

    assert out["count"] == 10, out
    got = {m["target"] for m in out["matches"] if m["source"] == "Controllo di gestione"}
    assert got == small_targets
    assert out["truncated"] is True


def test_expansion_does_not_traverse_hubs(world, wait_projected, monkeypatch):
    """GR-02: un hub come nodo intermedio non si attraversa; come estremo si'."""
    monkeypatch.setattr(settings, "graph_expand_degree_cap", 20)
    w = world
    seed = _entity(w, "Responsabile qualita'", w["a"])
    hub = _entity(w, "Sistema ERP", w["a"])
    _relate(w, seed, hub, w["a"])
    for i in range(40):
        _relate(w, _entity(w, f"Utente ERP {i}", w["a"]), hub, w["a"])
    _project(w, wait_projected, 41)

    out = _retrieve(w, ["Responsabile qualita'"], max_hops=2, limit=25)

    pairs = {(m["source"], m["target"]) for m in out["matches"]}
    assert ("Responsabile qualita'", "Sistema ERP") in pairs
    assert not any(src.startswith("Utente ERP") for src, _ in pairs), pairs
