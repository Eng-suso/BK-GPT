"""I confini che tengono l'evidenza dentro il proprio processo.

Test mirati sulla root cause di PROCESS-V2-08: il percorso di lettura era piu'
largo di quello di scrittura. Qui si verificano i singoli pezzi del confine -
il rifiuto di una lettura senza scope, il filtro strutturale sugli episodi, lo
scope guard sul processo, la scoperta di appartenenza di una memoria Mem0 -
mentre `test_process_evidence_isolation.py` verifica l'invariante end-to-end.
"""

from __future__ import annotations

import json
import uuid

import pytest

from backend.settings import settings


# --- il gateway non legge senza un confine dichiarato ----------------------

def test_graph_retrieval_without_a_scope_is_refused(monkeypatch):
    """Una lettura senza scope non degrada a client-wide: viene rifiutata."""
    from backend.memory import gateway

    monkeypatch.setattr(gateway, "graph_available", lambda: True)

    result = gateway.graph_retrieve(
        consultant_id=str(uuid.uuid4()),
        client_id=str(uuid.uuid4()),
        query="cosa hanno detto gli intervistati?",
    )

    assert result["status"] == "blocked"
    assert result["matches"] == []
    assert result["chunks"] == []
    assert "scope" in result["reason"]


def test_a_client_wide_read_stays_possible_when_it_is_declared(monkeypatch):
    """Cutover, sweep e chat consulente leggono ancora: lo dichiarano."""
    from backend.memory import gateway

    monkeypatch.setattr(gateway, "graph_available", lambda: True)
    monkeypatch.setattr(gateway, "_authorized_source_ids", lambda session, scope: None)
    monkeypatch.setattr(gateway, "canonical_session", _null_session)
    monkeypatch.setattr(gateway, "_resolve_seed_entities", lambda *a, **k: [])
    monkeypatch.setattr(
        gateway, "_text_search", lambda *a, **k: gateway._EMPTY_CHUNK_SEARCH
    )

    result = gateway.graph_retrieve(
        consultant_id=str(uuid.uuid4()),
        client_id=str(uuid.uuid4()),
        query="qualsiasi",
        allow_client_wide=True,
    )

    assert result["status"] != "blocked"


class _NullSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _null_session(*args, **kwargs):
    return _NullSession()


# --- quali righe stanno dentro il confine ----------------------------------

def _scope(**kwargs):
    from backend.memory.gateway import ReadScope

    return ReadScope(client_id="cl", **kwargs)


def test_the_scope_predicate_keeps_the_process_and_the_project_level_rows():
    from backend.memory.gateway import _scope_sql

    predicate, params = _scope_sql(_scope(project_id="pj", process_id="pr"))

    assert "process_id = CAST(:sc_pr AS uuid)" in predicate
    # L'evidenza di progetto, che non appartiene ad alcun processo, resta
    # leggibile: e' contesto dell'incarico, non di un altro processo.
    assert "process_id IS NULL" in predicate
    assert params == {"sc_pr": "pr", "sc_pj": "pj"}


def test_without_a_process_the_boundary_is_the_project():
    from backend.memory.gateway import _scope_sql

    predicate, params = _scope_sql(_scope(project_id="pj"))

    assert predicate.strip() == "AND project_id = CAST(:sc_pj AS uuid)"
    assert params == {"sc_pj": "pj"}


def test_a_declared_client_wide_read_has_no_predicate():
    from backend.memory.gateway import _scope_sql

    assert _scope_sql(_scope(project_id="pj", client_wide=True)) == ("", {})


def _node(**kwargs):
    from backend.memory.gateway import _Node

    defaults = {"label": "x", "project_id": None, "process_id": None, "source_ids": ()}
    return _Node(**{**defaults, "label": "x", **kwargs})


def test_a_node_of_another_process_is_out_of_scope():
    assert not _node(project_id="pj", process_id="altro").in_scope(
        _scope(project_id="pj", process_id="pr"), set()
    )


def test_a_shared_node_is_readable_through_an_authorized_source():
    """Un'entita' riusata da piu' processi entra solo per la propria provenance."""
    shared = _node(project_id="altro-pj", process_id="altro-pr", source_ids=("s1", "s2"))

    assert shared.in_scope(_scope(project_id="pj", process_id="pr"), {"s2"})
    assert not shared.in_scope(_scope(project_id="pj", process_id="pr"), {"s9"})


# --- Mem0: l'appartenenza dichiarata vince --------------------------------

def test_a_memory_of_another_project_is_out_of_scope():
    from backend.memory.gateway import _memory_out_of_scope

    assert _memory_out_of_scope({"client_id": "cl", "project_id": "altro"}, "cl", "pj")


def test_a_consultant_memory_stays_visible_everywhere():
    """Preferenze e metodo sono del consulente, non dell'incarico."""
    from backend.memory.gateway import _memory_out_of_scope

    assert not _memory_out_of_scope({}, "cl", "pj")
    assert not _memory_out_of_scope({"client_id": "cl"}, "cl", "pj")


# --- lo scope guard copre anche il processo -------------------------------

def test_a_tool_cannot_reach_another_process_of_the_same_project():
    from backend.agents.scope_guard import ScopeViolation, assert_process_in_scope, bind_active_scope
    from backend.schemas.chat import ProcessChatScope

    scope = ProcessChatScope(type="process", project_id="pj", process_id="proc-1")
    with bind_active_scope(scope):
        assert_process_in_scope("proc-1")  # quello autorizzato: passa
        with pytest.raises(ScopeViolation):
            assert_process_in_scope("proc-2")


def test_outside_a_process_chat_the_process_guard_does_not_fire():
    from backend.agents.scope_guard import assert_process_in_scope, bind_active_scope
    from backend.schemas.chat import ProjectChatScope

    with bind_active_scope(ProjectChatScope(type="project", project_id="pj")):
        assert_process_in_scope("proc-1")
    assert_process_in_scope("proc-1")  # fuori da un run: no-op


# --- l'indice episodico: appartenenza, non somiglianza di stringhe ---------

pytestmark_db = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)


@pytest.fixture()
def episodes():
    """Episodi di due processi con id in prefisso l'uno dell'altro."""
    from backend.memory.episodic import episodic_store

    project = f"proj-{uuid.uuid4().hex[:8]}"
    saved = []
    for process_id, titles in (
        (f"{project}-p1", ["Intervista uno", "Intervista due", "Intervista tre"]),
        (f"{project}-p10", ["Intervista del processo vicino"]),
    ):
        for title in titles:
            episodic_store.save_episode_memory(
                episode_type="interview",
                title=title,
                raw_content=f"Contenuto di {title}.",
                project=project,
                process_id=process_id,
                tags=[f"project:{project}", f"process:{process_id}", "process_evidence"],
            )
            saved.append(title)
    yield {"project": project, "one": f"{project}-p1", "ten": f"{project}-p10"}
    with episodic_store.episodic_connection() as session:
        from sqlalchemy import text

        session.execute(text("DELETE FROM episodes WHERE project = :p"), {"p": project})


@pytestmark_db
def test_a_process_id_that_is_a_prefix_of_another_does_not_leak(episodes):
    """`proc-1` non deve pescare gli episodi di `proc-10`."""
    from backend.memory.episodic import episodic_store

    found = episodic_store.list_episode_memory(
        project=episodes["project"], process_id=episodes["one"], limit=50
    )

    assert {item["title"] for item in found} == {
        "Intervista uno", "Intervista due", "Intervista tre",
    }


@pytestmark_db
def test_the_text_filter_does_not_silently_drop_the_oldest_evidence(episodes):
    """Il LIMIT non puo' cadere prima del filtro: e' cosi' che sparivano fonti."""
    from backend.memory.episodic import episodic_store

    found = episodic_store.list_episode_memory(
        project=episodes["project"],
        process_id=episodes["one"],
        query="Intervista",
        limit=50,
    )

    assert len(found) == 3


@pytestmark_db
def test_the_stored_episode_declares_its_process(episodes):
    from backend.memory.episodic import episodic_store

    found = episodic_store.list_episode_memory(
        project=episodes["project"], process_id=episodes["ten"], limit=50
    )

    assert [item["process_id"] for item in found] == [episodes["ten"]]
    assert f"process:{episodes['ten']}" in json.loads(found[0]["tags"])
