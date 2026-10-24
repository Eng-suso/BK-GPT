"""Ogni scrittura del disegno rifa' il confronto con le fonti, e il worker non lo perde.

Le regole sono quelle che `update_bpmn_model` gia' rispettava; qui valgono per
tutte le strade che cambiano il disegno, e per il worker che chiude un confronto:

| strada | prima | ora |
| --- | --- | --- |
| ripristino di una versione | il confronto restava `done` sul disegno vecchio | torna in coda |
| approvazione della review | scriveva il disegno senza lock ne' controllo di conflitto, fuori dal registro del turno, senza rimettere in coda il confronto | come ogni scrittura del disegno |
| worker che chiude un confronto | un disegno salvato mentre leggeva le fonti veniva segnato `done` con il rapporto del vecchio | il rapporto si registra, la riga resta in coda |
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import text

from backend.settings import settings

pytestmark = pytest.mark.skipif(not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL")

_XML = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" id="d">
  <process id="p"><task id="t1" name="{name}"/></process>
</definitions>"""


@pytest.fixture()
def tenant() -> Iterator[str]:
    from backend.security import get_current_tenant_id, reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-conformance-writes-{uuid.uuid4().hex[:8]}")
    try:
        yield get_current_tenant_id()
    finally:
        reset_current_tenant_id(token)


def _process_with_plan() -> dict:
    from backend import workspace_database as wd
    from backend.process_understanding import ProcessUnderstanding

    client = wd.create_client(name=f"Contoso {uuid.uuid4().hex[:5]}")
    project = wd.create_project(client_id=client["id"], name=f"Progetto {uuid.uuid4().hex[:5]}")
    process = wd.create_process(project_id=project["id"], name="Ciclo passivo")
    wd.prepare_bpmn_review(
        bpmn_model_id=process["bpmn_model_id"],
        process_description="Piano di prova.",
        process_understanding=ProcessUnderstanding(title="Ciclo passivo").model_dump(mode="json"),
    )
    return process


def _status(bpmn_model_id: str) -> str | None:
    from backend import workspace_database as wd

    with wd.workspace_connection() as session:
        return session.execute(
            text("SELECT conformance_status FROM workspace_bpmn_reviews WHERE bpmn_model_id = :model"),
            {"model": bpmn_model_id},
        ).scalar()


def _checked(bpmn_model_id: str, tenant: str) -> None:
    """Il confronto del disegno attuale e' fatto e chiuso."""
    from backend import workspace_database as wd

    wd.request_conformance_check(bpmn_model_id)
    wd.due_conformance_checks(5, only_tenant_id=tenant)
    wd.record_conformance_report(bpmn_model_id, {"verdict": "conformant"})
    assert _status(bpmn_model_id) == "done"


# --- ripristino --------------------------------------------------------------


def test_restoring_an_old_drawing_checks_it_against_the_sources_again(tenant):
    from backend import workspace_database as wd

    model_id = _process_with_plan()["bpmn_model_id"]
    wd.update_bpmn_model(model_id, _XML.format(name="Prima"))
    first = wd.get_bpmn_model(model_id)["version_id"]
    wd.update_bpmn_model(model_id, _XML.format(name="Seconda"))
    _checked(model_id, tenant)

    wd.restore_bpmn_version(model_id, first)

    assert _status(model_id) == "pending", "il rapporto parla del disegno di prima del ripristino"


# --- approvazione ------------------------------------------------------------


def test_approving_the_plan_checks_the_new_drawing_against_the_sources(tenant):
    from backend import workspace_database as wd

    model_id = _process_with_plan()["bpmn_model_id"]
    _checked(model_id, tenant)

    wd.approve_bpmn_review(model_id, override=True)

    assert _status(model_id) == "pending", "il disegno generato dall'approvazione non e' stato confrontato"


def test_an_approval_does_not_trip_the_next_write_of_the_same_turn(tenant):
    """L'approvazione dell'agente e' una sua scrittura, non quella di un collega."""
    from backend import workspace_database as wd
    from backend.agents.run_context import bind_turn_writes

    model_id = _process_with_plan()["bpmn_model_id"]
    wd.update_bpmn_model(model_id, _XML.format(name="Prima"))
    seen = wd.get_bpmn_model(model_id)["version_id"]

    with bind_turn_writes({model_id: seen}):
        wd.approve_bpmn_review(model_id, override=True)
        saved = wd.update_bpmn_model(model_id, _XML.format(name="Dopo l'approvazione"))

    assert saved["xml"]
    assert "Dopo l'approvazione" in wd.get_bpmn_model(model_id)["xml"]


def test_an_approval_does_not_overwrite_a_drawing_saved_meanwhile(tenant):
    from backend import workspace_database as wd
    from backend.agents.run_context import BpmnVersionConflict, bind_turn_writes

    model_id = _process_with_plan()["bpmn_model_id"]
    wd.update_bpmn_model(model_id, _XML.format(name="Prima"))
    seen = wd.get_bpmn_model(model_id)["version_id"]
    wd.update_bpmn_model(model_id, _XML.format(name="Del collega"), source="manual_save")

    with bind_turn_writes({model_id: seen}), pytest.raises(BpmnVersionConflict):
        wd.approve_bpmn_review(model_id, override=True)

    assert "Del collega" in wd.get_bpmn_model(model_id)["xml"]


# --- worker ------------------------------------------------------------------


class _Report:
    def model_dump(self, mode: str = "python") -> dict:
        return {"verdict": "conformant", "process_id": "p"}


def _audit_racing_a_new_drawing(model_id: str, *, then=None):
    """Un confronto durante il quale il consulente salva un disegno nuovo.

    Rispetta il contratto di `audit_process_conformance`: con `persist` registra
    il rapporto da se'.
    """
    from backend import workspace_database as wd

    def _audit(process_id, *, persist: bool = True, **_kwargs):
        wd.update_bpmn_model(model_id, _XML.format(name="Salvato durante la lettura"), source="manual_save")
        if then is not None:
            then()
        report = _Report()
        if persist:
            wd.record_conformance_report(model_id, report.model_dump(mode="json"))
        return report

    return _audit


def test_a_drawing_saved_while_the_sources_are_read_is_checked_again(tenant, monkeypatch):
    from backend import workspace_database as wd
    from backend.agents import conformance_audit
    from backend.workers import conformance_worker

    model_id = _process_with_plan()["bpmn_model_id"]
    wd.request_conformance_check(model_id)
    monkeypatch.setattr(conformance_audit, "audit_process_conformance", _audit_racing_a_new_drawing(model_id))

    conformance_worker.drain_once(limit=5, only_tenant_id=tenant)

    assert _status(model_id) == "pending", "il confronto del disegno nuovo e' andato perso"
    # Il rapporto del giro finito resta registrato: dice su quale disegno e' stato fatto.
    report = wd.get_bpmn_review(model_id, include_approved=True)["conformance"]["report"]
    assert report["verdict"] == "conformant"
    assert [row["bpmn_model_id"] for row in wd.due_conformance_checks(5, only_tenant_id=tenant)] == [model_id]


def test_an_unreadable_plan_does_not_drop_a_drawing_saved_meanwhile(tenant, monkeypatch):
    from backend import workspace_database as wd
    from backend.agents import conformance_audit
    from backend.workers import conformance_worker

    model_id = _process_with_plan()["bpmn_model_id"]
    wd.request_conformance_check(model_id)

    def _unreadable():
        raise wd.UnreadableReviewError("piano illeggibile")

    monkeypatch.setattr(
        conformance_audit, "audit_process_conformance", _audit_racing_a_new_drawing(model_id, then=_unreadable)
    )

    conformance_worker.drain_once(limit=5, only_tenant_id=tenant)

    assert _status(model_id) == "pending"


def _lease(bpmn_model_id: str) -> str | None:
    from backend import workspace_database as wd

    with wd.workspace_connection() as session:
        return session.execute(
            text("SELECT conformance_leased_at FROM workspace_bpmn_reviews WHERE bpmn_model_id = :model"),
            {"model": bpmn_model_id},
        ).scalar()


def test_a_worker_does_not_close_the_claim_of_the_worker_after_it(tenant, monkeypatch):
    """Due prese in carico in fila: la prima non tocca la seconda.

    Il disegno cambia mentre il primo worker legge le fonti, e un secondo worker
    prende in carico il confronto nuovo prima che il primo finisca. Lo stato
    della riga e' di nuovo `running`, ma la presa in carico non e' piu' quella
    del primo: il suo rapporto e la sua chiusura non valgono per la seconda.
    """
    from backend import workspace_database as wd
    from backend.agents import conformance_audit
    from backend.workers import conformance_worker

    model_id = _process_with_plan()["bpmn_model_id"]
    wd.request_conformance_check(model_id)
    second: dict = {}

    def _second_worker_claims():
        taken = wd.due_conformance_checks(5, only_tenant_id=tenant)
        assert [row["bpmn_model_id"] for row in taken] == [model_id]
        second["lease"] = _lease(model_id)

    monkeypatch.setattr(
        conformance_audit,
        "audit_process_conformance",
        _audit_racing_a_new_drawing(model_id, then=_second_worker_claims),
    )

    conformance_worker.drain_once(limit=1, only_tenant_id=tenant)

    assert _status(model_id) == "running", "il primo worker ha chiuso la presa in carico del secondo"
    assert _lease(model_id) == second["lease"]
    review = wd.get_bpmn_review(model_id, include_approved=True)
    assert (review["conformance"] or {}).get("report") is None, "il rapporto del primo e' finito sul confronto del secondo"


def test_a_worker_whose_report_was_refused_does_not_count_it_as_written(tenant, monkeypatch):
    """`_work_one` dice `True` solo se il rapporto e' stato davvero registrato."""
    from backend import workspace_database as wd
    from backend.agents import conformance_audit
    from backend.workers import conformance_worker

    model_id = _process_with_plan()["bpmn_model_id"]
    wd.request_conformance_check(model_id)
    monkeypatch.setattr(
        conformance_audit,
        "audit_process_conformance",
        _audit_racing_a_new_drawing(model_id, then=lambda: wd.due_conformance_checks(5, only_tenant_id=tenant)),
    )
    (row,) = wd.due_conformance_checks(5, only_tenant_id=tenant)

    assert conformance_worker._work_one(row) is False, "il rapporto rifiutato e' stato contato come scritto"
