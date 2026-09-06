"""PROJECT-01: il progetto deve conservare l'incarico, non solo il contenitore.

"Ricostruire l'AS-IS del ciclo ordini, validarlo con gli stakeholder, simularlo
e misurare i KPI" era l'obiettivo dichiarato dal consulente. Il record che ne
nasceva conservava nome, fase, stato, avanzamento, prossimo passo, milestone,
issue e deliverable: tutto tranne il perche'. La frase restava nella chat
history, e una Project Chat aperta dopo conosceva il contenitore ma non il
mandato.

Qui si verificano tre proprieta':

1. `objective` e' un campo del record, arriva dal tool e dall'HTTP, e non ha
   placeholder - una frase inventata al posto del consulente sarebbe peggio di
   un campo vuoto;
2. l'obiettivo raggiunge il prompt della Project Chat, che e' il punto dove il
   bug si manifestava;
3. fase e stato hanno un vocabolario definito in un posto solo, e nessun punto
   di ingresso decide il loro valore al posto del modello o del consulente.
"""

from __future__ import annotations

import inspect
import json
import uuid

import pytest

from backend.settings import settings
from backend.workspace_defaults import (
    DEFAULT_PROJECT_PHASE,
    DEFAULT_PROJECT_STATUS,
    PROJECT_PHASE_MEANINGS,
    PROJECT_PHASES,
    PROJECT_STATUS_MEANINGS,
    PROJECT_STATUSES,
    normalize_project_phase,
    normalize_project_status,
    resolve_project_phase,
    resolve_project_status,
)


# --- vocabolario: nessun database ------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("Discovery", "Discovery"),
        ("  discovery ", "Discovery"),
        ("as is", "AS-IS"),
        ("AS-IS", "AS-IS"),
        ("mappatura", "AS-IS"),
        ("to be", "TO-BE"),
        ("simulation", "Simulazione"),
        ("consegna", "Delivery"),
        # fuori vocabolario: ripulito, non scartato
        ("Pre-kickoff", "Pre-kickoff"),
    ],
)
def test_normalize_project_phase(raw, expected):
    assert normalize_project_phase(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("  ", None),
        ("in corso", "In corso"),
        ("attivo", "In corso"),
        ("at risk", "A rischio"),
        ("sospeso", "In pausa"),
        ("concluso", "Completato"),
        ("In gara", "In gara"),
    ],
)
def test_normalize_project_status(raw, expected):
    assert normalize_project_status(raw) == expected


def test_unknown_phase_and_status_resolve_to_the_placeholder():
    assert resolve_project_phase(None) == DEFAULT_PROJECT_PHASE
    assert resolve_project_status(None) == DEFAULT_PROJECT_STATUS
    assert resolve_project_phase("to be") == "TO-BE"
    assert resolve_project_status("at risk") == "A rischio"


def test_every_vocabulary_entry_has_a_definition():
    """Una fase senza definizione e' una stringa: il consulente deve sapere cosa
    significa "Validazione" senza chiederlo all'agente."""
    assert tuple(PROJECT_PHASE_MEANINGS) == PROJECT_PHASES
    assert tuple(PROJECT_STATUS_MEANINGS) == PROJECT_STATUSES
    assert all(meaning.strip() for meaning in PROJECT_PHASE_MEANINGS.values())
    assert all(meaning.strip() for meaning in PROJECT_STATUS_MEANINGS.values())


# --- contratto: nessun punto di ingresso decide fase, stato o obiettivo ----

def test_no_entry_point_defaults_phase_status_or_objective():
    from backend import workspace_database
    from backend.schemas.workspace import CreateProjectRequest
    from backend.toolsets.workspace import InitialWorkspaceSetupInput, ProjectRecordInput

    for field in ("objective", "phase", "status", "next_step"):
        assert ProjectRecordInput.model_fields[field].default is None
        assert CreateProjectRequest.model_fields[field].default is None
        assert inspect.signature(workspace_database.create_project).parameters[field].default is None

    assert InitialWorkspaceSetupInput.model_fields["project_objective"].default is None


def test_the_tool_schema_offers_the_project_vocabulary_to_the_model():
    from backend.toolsets.workspace import ProjectRecordInput

    rendered = json.dumps(ProjectRecordInput.model_json_schema(), ensure_ascii=False)

    for phase in PROJECT_PHASES:
        assert phase in rendered
    for status in PROJECT_STATUSES:
        assert status in rendered
    # la descrizione deve dire *perche'* l'obiettivo va registrato
    assert "Project Chat" in rendered


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


OBJECTIVE = (
    "Ricostruire l'AS-IS del ciclo ordini, validarlo con gli stakeholder, "
    "simularlo e misurare i KPI di lead time."
)


@pytestmark_db
def test_the_objective_survives_project_creation(tenant):
    from backend import workspace_database as wd

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    project = wd.create_project(
        client_id=client["id"],
        name=f"Ciclo ordini {uuid.uuid4().hex[:6]}",
        objective=OBJECTIVE,
    )

    assert project["objective"] == OBJECTIVE
    assert wd.get_project(project["id"])["objective"] == OBJECTIVE
    # i placeholder restano quelli del vocabolario, in un punto solo
    assert project["phase"] == DEFAULT_PROJECT_PHASE
    assert project["status"] == DEFAULT_PROJECT_STATUS


@pytestmark_db
def test_a_project_created_without_an_objective_says_so(tenant):
    """Il campo vuoto non e' un dettaglio silenzioso: l'agente lo deve vedere."""
    from backend import workspace_database as wd
    from backend.toolsets.workspace import create_workspace_project

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    result = _tool_payload(
        create_workspace_project.invoke(
            {"client_id": client["id"], "name": f"Senza brief {uuid.uuid4().hex[:6]}"}
        )
    )

    assert result["status"] == "created"
    assert result["payload"]["objective"] == ""
    assert any("objective" in warning for warning in result["warnings"])


@pytestmark_db
def test_the_project_chat_reads_the_objective_back(tenant):
    """Il bug si manifestava qui: la chat conosceva il contenitore, non il mandato."""
    from backend import workspace_database as wd
    from backend.agents.primary_scope import build_scope_system_prompt
    from backend.graphs.project.nodes import load_project_context

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    project = wd.create_project(
        client_id=client["id"],
        name=f"Ciclo ordini {uuid.uuid4().hex[:6]}",
        objective=OBJECTIVE,
    )

    context = load_project_context({"project_id": project["id"]})
    assert context["engagement_objective"] == OBJECTIVE

    prompt = build_scope_system_prompt({"scope_type": "project", "project_id": project["id"], **context})
    assert OBJECTIVE in prompt


@pytestmark_db
def test_the_chat_is_told_when_the_objective_is_missing(tenant):
    from backend.agents.primary_scope import build_scope_system_prompt

    prompt = build_scope_system_prompt(
        {"scope_type": "project", "project_id": "p-1", "engagement_objective": None}
    )

    assert "project_objective: non registrato" in prompt
    assert "update_workspace_project" in prompt


@pytestmark_db
def test_update_project_touches_only_the_declared_fields(tenant):
    from backend import workspace_database as wd

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    project = wd.create_project(
        client_id=client["id"],
        name=f"Ciclo ordini {uuid.uuid4().hex[:6]}",
        objective=OBJECTIVE,
        milestones=["Kickoff"],
    )

    updated = wd.update_project(project["id"], phase="validazione", progress=140)

    assert updated["phase"] == "Validazione"
    assert updated["progress"] == 100  # clamp, non errore
    assert updated["objective"] == OBJECTIVE
    assert updated["milestones"] == ["Kickoff"]
    assert updated["name"] == project["name"]


@pytestmark_db
def test_update_project_replaces_lists_whole(tenant):
    """La UI manda la lista che ha in mano: `[]` svuota, `None` non tocca."""
    from backend import workspace_database as wd

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    project = wd.create_project(
        client_id=client["id"],
        name=f"Ciclo ordini {uuid.uuid4().hex[:6]}",
        milestones=["Kickoff", "Validazione AS-IS"],
        deliverables=["Report AS-IS"],
    )

    updated = wd.update_project(
        project["id"],
        milestones=["Kickoff", "  ", "Simulazione"],
        deliverables=[],
    )

    assert updated["milestones"] == ["Kickoff", "Simulazione"]  # righe vuote scartate
    assert updated["deliverables"] == []


@pytestmark_db
def test_update_project_rejects_an_unknown_project(tenant):
    from backend import workspace_database as wd

    with pytest.raises(ValueError, match="non trovato"):
        wd.update_project("progetto-che-non-esiste", phase="TO-BE")


@pytestmark_db
def test_update_client_corrects_a_decided_value(tenant):
    """`create_client` riempie solo i placeholder: correggere e' un update."""
    from backend import workspace_database as wd

    client = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}", status="Prospect")
    updated = wd.update_client(client["id"], status="attivo", owner="Sohayb")

    assert updated["status"] == "Attivo"
    assert updated["owner"] == "Sohayb"
    assert updated["sector"] == client["sector"]
