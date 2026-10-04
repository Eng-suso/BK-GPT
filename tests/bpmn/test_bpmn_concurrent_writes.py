"""Due mani sullo stesso disegno: nessuna cancella il lavoro dell'altra in silenzio.

Il consulente salva il canvas a mano mentre l'agente, nello stesso processo,
sta lavorando su una copia letta all'inizio del turno. Senza un controllo
l'ultima scrittura vince e il salvataggio del consulente sparisce.

Due garanzie:

1. **salvataggio manuale** - chi salva dice da quale versione e' partito
   (`expected_version_id`); se nel frattempo ne e' nata un'altra, il
   salvataggio e' rifiutato invece di sovrascriverla;
2. **turno dell'agente** - dentro un turno l'agente puo' salvare quante volte
   vuole, ma se qualcun altro ha salvato dopo l'inizio del turno la sua
   scrittura e' rifiutata, e il messaggio gli dice di rileggere il canvas.
"""

from __future__ import annotations

import threading
import uuid

import pytest

from backend.settings import settings

pytestmark = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)

_XML = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" id="d">
  <process id="p"><task id="{task}" name="{task}"/></process>
</definitions>"""


@pytest.fixture()
def model_id():
    from backend import workspace_database as wd
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-bpmn-cas-{uuid.uuid4().hex[:8]}")
    try:
        client = wd.create_client(name=f"Cliente {uuid.uuid4().hex[:6]}")
        project = wd.create_project(client_id=client["id"], name="Acquisti")
        process = wd.create_process(project_id=project["id"], name="Ordine fornitore")
        yield process["bpmn_model_id"]
    finally:
        reset_current_tenant_id(token)


def _save_elsewhere(model_id: str, task: str) -> None:
    """Un salvataggio fuori dal turno: un thread nuovo non eredita il contesto."""
    from backend import workspace_database as wd
    from backend.security import get_current_tenant_id, reset_current_tenant_id, set_current_tenant_id

    tenant = get_current_tenant_id()
    errors: list[BaseException] = []

    def run() -> None:
        token = set_current_tenant_id(tenant)
        try:
            wd.update_bpmn_model(model_id, _XML.format(task=task), source="manual_save")
        except BaseException as exc:  # noqa: BLE001 - riportato al test
            errors.append(exc)
        finally:
            reset_current_tenant_id(token)

    worker = threading.Thread(target=run)
    worker.start()
    worker.join()
    if errors:
        raise errors[0]


def test_the_model_reports_the_version_it_is_at(model_id):
    from backend import workspace_database as wd

    before = wd.get_bpmn_model(model_id)["version_id"]
    wd.update_bpmn_model(model_id, _XML.format(task="primo"))
    after = wd.get_bpmn_model(model_id)["version_id"]

    assert after is not None
    assert after != before


def test_a_save_from_a_stale_version_is_refused(model_id):
    from backend import workspace_database as wd

    wd.update_bpmn_model(model_id, _XML.format(task="primo"))
    seen = wd.get_bpmn_model(model_id)["version_id"]
    wd.update_bpmn_model(model_id, _XML.format(task="secondo"), expected_version_id=seen)

    with pytest.raises(wd.BpmnVersionConflict):
        wd.update_bpmn_model(model_id, _XML.format(task="terzo"), expected_version_id=seen)

    assert "secondo" in wd.get_bpmn_model(model_id)["xml"]


def test_a_save_from_the_current_version_goes_through(model_id):
    from backend import workspace_database as wd

    wd.update_bpmn_model(model_id, _XML.format(task="primo"))
    seen = wd.get_bpmn_model(model_id)["version_id"]

    saved = wd.update_bpmn_model(model_id, _XML.format(task="secondo"), expected_version_id=seen)

    assert "secondo" in saved["xml"]
    assert saved["version_id"] != seen


def test_an_agent_turn_can_save_more_than_once(model_id):
    from backend import workspace_database as wd
    from backend.agents.run_context import bind_turn_writes

    wd.update_bpmn_model(model_id, _XML.format(task="primo"))
    with bind_turn_writes():
        wd.update_bpmn_model(model_id, _XML.format(task="agente_uno"), source="agent")
        wd.update_bpmn_model(model_id, _XML.format(task="agente_due"), source="agent")

    assert "agente_due" in wd.get_bpmn_model(model_id)["xml"]


def test_an_agent_turn_does_not_overwrite_a_save_made_during_the_turn(model_id):
    from backend import workspace_database as wd
    from backend.agents.run_context import bind_turn_writes

    wd.update_bpmn_model(model_id, _XML.format(task="primo"))
    with bind_turn_writes():
        wd.update_bpmn_model(model_id, _XML.format(task="agente"), source="agent")
        _save_elsewhere(model_id, "consulente")

        with pytest.raises(wd.BpmnVersionConflict, match="rileggi"):
            wd.update_bpmn_model(model_id, _XML.format(task="agente_ancora"), source="agent")

    assert "consulente" in wd.get_bpmn_model(model_id)["xml"]


def test_a_save_made_before_the_turn_does_not_block_the_agent(model_id):
    from backend import workspace_database as wd
    from backend.agents.run_context import bind_turn_writes

    _save_elsewhere(model_id, "consulente")
    with bind_turn_writes():
        wd.update_bpmn_model(model_id, _XML.format(task="agente"), source="agent")

    assert "agente" in wd.get_bpmn_model(model_id)["xml"]



def test_an_agent_working_on_a_stale_canvas_does_not_overwrite_the_newer_save(model_id):
    """Rilievo CodeRabbit sulla PR #54: una scheda rimasta aperta su una versione
    vecchia manda quell'XML all'agente. Il salvataggio del collega e' arrivato
    prima del turno, quindi l'istante da solo non lo vede: serve la versione da
    cui viene l'XML."""
    from backend import workspace_database as wd
    from backend.agents.run_context import bind_turn_writes

    wd.update_bpmn_model(model_id, _XML.format(task="primo"))
    stale = wd.get_bpmn_model(model_id)["version_id"]
    _save_elsewhere(model_id, "collega")

    with bind_turn_writes({model_id: stale}):
        with pytest.raises(wd.BpmnVersionConflict):
            wd.update_bpmn_model(model_id, _XML.format(task="agente"), source="agent")

    assert "collega" in wd.get_bpmn_model(model_id)["xml"]


def test_an_agent_working_on_the_current_canvas_moves_its_base_as_it_writes(model_id):
    from backend import workspace_database as wd
    from backend.agents.run_context import bind_turn_writes

    wd.update_bpmn_model(model_id, _XML.format(task="primo"))
    current = wd.get_bpmn_model(model_id)["version_id"]

    with bind_turn_writes({model_id: current}):
        wd.update_bpmn_model(model_id, _XML.format(task="agente_uno"), source="agent")
        wd.update_bpmn_model(model_id, _XML.format(task="agente_due"), source="agent")

    assert "agente_due" in wd.get_bpmn_model(model_id)["xml"]


def test_a_restore_inside_a_turn_does_not_overwrite_a_save_made_meanwhile(model_id):
    from backend import workspace_database as wd
    from backend.agents.run_context import bind_turn_writes

    wd.update_bpmn_model(model_id, _XML.format(task="primo"))
    first = wd.get_bpmn_model(model_id)["version_id"]
    with bind_turn_writes():
        _save_elsewhere(model_id, "consulente")
        with pytest.raises(wd.BpmnVersionConflict):
            wd.restore_bpmn_version(model_id, first)

    assert "consulente" in wd.get_bpmn_model(model_id)["xml"]


def test_the_save_route_answers_409_and_writes_nothing_on_a_stale_version(model_id):
    from fastapi.testclient import TestClient

    from backend import workspace_database as wd
    from backend.app import app
    from backend.security import get_current_tenant_id

    wd.update_bpmn_model(model_id, _XML.format(task="primo"))
    seen = wd.get_bpmn_model(model_id)["version_id"]
    wd.update_bpmn_model(model_id, _XML.format(task="secondo"))
    versions_before = len(wd.list_bpmn_versions(model_id))

    # Senza `with`: il lifespan avvierebbe i worker di coda.
    response = TestClient(app).put(
        f"/v1/workspace/bpmn-models/{model_id}",
        json={"xml": _XML.format(task="terzo"), "expected_version_id": seen},
        headers={"X-DeliR-Tenant-Id": get_current_tenant_id()},
    )

    assert response.status_code == 409, response.text
    assert len(wd.list_bpmn_versions(model_id)) == versions_before
    assert "secondo" in wd.get_bpmn_model(model_id)["xml"]

# --- l'esito arriva al modello ------------------------------------------------


def _run_tool_node(tool_fn):
    """Il nodo dei tool come lo monta `build_tool_chat_subgraph`, in un grafo minimo."""
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode

    from backend.agents.run_context import report_bpmn_version_conflict

    wrapped = tool(tool_fn)
    graph = StateGraph(MessagesState)
    graph.add_node("tools", ToolNode([wrapped], handle_tool_errors=report_bpmn_version_conflict))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    call = {"name": wrapped.name, "args": {}, "id": "call-1", "type": "tool_call"}
    state = graph.compile().invoke({"messages": [AIMessage(content="", tool_calls=[call])]})
    return {"messages": state["messages"][1:]}


def test_a_conflict_inside_a_tool_reaches_the_model_as_its_result():
    from backend.agents.run_context import BpmnVersionConflict

    def salva_canvas() -> str:
        """Salva il canvas."""
        raise BpmnVersionConflict("rileggi il canvas salvato")

    result = _run_tool_node(salva_canvas)

    message = result["messages"][0]
    assert "rileggi il canvas salvato" in message.content
    assert message.content.startswith("Modifica non salvata")


def test_any_other_tool_error_still_stops_the_turn():
    def salva_canvas() -> str:
        """Salva il canvas."""
        raise RuntimeError("guasto vero")

    with pytest.raises(RuntimeError, match="guasto vero"):
        _run_tool_node(salva_canvas)
