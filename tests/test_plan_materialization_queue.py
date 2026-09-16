"""Il piano si ricostruisce quando cambia l'evidenza, non davanti a chi aspetta.

La sintesi del piano costa tre chiamate al modello, e viveva dentro il percorso
critico di «Genera BPMN». Qui si verifica che quel lavoro sia uscito di li':

- salvare una fonte mette il processo in coda, nella stessa transazione della
  fonte;
- cinque fonti di seguito non sono cinque ricostruzioni, sono una;
- il worker lavora la coda dentro il tenant della riga;
- un guasto momentaneo si riprova con backoff, un processo che non esiste no;
- con il piano gia' materializzato, il comando di disegno non chiama nessun
  modello.

Servono la DSN workspace e quelle canonical (`cd ops && docker compose up -d`).
"""

from __future__ import annotations

import uuid

import pytest

from backend.settings import settings

if not all((settings.workspace_database_url, settings.canonical_database_url)):
    pytest.skip(
        "servono WORKSPACE_DATABASE_URL e le DSN canonical",
        allow_module_level=True,
    )

from backend import workspace_database as wd  # noqa: E402
from backend.agents import process_synthesis  # noqa: E402
from backend.agents.process_snapshot import build_process_snapshot  # noqa: E402
from backend.agents.process_synthesis import PlanSynthesis  # noqa: E402
from backend.security import get_current_tenant_id  # noqa: E402
from backend.workers import plan_worker  # noqa: E402
from backend.workspace_services.bpmn_draft import generate_bpmn_draft  # noqa: E402

from tests.test_process_canvas_handoff_e2e import (  # noqa: E402
    _bind_process_chat,
    _prepare_plan,
    _save_interviews,
    empty_process,  # noqa: F401 - fixture
)


@pytest.fixture(autouse=True)
def _no_live_model(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None)


@pytest.fixture(autouse=True)
def _empty_queue():
    """La coda parte vuota a ogni test.

    Il worker prende le richieste piu' vecchie per prime: senza questo, le righe
    lasciate da un test precedente riempiono il lotto e quella del test corrente
    non viene mai lavorata. Il test fallirebbe raccontando un difetto che non
    c'e'.
    """
    _purge_queue()
    yield
    _purge_queue()


def _purge_queue() -> None:
    from sqlalchemy import delete

    from backend.workspace_storage import (
        WorkspacePlanMaterialization,
        workspace_connection,
    )

    with workspace_connection() as session:
        session.execute(delete(WorkspacePlanMaterialization))


def test_saving_a_source_queues_the_plan(empty_process):  # noqa: F811
    """La fonte entra e il piano risulta da rifare, senza che nessuno lo chieda."""
    assert wd.plan_materialization_for(empty_process["process_id"]) is None

    wd.create_project_source(
        project_id=empty_process["project_id"],
        name="Intervista Laura Conti",
        type="Intervista",
        process_id=empty_process["process_id"],
    )

    queued = wd.plan_materialization_for(empty_process["process_id"])
    assert queued is not None
    assert queued["status"] == "pending"
    assert "Laura" in queued["reason"]


def test_five_sources_are_one_rebuild(empty_process):  # noqa: F811
    """Cinque interviste di seguito sono una sintesi dopo l'ultima, non cinque."""
    for index in range(5):
        wd.create_project_source(
            project_id=empty_process["project_id"],
            name=f"Fonte {index}",
            type="Intervista",
            process_id=empty_process["process_id"],
        )

    rows = wd.due_plan_materializations(limit=50)
    mine = [row for row in rows if row["process_id"] == empty_process["process_id"]]
    assert len(mine) == 1
    assert mine[0]["attempts"] == 0


def test_a_source_that_fails_to_save_leaves_no_queued_work(empty_process, monkeypatch):  # noqa: F811
    """Coda e fonte stanno nella stessa transazione, o non vale niente.

    Se la richiesta di ricostruzione sopravvivesse a un salvataggio annullato, il
    worker ricostruirebbe il piano per una fonte che non esiste: lavoro speso su
    una conoscenza che nessuno ha registrato.
    """
    original = wd.enqueue_plan_materialization

    def _boom(process_id, *, reason="", session=None):
        original(process_id, reason=reason, session=session)
        raise RuntimeError("guasto dopo l'inserimento in coda")

    monkeypatch.setattr(wd, "enqueue_plan_materialization", _boom)

    with pytest.raises(RuntimeError):
        wd.create_project_source(
            project_id=empty_process["project_id"],
            name="Fonte che non arriva",
            type="Intervista",
            process_id=empty_process["process_id"],
        )

    assert wd.plan_materialization_for(empty_process["process_id"]) is None
    names = [item["name"] for item in wd.list_project_sources(empty_process["project_id"])]
    assert "Fonte che non arriva" not in names


def test_a_project_source_without_a_process_queues_nothing(empty_process):  # noqa: F811
    """Una fonte di progetto non appartiene a nessun processo: niente da rifare."""
    wd.create_project_source(
        project_id=empty_process["project_id"],
        name="Documento di progetto",
        type="Documento",
        process_id=None,
    )

    assert wd.plan_materialization_for(empty_process["process_id"]) is None


def test_the_worker_materializes_the_plan_inside_the_row_tenant(empty_process, monkeypatch):  # noqa: F811
    """Il worker gira fuori da una richiesta HTTP: il tenant lo porta la riga."""
    _save_interviews(empty_process)
    tenant = get_current_tenant_id()
    seen: list[tuple[str, str]] = []

    def _fake_ensure(process_id: str, *, force: bool = False) -> PlanSynthesis:
        seen.append((process_id, get_current_tenant_id()))
        return PlanSynthesis(
            action="synthesized",
            snapshot=build_process_snapshot(process_id),
            reason="piano costruito nel test",
        )

    monkeypatch.setattr(process_synthesis, "ensure_process_plan", _fake_ensure)

    processed = plan_worker.drain_once(limit=50)

    assert processed >= 1
    assert (empty_process["process_id"], tenant) in seen
    row = wd.plan_materialization_for(empty_process["process_id"])
    assert row["status"] == "done"
    assert row["last_action"] == "synthesized"


def test_two_tenants_are_worked_each_inside_its_own(monkeypatch):
    """Due richieste, due confini: nessuna delle due lavora dentro l'altro.

    Con un tenant solo il test passerebbe anche se il worker usasse quello
    ambientale: la prova sta nell'avere due righe e vedere che ognuna porta il
    proprio.
    """
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    created: list[tuple[str, str]] = []
    for _ in range(2):
        tenant = f"t-plan-{uuid.uuid4().hex[:8]}"
        token = set_current_tenant_id(tenant)
        try:
            client = wd.create_client(name=f"Cliente {uuid.uuid4().hex[:6]}")
            project = wd.create_project(client_id=client["id"], name="Acquisti")
            process = wd.create_process(project_id=project["id"], name="Ciclo passivo")
            wd.create_project_source(
                project_id=project["id"],
                name="Intervista",
                type="Intervista",
                process_id=process["id"],
            )
            created.append((tenant, process["id"]))
        finally:
            reset_current_tenant_id(token)

    seen: list[tuple[str, str]] = []

    def _fake_ensure(process_id: str, *, force: bool = False) -> PlanSynthesis:
        seen.append((get_current_tenant_id(), process_id))
        return PlanSynthesis(action="synthesized", snapshot=None, reason="test")

    monkeypatch.setattr(process_synthesis, "ensure_process_plan", _fake_ensure)

    plan_worker.drain_once(limit=50)

    assert sorted(seen) == sorted(created)
    for tenant, process_id in created:
        token = set_current_tenant_id(tenant)
        try:
            assert wd.plan_materialization_for(process_id)["status"] == "done"
        finally:
            reset_current_tenant_id(token)


def test_a_transient_failure_is_retried_later(empty_process, monkeypatch):  # noqa: F811
    """Il modello in rate limit non e' un piano impossibile: si riprova."""
    _save_interviews(empty_process)

    def _explode(process_id: str, *, force: bool = False):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(process_synthesis, "ensure_process_plan", _explode)

    plan_worker.drain_once(limit=50)

    row = wd.plan_materialization_for(empty_process["process_id"])
    assert row["status"] == "pending"
    assert row["attempts"] == 1
    assert "429" in row["last_error"]
    # Non e' piu' eleggibile adesso: il backoff la tiene fuori dalla prossima
    # passata, altrimenti il worker girerebbe a vuoto sullo stesso guasto.
    ready = [
        item
        for item in wd.due_plan_materializations(limit=50)
        if item["process_id"] == empty_process["process_id"]
    ]
    assert not ready


def test_a_process_that_no_longer_exists_leaves_the_queue_at_once(
    empty_process,  # noqa: F811
    monkeypatch,
):
    """Riprovare cinque volte per dire la stessa cosa riempie i log e basta."""
    _save_interviews(empty_process)

    def _gone(process_id: str, *, force: bool = False) -> PlanSynthesis:
        return PlanSynthesis(
            action="process_not_found",
            snapshot=None,
            reason=f"Processo non trovato: {process_id}",
        )

    monkeypatch.setattr(process_synthesis, "ensure_process_plan", _gone)

    plan_worker.drain_once(limit=50)

    row = wd.plan_materialization_for(empty_process["process_id"])
    assert row["status"] == "failed"
    assert row["attempts"] == 1


def test_a_new_source_reopens_a_failed_request(empty_process):  # noqa: F811
    """Una fonte nuova rende di nuovo utile un lavoro che aveva rinunciato."""
    wd.create_project_source(
        project_id=empty_process["project_id"],
        name="Prima fonte",
        type="Intervista",
        process_id=empty_process["process_id"],
    )
    row = wd.plan_materialization_for(empty_process["process_id"])
    wd.fail_plan_materialization(row["id"], error="guasto", max_attempts=1)
    assert wd.plan_materialization_for(empty_process["process_id"])["status"] == "failed"

    wd.create_project_source(
        project_id=empty_process["project_id"],
        name="Seconda fonte",
        type="Intervista",
        process_id=empty_process["process_id"],
    )

    reopened = wd.plan_materialization_for(empty_process["process_id"])
    assert reopened["status"] == "pending"
    assert reopened["attempts"] == 0
    assert reopened["last_error"] is None


def test_the_command_declares_a_plan_that_is_behind_the_evidence(empty_process):  # noqa: F811
    """Disegnare un piano indietro e' onesto solo se si dice che e' indietro."""
    _save_interviews(empty_process)
    _prepare_plan(empty_process)

    wd.create_project_source(
        project_id=empty_process["project_id"],
        name="Intervista Marco Gallo",
        type="Intervista",
        process_id=empty_process["process_id"],
    )

    with _bind_process_chat(empty_process["project_id"], empty_process["process_id"]):
        result = generate_bpmn_draft(
            empty_process["process_id"], synthesize_missing_plan=False
        )

    assert result.status == "drafted"
    assert result.metrics["llm_calls"] == 0
    assert any("ultima evidenza" in item for item in result.pending_verification)


def test_taking_a_row_hides_it_from_the_other_workers(empty_process):  # noqa: F811
    """Due worker non sintetizzano lo stesso piano due volte.

    Senza presa in carico, due istanze dell'app leggevano la stessa riga e il
    processo si trovava due versioni del piano nate dallo stesso evento.
    """
    wd.create_project_source(
        project_id=empty_process["project_id"],
        name="Fonte contesa",
        type="Intervista",
        process_id=empty_process["process_id"],
    )

    first = [
        row
        for row in wd.due_plan_materializations(limit=50)
        if row["process_id"] == empty_process["process_id"]
    ]
    second = [
        row
        for row in wd.due_plan_materializations(limit=50)
        if row["process_id"] == empty_process["process_id"]
    ]

    assert len(first) == 1
    assert second == [], "la riga presa in carico non deve tornare al giro dopo"
    # Non e' uno stato `running`: e' una scadenza, e quando passa la riga torna
    # eleggibile da sola anche se chi l'aveva presa e' morto.
    assert wd.plan_materialization_for(empty_process["process_id"])["status"] == "pending"


def test_the_queue_counts_what_is_waiting_and_what_gave_up(empty_process):  # noqa: F811
    wd.create_project_source(
        project_id=empty_process["project_id"],
        name="Fonte per le statistiche",
        type="Intervista",
        process_id=empty_process["process_id"],
    )

    stats = plan_worker.queue_stats()

    assert stats["pending"] >= 1
    assert set(stats) == {"pending", "done", "stuck"}


def test_an_unknown_process_id_is_not_queued():
    assert wd.enqueue_plan_materialization(None) is None
    assert wd.enqueue_plan_materialization("") is None


def test_a_failed_row_that_no_longer_exists_is_reported_as_missing():
    assert wd.complete_plan_materialization(-1, action="synthesized", plan_version=1) is None
    assert wd.fail_plan_materialization(-1, error="niente") is None
    assert uuid.uuid4()
