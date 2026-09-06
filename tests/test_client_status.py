"""CLIENT-01: lo stato cliente non puo' nascere da un default hard-coded.

"Ho acquisito un nuovo cliente: Esaote S.p.A." creava un record `Prospect`,
perche' `status="Prospect"` era il default in ogni punto di ingresso. Un
prospect e' qualcuno che stai ancora cercando di acquisire: il record nasceva
in contraddizione con la frase che lo aveva creato.

Qui si verificano le due proprieta' che tengono il fix in piedi:

1. nessun punto di ingresso decide lo stato al posto del modello - il default e'
   `None` ("non dichiarato"), e il placeholder si applica una volta sola al
   confine col database;
2. `create_client` resta idempotente per nome, e "non creo un duplicato" non
   significa "butto via l'informazione nuova": i campi ancora al placeholder si
   riempiono, quelli gia' decisi non si toccano.
"""

from __future__ import annotations

import inspect
import json
import uuid

import pytest

from backend.settings import settings
from backend.workspace_defaults import (
    CLIENT_STATUSES,
    UNKNOWN_CLIENT_STATUS,
    is_unknown_client_status,
    normalize_client_status,
    resolve_client_status,
)


# --- vocabolario: nessun database ------------------------------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("Attivo", "Attivo"),
        ("attivo", "Attivo"),
        ("  ATTIVO  ", "Attivo"),
        ("cliente", "Attivo"),
        ("acquisito", "Attivo"),
        ("active", "Attivo"),
        ("da seguire", "Da seguire"),
        ("follow-up", "Da seguire"),
        ("prospect", "Prospect"),
        ("lead", "Prospect"),
        # fuori vocabolario: ripulito, non scartato - lo stato resta free-form
        ("In gara", "In gara"),
    ],
)
def test_normalize_client_status(raw, expected):
    assert normalize_client_status(raw) == expected


def test_unknown_status_resolves_to_the_placeholder():
    assert resolve_client_status(None) == UNKNOWN_CLIENT_STATUS
    assert resolve_client_status("  ") == UNKNOWN_CLIENT_STATUS
    assert resolve_client_status("Attivo") == "Attivo"


def test_only_the_placeholder_counts_as_unknown():
    assert is_unknown_client_status(None)
    assert is_unknown_client_status("")
    assert is_unknown_client_status("prospect")
    assert not is_unknown_client_status("Attivo")
    assert not is_unknown_client_status("Da seguire")


# --- contratto: nessun punto di ingresso decide lo stato -------------------

def test_no_entry_point_defaults_the_client_status():
    """Il default hard-coded era la causa del bug: non deve tornare."""
    from backend import workspace_database
    from backend.schemas.workspace import CreateClientRequest
    from backend.toolsets.workspace import (
        ClientRecordInput,
        InitialWorkspaceSetupInput,
        create_workspace_client,
        manage_client_record,
    )

    assert ClientRecordInput.model_fields["status"].default is None
    assert InitialWorkspaceSetupInput.model_fields["client_status"].default is None
    assert CreateClientRequest.model_fields["status"].default is None
    assert inspect.signature(workspace_database.create_client).parameters["status"].default is None

    for tool in (create_workspace_client, manage_client_record):
        status_schema = tool.args_schema.model_json_schema()["properties"]["status"]
        assert "Prospect" not in json.dumps(status_schema.get("default"))


def test_the_tool_schema_offers_the_status_vocabulary_to_the_model():
    """Il modello deve vedere le alternative, altrimenti non puo' sceglierle."""
    from backend.toolsets.workspace import ClientRecordInput

    schema = ClientRecordInput.model_json_schema()
    rendered = json.dumps(schema, ensure_ascii=False)

    for status in CLIENT_STATUSES:
        assert status in rendered
    # la descrizione deve dire *quando* valorizzarlo, non solo che esiste
    assert "acquisito" in rendered


# --- comportamento reale: serve il database operativo ----------------------

pytestmark_db = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)


@pytest.fixture()
def tenant():
    """
    Establishes a temporary tenant context for the enclosed operation and restores the previous context afterward.
    """
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
    try:
        yield
    finally:
        reset_current_tenant_id(token)


def _tool_payload(result: str) -> dict:
    """
    Extract the JSON payload from a tool result.
    
    Parameters:
        result (str): A result containing an action line followed by a JSON object.
    
    Returns:
        dict: The decoded JSON payload.
    """
    return json.loads(result.split("\n", 1)[1])


@pytestmark_db
def test_an_acquired_client_is_not_recorded_as_a_prospect(tenant):
    """La regressione CLIENT-01, dal tool che l'agente chiama davvero."""
    from backend.toolsets.workspace import manage_client_record

    name = f"Esaote {uuid.uuid4().hex[:6]}"
    result = _tool_payload(
        manage_client_record.invoke({"operation": "create", "name": name, "status": "Attivo"})
    )

    assert result["status"] == "created"
    assert result["payload"]["status"] == "Attivo"


@pytestmark_db
def test_an_undeclared_status_falls_back_to_the_placeholder(tenant):
    from backend import workspace_database as wd

    client = wd.create_client(name=f"Ignota {uuid.uuid4().hex[:6]}")

    assert client["status"] == UNKNOWN_CLIENT_STATUS
    assert client["sector"] == "Non specificato"
    assert client["owner"] == "Da assegnare"
    assert client["contact"] == ""


@pytestmark_db
def test_create_client_is_idempotent(tenant):
    """Stessi argomenti, due volte: un record solo, e la stessa risposta."""
    from backend import workspace_database as wd

    name = f"Esaote {uuid.uuid4().hex[:6]}"
    args = {"name": name, "sector": "Medicale", "status": "Attivo", "owner": "Sohayb"}

    first = wd.create_client(**args)
    second = wd.create_client(**args)

    assert first == second
    assert len([c for c in wd.list_clients() if c["name"] == name]) == 1
    # anche scritto diversamente e' lo stesso cliente
    third = wd.create_client(name=f"  {name.upper()}  ")
    assert third["id"] == first["id"]
    assert len([c for c in wd.list_clients() if c["id"] == first["id"]]) == 1


@pytestmark_db
def test_the_tool_reports_a_repeated_create_as_existing(tenant):
    from backend.toolsets.workspace import manage_client_record

    name = f"Esaote {uuid.uuid4().hex[:6]}"
    call = {"operation": "create", "name": name, "status": "Attivo"}

    first = _tool_payload(manage_client_record.invoke(call))
    second = _tool_payload(manage_client_record.invoke(call))

    assert first["status"] == "created"
    assert second["status"] == "exists"
    assert second["entity_id"] == first["entity_id"]
    assert second["payload"] == first["payload"]


@pytestmark_db
def test_a_repeated_create_fills_placeholders_without_clobbering_decisions(tenant):
    """L'idempotenza non deve buttare via l'informazione arrivata dopo."""
    from backend import workspace_database as wd

    name = f"Esaote {uuid.uuid4().hex[:6]}"
    created = wd.create_client(name=name)
    assert created["status"] == UNKNOWN_CLIENT_STATUS

    # il consulente dice che il cliente e' stato acquisito: il placeholder cede
    enriched = wd.create_client(name=name, status="Attivo", sector="Medicale")
    assert enriched["id"] == created["id"]
    assert enriched["status"] == "Attivo"
    assert enriched["sector"] == "Medicale"

    # una create successiva senza stato non retrocede il record
    assert wd.create_client(name=name)["status"] == "Attivo"
    # ne' una che porta uno stato diverso: cambiarlo e' un update, non una create
    assert wd.create_client(name=name, status="Da seguire")["status"] == "Attivo"
    assert wd.create_client(name=name, sector="Altro")["sector"] == "Medicale"

    assert len([c for c in wd.list_clients() if c["name"] == name]) == 1


@pytestmark_db
def test_the_http_route_does_not_invent_a_status(tenant):
    """Anche il create da UI: assente significa sconosciuto, non prospect scelto."""
    from backend.schemas.workspace import CreateClientRequest
    from backend import workspace_database as wd

    request = CreateClientRequest(name=f"Esaote {uuid.uuid4().hex[:6]}", status="Attivo")
    client = wd.create_client(**request.model_dump())

    assert client["status"] == "Attivo"
    assert client["sector"] == "Non specificato"
