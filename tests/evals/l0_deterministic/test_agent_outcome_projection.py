"""L'agente legge il grafo di un cliente la cui proiezione non e' affidabile (P1.4).

Neo4j e' una proiezione di Postgres. Quando la riconciliazione l'ha trovata
diversa (`CORRUPT`) o l'ha scritta un projector vecchio (`STALE`), servirla
vorrebbe dire dare all'agente archi che forse non esistono piu'. Il gateway
ripiega su Postgres (`gateway/graph.py`); qui lo si guarda da fuori, con un
turno vero: il modello chiede il contesto del grafo del processo, e si misura
cosa gli torna.

| proiezione | il runtime |
| --- | --- |
| corrupt | non legge Neo4j, serve da Postgres e lo dice all'agente con il motivo |
| stale | come sopra: un grafo di un altro projector non si serve |
| fresh (controllo) | legge Neo4j: senza questo, gli altri due passerebbero anche se il ripiego non ci fosse |

Lo stato della proiezione e' quello vero, scritto in `graph_projection_state`
come lo scrivono la riconciliazione e il worker. Neo4j non c'e': la sua
espansione e' sostituita da un registro che dice se e' stata chiamata.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings
from tests.evals.outcome_harness import call, run_agent_turn

pytestmark = pytest.mark.skipif(
    not (
        settings.workspace_database_url
        and settings.canonical_database_url
        and settings.canonical_migrator_url
        and settings.canonical_worker_url
    ),
    reason="servono WORKSPACE_DATABASE_URL e le DSN canonical (app, migrator, worker)",
)


@pytest.fixture()
def tenant() -> Iterator[None]:
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"outcome-{uuid.uuid4().hex[:10]}")
    try:
        yield
    finally:
        reset_current_tenant_id(token)


@pytest.fixture()
def process(tenant) -> Iterator[dict[str, str]]:
    """Un processo nel workspace e il cliente canonical a cui appartiene."""
    from backend import workspace_database as wd
    from backend.memory import scope as canonical_scope

    client = wd.create_client(name=f"Cliente {uuid.uuid4().hex[:6]}")
    project = wd.create_project(client_id=client["id"], name="Acquisti")
    created = wd.create_process(project_id=project["id"], name="Ordine")
    scope = canonical_scope.resolve(project["id"], created["id"])
    yield {"project_id": project["id"], "process_id": created["id"], "client_id": str(scope.client_id)}

    with create_engine(settings.canonical_migrator_url, future=True).begin() as conn:
        conn.execute(
            text("DELETE FROM graph_projection_state WHERE client_id = CAST(:cl AS uuid)"),
            {"cl": str(scope.client_id)},
        )


def _corrupt(client_id: str) -> None:
    from backend.memory.knowledge_graph import projection_state

    with create_engine(settings.canonical_migrator_url, future=True).begin() as conn:
        projection_state.mark_corrupt(conn, client_id, "missing_edges=3")


def _written_by_an_old_projector(client_id: str) -> None:
    with create_engine(settings.canonical_migrator_url, future=True).begin() as conn:
        conn.execute(
            text(
                "INSERT INTO graph_projection_state (client_id, watermark, projector_version) "
                "VALUES (CAST(:cl AS uuid), 5, 'vecchio')"
            ),
            {"cl": client_id},
        )


def _fresh(client_id: str) -> None:
    """Nessuno stato e coda vuota: la proiezione e' verificata fresca."""


@pytest.fixture()
def neo4j(monkeypatch) -> list[str]:
    """Neo4j finto: registra chi lo legge e non risponde niente."""
    from backend.memory import gateway, projection_health
    from backend.memory.gateway import graph

    reads: list[str] = []

    def _expand(client_id, *_args, **_kwargs):
        reads.append(client_id)
        return [], False

    monkeypatch.setattr(graph, "_expand", _expand)
    # Il tool chiede al pacchetto, il retrieve al suo modulo: Neo4j "c'e'" per
    # entrambi, cosi' si arriva alla domanda sulla proiezione.
    monkeypatch.setattr(gateway, "graph_available", lambda: True)
    monkeypatch.setattr(graph, "graph_available", lambda: True)
    # Il rapporto sulla proiezione si tiene per qualche secondo: qui ogni
    # scenario deve leggere lo stato che ha appena scritto.
    monkeypatch.setattr(projection_health, "_cache", {})
    return reads


def _graph_seen_by_the_model(process: dict[str, str]):
    from backend.toolsets.process_memory import retrieve_process_graph_context

    outcome = run_agent_turn(
        tools=[retrieve_process_graph_context],
        script=[
            call(
                "retrieve_process_graph_context",
                project_id=process["project_id"],
                process_id=process["process_id"],
                query="Chi approva l'ordine e su quali fonti si regge?",
                relation_focus="evidence-lineage",
                reason="Il consulente chiede da dove viene l'approvazione.",
                entities=["Approvazione ordine"],
            )
        ],
        observe=dict,
    )
    assert outcome.error is None
    result = outcome.result_of("retrieve_process_graph_context")
    # `format_workspace_result`: il nome dell'azione, poi il JSON.
    action, _, body = result.content.partition("\n")
    assert action == "retrieve_process_graph_context"
    graph = json.loads(body)["payload"]["knowledge_graph"]
    return outcome, result, graph


@pytest.mark.parametrize(
    ("make", "health"),
    [(_corrupt, "corrupt"), (_written_by_an_old_projector, "stale")],
    ids=["corrupt", "stale"],
)
def test_an_untrusted_projection_is_never_served_to_the_agent(process, neo4j, make, health):
    make(process["client_id"])

    outcome, result, graph = _graph_seen_by_the_model(process)

    assert neo4j == [], "una proiezione non affidabile non si legge"
    assert graph["projection"]["health"] == health
    assert graph["projection"]["served_from"] == "postgres"
    # Il motivo e cosa manca viaggiano con la risposta: l'agente non scambia
    # un ripiego per il grafo completo.
    assert "kg_reproject" in graph["projection"]["reason"]
    assert graph["projection"]["coverage"]
    # ...e arrivano davvero al modello, nel turno dopo la chiamata.
    assert '"served_from": "postgres"' in outcome.model_inputs[1][-1].content
    assert result.content == outcome.model_inputs[1][-1].content


def test_a_fresh_projection_is_read_from_neo4j(process, neo4j):
    _fresh(process["client_id"])

    _, _, graph = _graph_seen_by_the_model(process)

    assert neo4j == [process["client_id"]]
    assert graph["projection"] == {"health": "fresh", "served_from": "neo4j"}
