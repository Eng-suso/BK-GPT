"""Il registro dei consumi sa quale consulente ha speso.

Il limite d'uso della prova e' per persona. Il registro conosceva il tenant e non
il consulente: il dato c'era nell'autenticazione, ma non arrivava all'operazione.
Una dipendenza FastAPI sincrona gira in un thread con una copia del contesto, e
quello che imposta non arriva alla rotta: per questo `require_principal` e'
`async`, e il test end-to-end qui sotto lo tiene vero.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from backend.llm import LlmTask, Outcome, OperationKind, TokenUsage, new_operation, operation
from backend.security import get_current_user_id, require_principal, set_current_user_id
from backend.settings import settings


@pytest.fixture()
def nessun_consulente():
    token = set_current_user_id(None)
    yield
    from backend import security

    security._user_id.reset(token)


def test_l_operazione_prende_il_consulente_dalla_richiesta(nessun_consulente):
    set_current_user_id("consulente-a")

    assert new_operation(OperationKind.CHAT_TURN).user_id == "consulente-a"


def test_un_operazione_annidata_eredita_il_consulente_del_padre(nessun_consulente):
    with operation(OperationKind.CHAT_TURN, user_id="consulente-a"):
        assert new_operation(OperationKind.BPMN_DRAFT).user_id == "consulente-a"


def test_il_consulente_esplicito_vince(nessun_consulente):
    set_current_user_id("dalla-richiesta")

    with operation(OperationKind.KG_INGESTION, user_id="dal-job") as opened:
        assert opened.user_id == "dal-job"


def test_il_lavoro_che_nessuno_ha_chiesto_non_ha_consulente(nessun_consulente):
    assert new_operation(OperationKind.MEMORY_PROJECTION).user_id is None


def test_la_riga_del_registro_porta_il_consulente():
    from sqlalchemy import select

    from backend.llm import usage
    from backend.workspace_storage import WorkspaceLlmUsage, workspace_connection

    with operation(OperationKind.CHAT_TURN, user_id="consulente-ledger") as opened:
        usage.record(
            operation=opened,
            task=LlmTask.CHAT_TURN.value,
            model="gpt-test",
            outcome=Outcome.OK,
            tokens=TokenUsage(input=10, output=2),
        )

    with workspace_connection() as session:
        row = session.scalars(
            select(WorkspaceLlmUsage).where(WorkspaceLlmUsage.operation_id == opened.id)
        ).one()
        assert row.user_id == "consulente-ledger"


def test_il_consulente_autenticato_arriva_alla_rotta_sincrona(monkeypatch):
    monkeypatch.setattr(settings, "delir_auth_enabled", False)
    app = FastAPI()

    @app.get("/chi", dependencies=[Depends(require_principal)])
    def chi() -> dict:
        # Una rotta `def`, come quasi tutte quelle di DeliR: gira nel pool.
        return {"user_id": get_current_user_id(), "operation": new_operation("t").user_id}

    response = TestClient(app).get("/chi", headers={"X-DeliR-User-ID": "consulente-http"})

    assert response.status_code == 200
    assert response.json() == {"user_id": "consulente-http", "operation": "consulente-http"}


def test_l_ingestione_accodata_ricorda_chi_l_ha_causata(nessun_consulente):
    from backend.llm import current_user_id

    with operation(OperationKind.CHAT_TURN, user_id="consulente-kg"):
        assert current_user_id() == "consulente-kg"
