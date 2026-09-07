"""PROJECT-02..05: dove finisce la Project Chat e dove comincia a inventare.

Quattro difetti osservati nella stessa sessione di test, tutti sul confine fra
"il progetto" e "il processo":

- PROJECT-02, un progetto senza processi si faceva raccontare le lacune di un
  processo inesistente;
- PROJECT-03, "crea questo processo nel progetto" finiva in un handoff al
  Process Macro, che pero' un `process_id` lo pretende: vicolo cieco;
- PROJECT-04, "aggiungi il processo" un turno dopo averlo nominato tornava
  come "quale processo?";
- PROJECT-05, davanti alla capability mancante l'agente inventava un pulsante.

I test qui sotto coprono le parti verificabili senza modello: il gate di
routing, il prompt di scope, il digest che il router legge e il tool di
registrazione.
"""

from __future__ import annotations

import json
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from backend.agents.primary_scope import build_scope_system_prompt
from backend.graphs.common import recent_conversation_digest
from backend.graphs.project.graph import parse_project_router_json
from backend.graphs.project.tools import create_project_process, project_tools
from backend.graphs.routing_contracts import resolved_project_process
from backend.settings import settings


PROCESSES = [
    {"id": "proc-1", "name": "Gestione acquisto materiali indiretti e servizi"},
]


# --- PROJECT-02: zero processi, zero inferenze -----------------------------

def test_an_empty_portfolio_says_readiness_is_not_evaluable():
    prompt = build_scope_system_prompt(
        {"scope_type": "project", "project_id": "p-1", "project_processes": []}
    )

    assert "process_count: 0" in prompt
    assert "readiness di processo non e' valutabile" in prompt
    assert "create_project_process" in prompt


def test_a_project_with_processes_gets_no_empty_portfolio_warning():
    prompt = build_scope_system_prompt(
        {"scope_type": "project", "project_id": "p-1", "project_processes": PROCESSES}
    )

    assert "process_count: 0" not in prompt


def test_process_coordination_is_refused_without_processes():
    """Coordinare zero processi non e' prudenza, e' una domanda senza oggetto."""
    result = parse_project_router_json(
        json.dumps(
            {
                "route": "process_coordination",
                "confidence": 0.9,
                "suggested_capability": "project.process_coordination",
                "reason": "Readiness dei processi in scope.",
            }
        ),
        user_request="Elenca i processi in scope e la loro readiness.",
        state={"project_processes": []},
    )

    assert result["project_route"] == "clarification"
    assert result["orchestration_status"] == "missing_prerequisite"
    assert "Missing prerequisite: existing_project_process" in result["blocking_conditions"]


# --- PROJECT-03: il progetto possiede i propri processi --------------------

def test_project_scope_owns_process_creation():
    assert "create_project_process" in {item.name for item in project_tools}


def test_delegation_is_refused_for_a_process_that_does_not_exist():
    """Il nome c'e', il record no: delegare qui manda il turno in un vicolo cieco."""
    result = parse_project_router_json(
        json.dumps(
            {
                "route": "delegate_process",
                "confidence": 0.9,
                "entity_hints": {"process": "Gestione acquisto materiali indiretti e servizi"},
                "suggested_capability": "project.process_delegation",
                "reason": "Il consulente ha chiesto di aggiungere il processo.",
            }
        ),
        user_request="aggiungi il processo",
        state={"project_processes": []},
    )

    assert result["project_route"] == "clarification"
    assert result["orchestration_status"] == "missing_prerequisite"
    assert "Missing prerequisite: existing_project_process" in result["blocking_conditions"]


def test_a_hint_only_counts_when_the_process_is_registered():
    registered = {"entity_hints": {"process": "Acquisti"}, "project_processes": PROCESSES}
    assert resolved_project_process(registered) is None

    exact = {
        "entity_hints": {"process": " gestione ACQUISTO materiali indiretti e servizi "},
        "project_processes": PROCESSES,
    }
    assert resolved_project_process(exact) == PROCESSES[0]

    by_id = {"entity_hints": {"process": "proc-1"}, "project_processes": PROCESSES}
    assert resolved_project_process(by_id) == PROCESSES[0]

    # Nessun hint: un solo processo nel progetto e' gia' inequivocabile.
    assert resolved_project_process({"project_processes": PROCESSES}) == PROCESSES[0]
    assert resolved_project_process({"project_processes": [*PROCESSES, {"id": "p2", "name": "Vendite"}]}) is None


def test_the_creation_tool_promises_not_to_start_discovery():
    description = create_project_process.description

    assert "does not start discovery" in description
    assert "Idempotent by name" in description


# --- PROJECT-04: il riferimento appena nominato ----------------------------

def test_the_router_digest_carries_the_entity_named_last_turn():
    state = {
        "messages": [
            HumanMessage(content="Il processo si chiama Gestione acquisto materiali indiretti e servizi."),
            AIMessage(content="Perimetro: dalla richiesta d'acquisto al pagamento fornitore. As-Is."),
            HumanMessage(content="aggiungi il processo"),
        ]
    }

    digest = recent_conversation_digest(state)

    assert "Gestione acquisto materiali indiretti e servizi" in digest
    assert digest.index("utente: Il processo") < digest.index("DeliR: Perimetro")
    assert digest.endswith("utente: aggiungi il processo")


def test_the_digest_leaves_out_tool_traffic_and_empty_turns():
    state = {
        "messages": [
            SystemMessage(content="contratto di scope"),
            HumanMessage(content="ciao"),
            AIMessage(content="", tool_calls=[]),
            ToolMessage(content="{\"status\": \"ok\"}", tool_call_id="call-1"),
            AIMessage(content="Fatto."),
        ]
    }

    digest = recent_conversation_digest(state)

    assert digest == "utente: ciao\nDeliR: Fatto."


def test_the_digest_keeps_the_newest_turns_within_budget():
    state = {"messages": [HumanMessage(content=f"messaggio {index}") for index in range(40)]}

    digest = recent_conversation_digest(state, max_turns=3)

    assert digest == "utente: messaggio 37\nutente: messaggio 38\nutente: messaggio 39"


def test_the_scope_prompt_tells_the_agent_to_resolve_references():
    prompt = build_scope_system_prompt({"scope_type": "project", "project_id": "p-1"})

    assert "va risolto leggendo la" in prompt


# --- PROJECT-05: nessun pulsante inventato ---------------------------------

def test_the_scope_prompt_forbids_inventing_the_interface():
    prompt = build_scope_system_prompt({"scope_type": "consultant"})

    assert "Non inventare percorsi nell'interfaccia" in prompt
    assert "Quando una capability manca, dillo apertamente" in prompt


# --- comportamento reale: serve il database operativo ----------------------

pytestmark_db = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)


@pytest.fixture()
def tenant():
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
    try:
        yield
    finally:
        reset_current_tenant_id(token)


def _tool_payload(result: str) -> dict:
    """Il risultato enterprise e' `action\\n{json}`."""
    return json.loads(result.split("\n", 1)[1])


PROCESS_NAME = "Gestione acquisto materiali indiretti e servizi"
PERIMETER = "Dalla richiesta d'acquisto interna al pagamento della fattura fornitore."


@pytestmark_db
def test_the_project_registers_its_own_process(tenant):
    from backend import workspace_database as wd

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    project = wd.create_project(client_id=client["id"], name=f"Acquisti {uuid.uuid4().hex[:6]}")

    result = _tool_payload(
        create_project_process.invoke(
            {"project_id": project["id"], "name": PROCESS_NAME, "scope_note": PERIMETER}
        )
    )

    assert result["status"] == "created"
    process_id = result["payload"]["process_id"]
    assert wd.get_process(process_id)["name"] == PROCESS_NAME
    # Il record nasce con il suo modello BPMN vuoto: nessun XML generato.
    assert wd.get_bpmn_model(result["payload"]["bpmn_model_id"])["xml"] is None
    # Il perimetro dichiarato non resta nella sola chat.
    sources = wd.list_project_sources(project["id"])
    assert any(source["meta"] == PERIMETER and source["process_id"] == process_id for source in sources)


@pytestmark_db
def test_registering_the_same_process_twice_does_not_duplicate_it(tenant):
    from backend import workspace_database as wd

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    project = wd.create_project(client_id=client["id"], name=f"Acquisti {uuid.uuid4().hex[:6]}")

    first = _tool_payload(
        create_project_process.invoke({"project_id": project["id"], "name": PROCESS_NAME})
    )
    second = _tool_payload(
        create_project_process.invoke({"project_id": project["id"], "name": f"  {PROCESS_NAME.upper()} "})
    )

    assert first["status"] == "created"
    assert second["status"] == "exists"
    assert second["entity_id"] == first["entity_id"]
    assert len(wd.list_project_processes(project["id"])) == 1


@pytestmark_db
def test_a_process_registered_without_a_perimeter_says_so(tenant):
    from backend import workspace_database as wd

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    project = wd.create_project(client_id=client["id"], name=f"Acquisti {uuid.uuid4().hex[:6]}")

    result = _tool_payload(
        create_project_process.invoke({"project_id": project["id"], "name": PROCESS_NAME})
    )

    assert any("perimeter" in warning for warning in result["warnings"])


@pytestmark_db
def test_the_registered_process_unblocks_delegation(tenant):
    """Il fix e' completo solo se dopo la creazione l'handoff diventa possibile."""
    from backend import workspace_database as wd
    from backend.graphs.project.nodes import load_project_context

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    project = wd.create_project(client_id=client["id"], name=f"Acquisti {uuid.uuid4().hex[:6]}")
    create_project_process.invoke({"project_id": project["id"], "name": PROCESS_NAME})

    state = load_project_context({"project_id": project["id"]})
    result = parse_project_router_json(
        json.dumps(
            {
                "route": "delegate_process",
                "confidence": 0.9,
                "entity_hints": {"process": PROCESS_NAME},
                "suggested_capability": "project.process_delegation",
                "reason": "Discovery AS-IS sul processo registrato.",
            }
        ),
        user_request="partiamo con la discovery di quel processo",
        state=state,
    )

    assert result["project_route"] == "delegate_process"
    assert result["delegation_target"] == "process_macro"
