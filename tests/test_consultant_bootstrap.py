"""La Consulting Chat sa fare il bootstrap del workspace.

Difetto CONSULTANT-V2-03: "crea un progetto per Esaote" veniva delegato al
Project Macro Agent, che pero' governa cio' che succede *dentro* un progetto
esistente. La risposta arrivava un passo troppo presto — non si puo' prendere in
carico un progetto che nessuno ha ancora creato.
"""

import pytest

from backend.graphs.consulting.graph import load_workspace_records
from backend.graphs.consulting.subgraphs.setup.tools import setup_tools
from backend.graphs.routing_contracts import (
    ConsultingRoutingDecision,
    authorize_routing_decision,
    capability_menu,
    has_existing_project,
)


def consulting_decision(**kwargs) -> ConsultingRoutingDecision:
    return ConsultingRoutingDecision(**kwargs)


def authorize(decision: ConsultingRoutingDecision, state: dict) -> dict:
    return authorize_routing_decision(
        owner="consultant",
        decision=decision,
        state=state,
        parse_source="structured",
        parse_error=None,
    )


WORKSPACE_WITH_ESAOTE_CLIENT_ONLY = {
    "workspace_clients": [{"id": "esaote", "name": "Esaote"}],
    "workspace_projects": [],
}

WORKSPACE_WITH_ESAOTE_PROJECT = {
    "workspace_clients": [{"id": "esaote", "name": "Esaote"}],
    "workspace_projects": [
        {
            "id": "esaote-ordini",
            "name": "Ciclo ordini",
            "client_id": "esaote",
            "client": "Esaote",
        }
    ],
}


def test_a_project_that_does_not_exist_cannot_be_handed_to_the_project_agent():
    result = authorize(
        consulting_decision(
            route="delegate_project",
            suggested_capability="consultant.project_delegation",
            entity_hints={"client": "Esaote"},
        ),
        WORKSPACE_WITH_ESAOTE_CLIENT_ONLY,
    )

    assert result["status"] == "missing_prerequisite"
    assert result["missing_prerequisites"] == ["existing_project"]
    assert result["refused_route"] == "delegate_project"


def test_creating_the_project_container_is_authorized_setup():
    result = authorize(
        consulting_decision(
            route="setup",
            suggested_capability="consultant.setup",
            entity_hints={"client": "Esaote"},
        ),
        WORKSPACE_WITH_ESAOTE_CLIENT_ONLY,
    )

    assert result["status"] == "authorized"
    assert result["target"] == "setup_subgraph"


def test_an_existing_project_is_still_handed_over():
    result = authorize(
        consulting_decision(
            route="delegate_project",
            suggested_capability="consultant.project_delegation",
            entity_hints={"project": "Ciclo ordini"},
        ),
        WORKSPACE_WITH_ESAOTE_PROJECT,
    )

    assert result["status"] == "authorized"
    assert result["target"] == "project_macro"


@pytest.mark.parametrize(
    ("state", "hints", "expected"),
    [
        (WORKSPACE_WITH_ESAOTE_PROJECT, {"project": "Ciclo ordini"}, True),
        (WORKSPACE_WITH_ESAOTE_PROJECT, {"project": "esaote-ordini"}, True),
        (WORKSPACE_WITH_ESAOTE_PROJECT, {"project": "Ciclo fatture"}, False),
        (WORKSPACE_WITH_ESAOTE_PROJECT, {"client": "Esaote"}, True),
        (WORKSPACE_WITH_ESAOTE_PROJECT, {"client": "Bracco"}, False),
        (WORKSPACE_WITH_ESAOTE_PROJECT, {}, True),
        (WORKSPACE_WITH_ESAOTE_CLIENT_ONLY, {}, False),
    ],
)
def test_project_existence_is_read_from_records_not_from_the_router(state, hints, expected):
    assert has_existing_project({**state, "entity_hints": hints}) is expected


def test_an_unknown_workspace_blocks_the_handover_instead_of_assuming_it():
    # Nessun record caricato: delegare sarebbe una scommessa sul fatto che il
    # progetto esista.
    assert has_existing_project({"entity_hints": {"project": "Ciclo ordini"}}) is False


def test_the_capability_menu_tells_the_router_where_creation_belongs():
    menu = capability_menu("consultant")

    assert "consultant.setup" in menu
    assert "existing_project" in menu
    assert "Crea un progetto per" in menu


def test_setup_can_create_a_project_for_a_client_that_already_exists():
    names = {tool.name for tool in setup_tools}

    assert "list_workspace_clients" in names
    assert "create_workspace_project" in names
    assert len(setup_tools) <= 8


def test_workspace_records_load_without_a_model_and_survive_a_dead_database(monkeypatch):
    from backend.graphs.consulting import graph as consulting_graph

    monkeypatch.setattr(
        consulting_graph.workspace_database,
        "list_clients",
        lambda: [{"id": "esaote", "name": "Esaote"}],
    )
    monkeypatch.setattr(
        consulting_graph.workspace_database,
        "list_projects",
        lambda: [
            {
                "id": "esaote-ordini",
                "name": "Ciclo ordini",
                "client_id": "esaote",
                "client": "Esaote",
                "objective": "irrilevante per il routing",
            }
        ],
    )

    loaded = load_workspace_records({})

    assert loaded["workspace_clients"] == [{"id": "esaote", "name": "Esaote"}]
    assert loaded["workspace_projects"] == [
        {
            "id": "esaote-ordini",
            "name": "Ciclo ordini",
            "client_id": "esaote",
            "client": "Esaote",
        }
    ]

    def explode():
        raise RuntimeError("database irraggiungibile")

    monkeypatch.setattr(consulting_graph.workspace_database, "list_clients", explode)

    assert load_workspace_records({}) == {"workspace_clients": [], "workspace_projects": []}
