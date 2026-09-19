"""La coda dei confronti: una presa in carico scade, e non esce dal suo tenant.

Due difetti veri, non ipotesi:

1. il 2026-09-17 la coda marcava `running` e basta. Un confronto dura minuti - e'
   una lettura per fonte - e se il processo che lo stava facendo muore (riavvio,
   deploy) la riga resta presa in carico per sempre: nessuno la rilavora e il
   pannello mostra "Confronto in corso" all'infinito. E' il difetto che la coda
   dei piani aveva gia' chiuso con una scadenza;
2. le passate prendevano le righe piu' vecchie di **tutti** i tenant: nello stesso
   database di sviluppo dove vivono i dati veri, una passata di test ha preso in
   carico due processi reali.

Serve la DSN workspace.
"""

from __future__ import annotations

import uuid

import pytest

from backend.settings import settings

if not settings.workspace_database_url:
    pytest.skip("serve WORKSPACE_DATABASE_URL", allow_module_level=True)

from datetime import UTC, datetime, timedelta  # noqa: E402

from sqlalchemy import text  # noqa: E402

from backend import workspace_database as wd  # noqa: E402
from backend.process_understanding import ProcessUnderstanding  # noqa: E402
from backend.security import (  # noqa: E402
    get_current_tenant_id,
    reset_current_tenant_id,
    set_current_tenant_id,
)


def _process_with_plan(label: str) -> dict:
    client = wd.create_client(name=f"Contoso {label} {uuid.uuid4().hex[:5]}")
    project = wd.create_project(client_id=client["id"], name=f"Progetto {uuid.uuid4().hex[:5]}")
    process = wd.create_process(project_id=project["id"], name="Ciclo passivo")
    wd.prepare_bpmn_review(
        bpmn_model_id=process["bpmn_model_id"],
        process_description="Piano di prova.",
        process_understanding=ProcessUnderstanding(title="Ciclo passivo").model_dump(mode="json"),
    )
    return process


@pytest.fixture()
def tenant():
    token = set_current_tenant_id(f"t-conformance-queue-{uuid.uuid4().hex[:8]}")
    try:
        yield get_current_tenant_id()
    finally:
        reset_current_tenant_id(token)


def _leased_at(bpmn_model_id: str, value: str | None) -> None:
    with wd.workspace_connection() as session:
        session.execute(
            text(
                "UPDATE workspace_bpmn_reviews SET conformance_leased_at = :at "
                "WHERE bpmn_model_id = :model"
            ),
            {"at": value, "model": bpmn_model_id},
        )


def test_a_check_taken_by_a_worker_that_died_comes_back_on_its_own(tenant):
    process = _process_with_plan("lease")
    wd.request_conformance_check(process["bpmn_model_id"])

    taken = wd.due_conformance_checks(5, only_tenant_id=tenant)
    assert [row["bpmn_model_id"] for row in taken] == [process["bpmn_model_id"]]

    # Presa in carico fresca: un altro worker non la tocca.
    assert wd.due_conformance_checks(5, only_tenant_id=tenant) == []

    # Il worker muore: la riga resta `running` e nessuno la rilascia.
    _leased_at(
        process["bpmn_model_id"],
        (datetime.now(UTC) - timedelta(seconds=wd.CONFORMANCE_LEASE_SECONDS + 60)).isoformat(
            timespec="seconds"
        ),
    )

    again = wd.due_conformance_checks(5, only_tenant_id=tenant)
    assert [row["bpmn_model_id"] for row in again] == [process["bpmn_model_id"]], (
        "una presa in carico scaduta deve tornare eleggibile da sola"
    )


def test_a_finished_check_releases_what_it_had_taken(tenant):
    process = _process_with_plan("release")
    wd.request_conformance_check(process["bpmn_model_id"])
    wd.due_conformance_checks(5, only_tenant_id=tenant)

    wd.record_conformance_report(process["bpmn_model_id"], {"verdict": "conformant"})

    state = wd.get_bpmn_review(process["bpmn_model_id"], include_approved=True)["conformance"]
    assert state["status"] == "done"
    assert wd.due_conformance_checks(5, only_tenant_id=tenant) == []


def test_a_queue_pass_stays_inside_its_own_workspace():
    """Il difetto del 2026-09-17: una passata di test prese due processi reali."""
    mine = set_current_tenant_id(f"t-queue-mine-{uuid.uuid4().hex[:6]}")
    try:
        my_process = _process_with_plan("mine")
        wd.request_conformance_check(my_process["bpmn_model_id"])
        my_tenant = get_current_tenant_id()
    finally:
        reset_current_tenant_id(mine)

    other = set_current_tenant_id(f"t-queue-other-{uuid.uuid4().hex[:6]}")
    try:
        other_process = _process_with_plan("other")
        wd.request_conformance_check(other_process["bpmn_model_id"])
    finally:
        reset_current_tenant_id(other)

    token = set_current_tenant_id(my_tenant)
    try:
        taken = wd.due_conformance_checks(10, only_tenant_id=my_tenant)
    finally:
        reset_current_tenant_id(token)

    assert [row["bpmn_model_id"] for row in taken] == [my_process["bpmn_model_id"]]

    # E la riga dell'altro workspace e' rimasta intatta, in attesa.
    with wd.workspace_connection() as session:
        status = session.execute(
            text(
                "SELECT conformance_status, conformance_leased_at FROM workspace_bpmn_reviews "
                "WHERE bpmn_model_id = :model"
            ),
            {"model": other_process["bpmn_model_id"]},
        ).first()
    assert status[0] == "pending" and status[1] is None


def test_the_worker_pass_of_a_test_cannot_reach_another_workspace():
    """La difesa non e' solo il parametro: nei test vale anche senza chiederlo.

    Il worker drena senza dire un tenant - e' cosi' che gira in produzione. Nei
    test quella stessa passata deve restare dentro il tenant del test, altrimenti
    il primo `drain_once()` scritto per comodita' rimette in gioco il difetto.
    """
    from backend.workers import conformance_worker

    other = set_current_tenant_id(f"t-queue-outsider-{uuid.uuid4().hex[:6]}")
    try:
        outsider = _process_with_plan("outsider")
        wd.request_conformance_check(outsider["bpmn_model_id"])
    finally:
        reset_current_tenant_id(other)

    token = set_current_tenant_id(f"t-queue-worker-{uuid.uuid4().hex[:6]}")
    try:
        conformance_worker.drain_once(limit=10)
    finally:
        reset_current_tenant_id(token)

    with wd.workspace_connection() as session:
        status = session.execute(
            text(
                "SELECT conformance_status FROM workspace_bpmn_reviews WHERE bpmn_model_id = :model"
            ),
            {"model": outsider["bpmn_model_id"]},
        ).scalar()
    assert status == "pending", "la coda di un altro workspace non si tocca"
