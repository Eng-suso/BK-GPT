"""Caso Esaote, riprodotto: dalle interviste al canvas, con il revisore nel loop.

Il 2026-09-17 il processo «Gestione acquisto materiali indiretti e servizi» aveva
tre interviste agli atti e un piano V1 preparato dal titolo, prima che le
interviste arrivassero: zero attori, zero attivita', `evidence_source_set_id`
nullo, nessuna riga nella coda di materializzazione. «Genera il BPMN» ha
risposto sei volte «ho disegnato la bozza e l'ho riletta» davanti a un canvas
con un inizio e una fine, e la chat del canvas ha detto al consulente che le
evidenze non bastavano.

Qui lo stesso stato si ricostruisce e si attraversa per intero:

1. **il piano vecchio non si disegna**: il comando lo riconosce, lo ricostruisce
   sulle interviste o rifiuta con la causa - mai start -> end chiamato bozza;
2. **il revisore e' nel loop**: il canvas salvato si confronta con il piano, il
   documento di review con il piano, il piano con le fonti intere, e un agente
   legge ogni fonte cercando cio' che il piano non ha. Un rilievo con una
   citazione inventata si scarta; un rilievo verificato ricostruisce il piano,
   e il disegno si rifa' e si riverifica;
3. **nessun percorso lascia il piano indietro**: la chat del canvas lo
   ricostruisce prima di ragionare, lo sweep del worker rimette in coda i piani
   che nessuna scrittura aveva segnalato.

L'estrattore e il revisore sono sostituiti da due fake deterministici: qui si
verifica l'harness - cosa il runtime accetta, rifiuta, ripara e dichiara - non
la bravura del modello. La stessa catena con il modello vero e' in
`tests/evals/test_conformance_eval.py`, gated.

Servono la DSN workspace e quelle canonical (`cd ops && docker compose up -d`).
"""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET

import pytest

from backend.settings import settings

if not all((settings.workspace_database_url, settings.canonical_database_url)):
    pytest.skip(
        "servono WORKSPACE_DATABASE_URL e le DSN canonical",
        allow_module_level=True,
    )

from sqlalchemy import text  # noqa: E402

from backend import workspace_database as wd  # noqa: E402
from backend.agents.conformance_audit import (  # noqa: E402
    AuditedContradiction,
    AuditedFact,
    SourceAuditRequest,
    SourceAuditVerdict,
    flow_signature,
)
from backend.agents.process_snapshot import build_process_snapshot  # noqa: E402
from backend.bpmn import BPMNSemanticModel, semantic_model_to_bpmn_xml  # noqa: E402
from backend.process_understanding import (  # noqa: E402
    ProcessUnderstanding,
    ProcessUnderstandingResult,
    ProcessUnknown,
    render_process_review,
)
from backend.security import get_current_tenant_id  # noqa: E402
from backend.workspace_services.bpmn_draft import (  # noqa: E402
    generate_bpmn_draft,
    generate_verified_bpmn_draft,
)

from tests.test_process_canvas_handoff_e2e import (  # noqa: E402
    INTERVIEWS,
    _bind_process_chat,
    _save_interviews,
    _supported_understanding,
    empty_process,  # noqa: F401 - fixture
)

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
TASK_TAGS = {"task", "userTask", "manualTask", "serviceTask", "sendTask", "receiveTask"}

# Le parole di Paolo che il primo piano non rappresenta: e' il fatto che il
# revisore deve trovare, citare, e far rientrare nel piano.
PAOLO_URGENT_QUOTE = "chiamo direttamente il fornitore e faccio consegnare"
REVIEWER_NOTE_MARKER = "Verifica di conformita' sul piano precedente"


@pytest.fixture(autouse=True)
def _no_live_model(monkeypatch):
    """Nessun modello vero: estrattore e revisore sono i fake di questo modulo."""
    monkeypatch.setattr(settings, "openai_api_key", None)


# --- lo stato Esaote -----------------------------------------------------


def _legacy_empty_plan(scope: dict) -> None:
    """Il piano V1 com'era: preparato dal titolo, prima delle interviste.

    Nessuna evidenza agli atti in quel momento, quindi nessuna guardia lo
    ferma; nessun set di fonti dichiarato, perche' la colonna allora non si
    scriveva.
    """
    empty = ProcessUnderstanding(
        title="Gestione acquisto materiali indiretti e servizi",
        scope="Da definire: le evidenze disponibili indicano esclusivamente il titolo del processo.",
        unknowns=[
            ProcessUnknown(
                question="Quale attivita' viene eseguita per prima dopo l'avvio della richiesta?",
                affects="Percorso principale",
                severity="blocking",
            )
        ],
    )
    wd.prepare_bpmn_review(
        bpmn_model_id=scope["bpmn_model_id"],
        process_description=(
            "Generare il BPMN del processo esclusivamente a partire dalle evidenze "
            "disponibili nel workspace."
        ),
        process_understanding=empty.model_dump(mode="json"),
    )


def _forget_queue(scope: dict) -> None:
    """Le fonti di prima della coda: nessuna riga di materializzazione."""
    with wd.workspace_connection() as session:
        session.execute(
            text(
                "DELETE FROM workspace_plan_materializations "
                "WHERE tenant_id = :tenant AND process_id = :process"
            ),
            {"tenant": get_current_tenant_id(), "process": scope["process_id"]},
        )


@pytest.fixture()
def esaote_state(empty_process):  # noqa: F811 - fixture di modulo
    """Piano V1 vuoto e vecchio, tre interviste agli atti, coda vuota."""
    _legacy_empty_plan(empty_process)
    _save_interviews(empty_process)
    _forget_queue(empty_process)

    snapshot = build_process_snapshot(empty_process["process_id"])
    assert snapshot is not None
    assert snapshot.evidence_count == len(INTERVIEWS)
    assert snapshot.has_semantic_model and not snapshot.plan_is_current, (
        "lo stato di partenza deve essere quello del caso reale: un piano che c'e' "
        "ma non e' costruito sulle interviste"
    )
    assert not (snapshot.process_understanding or {}).get("steps")
    return empty_process


# --- i fake: estrattore e revisore ---------------------------------------


def _grounded_plan(*, include_urgent_path: bool) -> ProcessUnderstanding:
    """Il piano che le tre interviste reggono, con le parole delle fonti.

    Senza il percorso urgente e' il piano di un estrattore che ha perso il
    passaggio di Paolo: formalmente valido, e non fedele alle fonti.
    """
    plan = _supported_understanding()
    evidence = {
        "ufficio_tecnico": "Laura Conti, Ufficio Tecnico",
        "acquisti": "Francesca Neri, Ufficio Acquisti",
        "manutenzione": "Paolo Marchetti, Manutenzione",
        "apri_richiesta": "apro una richiesta di acquisto e la mando ad Acquisti",
        "verifica_autorizzazione": "verifico che ci sia l'autorizzazione del responsabile",
        "firma_direttore": "Sopra i cinquemila euro serve sempre la firma del direttore acquisti",
        "crea_ordine": "creo l'ordine e lo invio al fornitore",
        "chiama_fornitore": PAOLO_URGENT_QUOTE,
        "soglia_firma": "Sopra i cinquemila euro serve sempre la firma",
    }
    for actor in plan.actors:
        actor.source_evidence = [evidence[actor.id]]
    for step in plan.steps:
        step.source_evidence = [evidence[step.id]]
    for decision in plan.decisions:
        decision.source_evidence = [evidence[decision.id]]
    for exception in plan.exceptions:
        exception.label = "Linea ferma"
        exception.trigger = "la linea e' ferma"
        exception.handling = "chiamo direttamente il fornitore"

    if not include_urgent_path:
        plan.actors = [item for item in plan.actors if item.id != "manutenzione"]
        plan.steps = [item for item in plan.steps if item.id != "chiama_fornitore"]
        plan.exceptions = []
        plan.flow_edges = [item for item in plan.flow_edges if item.id != "linea_ferma_to_chiamata"]
        plan.unknowns = []
    return plan


class FakeExtractor:
    """L'estrattore per fonte: perde il percorso urgente finche' nessuno glielo segnala."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, title: str, source_text: str, *, with_quality_report: bool = True):
        self.calls.append(source_text)
        noted = REVIEWER_NOTE_MARKER in source_text and PAOLO_URGENT_QUOTE in source_text
        return ProcessUnderstandingResult(
            status="success",
            process=_grounded_plan(include_urgent_path=noted),
        )

    @property
    def notes_received(self) -> list[str]:
        return [call for call in self.calls if REVIEWER_NOTE_MARKER in call]


class FakeAuditor:
    """Il revisore: trova il passaggio di Paolo mancante, e al primo giro inventa una prova."""

    def __init__(self, *, contradict: str | None = None) -> None:
        self.requests: list[SourceAuditRequest] = []
        self.contradict = contradict

    def __call__(self, request: SourceAuditRequest) -> SourceAuditVerdict:
        self.requests.append(request)
        refs = {str(item["ref"]) for item in request.plan_elements}
        verdict = SourceAuditVerdict()
        if "Paolo" in request.source_name and "steps:chiama_fornitore" not in refs:
            verdict.missing_facts = [
                AuditedFact(
                    kind="activity",
                    statement="Con la linea ferma Manutenzione chiama direttamente il fornitore",
                    quote=PAOLO_URGENT_QUOTE,
                ),
                # Una prova che la fonte non contiene: il runtime deve scartarla.
                AuditedFact(
                    kind="rule",
                    statement="Il fornitore emette sempre una nota di credito",
                    quote="il fornitore emette sempre una nota di credito entro trenta giorni",
                ),
            ]
        if self.contradict and "Francesca" in request.source_name:
            verdict.contradicted_elements = [
                AuditedContradiction(
                    element_ref=self.contradict,
                    quote="verifico che ci sia l'autorizzazione del responsabile",
                    explanation="la fonte colloca la verifica prima dell'ordine, non dopo",
                ),
                # Un riferimento che il piano non ha: scartato.
                AuditedContradiction(
                    element_ref="steps:non_esiste",
                    quote="creo l'ordine e lo invio al fornitore",
                    explanation="riferimento inventato",
                ),
            ]
        return verdict


@pytest.fixture()
def extractor(monkeypatch) -> FakeExtractor:
    fake = FakeExtractor()
    monkeypatch.setattr("backend.agents.process_synthesis.build_process_understanding", fake)
    return fake


@pytest.fixture()
def auditor(monkeypatch) -> FakeAuditor:
    fake = FakeAuditor()
    # Il revisore "del modello configurato" e' quello che API e chat usano: si
    # sostituisce li', cosi' il test attraversa il percorso reale.
    monkeypatch.setattr("backend.agents.conformance_audit.llm_source_auditor", lambda: fake)
    return fake


def _canvas_tags(xml: str) -> list[str]:
    return [element.tag.rsplit("}", 1)[-1] for element in ET.fromstring(xml).iter()]


def _canvas_task_names(xml: str) -> list[str]:
    return [
        str(element.attrib.get("name") or "")
        for element in ET.fromstring(xml).iter()
        if element.tag.rsplit("}", 1)[-1] in TASK_TAGS
    ]


def _draft_versions(bpmn_model_id: str) -> list[dict]:
    return [item for item in wd.list_bpmn_versions(bpmn_model_id) if item["source"] == "bpmn_draft_command"]


# --- 1. il piano vecchio non si disegna ----------------------------------


def test_a_stale_plan_is_refused_when_rebuilding_is_not_allowed(esaote_state):
    """Senza il ramo lento, il comando rifiuta con la causa e mette in coda il lavoro."""
    with _bind_process_chat(esaote_state["project_id"], esaote_state["process_id"]):
        result = generate_bpmn_draft(esaote_state["process_id"], synthesize_missing_plan=False)

    assert result.status == "failed"
    assert result.reason_code == "plan_stale"
    assert result.metrics["llm_calls"] == 0
    assert _draft_versions(esaote_state["bpmn_model_id"]) == [], (
        "un piano che non descrive le interviste non deve arrivare sul canvas"
    )
    queued = wd.plan_materialization_for(esaote_state["process_id"])
    assert queued is not None and queued["status"] == "pending"


def test_a_failed_rebuild_is_a_technical_failure_not_a_drawing(esaote_state):
    """Estrattore non disponibile: guasto dichiarato, nessun start -> end sul canvas."""
    with _bind_process_chat(esaote_state["project_id"], esaote_state["process_id"]):
        result = generate_bpmn_draft(esaote_state["process_id"])

    assert result.status == "failed"
    assert result.reason_code == "plan_synthesis_failed"
    assert any("OPENAI_API_KEY" in item for item in result.issues)
    assert _draft_versions(esaote_state["bpmn_model_id"]) == []


def test_an_empty_plan_on_current_sources_is_not_drawn(esaote_state, monkeypatch):
    """Un piano senza attivita' non diventa un inizio e una fine chiamati bozza."""
    from backend.graphs.process.nodes import load_evidence_ledger

    ledger = load_evidence_ledger(esaote_state["project_id"], esaote_state["process_id"])
    with wd.workspace_connection() as session:
        session.execute(
            text(
                "UPDATE workspace_bpmn_reviews SET evidence_source_set_id = :set "
                "WHERE bpmn_model_id = :model AND tenant_id = :tenant"
            ),
            {
                "set": ledger["source_set_id"],
                "model": esaote_state["bpmn_model_id"],
                "tenant": get_current_tenant_id(),
            },
        )

    with _bind_process_chat(esaote_state["project_id"], esaote_state["process_id"]):
        result = generate_bpmn_draft(esaote_state["process_id"])

    assert result.status == "failed"
    assert result.reason_code == "plan_ignores_evidence"
    assert _draft_versions(esaote_state["bpmn_model_id"]) == []


# --- 2. il revisore nel loop ---------------------------------------------


def test_esaote_generate_from_the_endpoint_rebuilds_verifies_and_repairs(
    esaote_state, extractor, auditor
):
    """Il bottone «Genera BPMN»: dal piano vuoto a un canvas conforme alle interviste."""
    from fastapi.testclient import TestClient

    from backend.app import app

    headers = {"X-DeliR-Tenant-Id": get_current_tenant_id()}
    with TestClient(app) as client:
        response = client.post(
            f"/v1/workspace/processes/{esaote_state['process_id']}/bpmn-draft",
            headers=headers,
        )
        status = client.get(
            f"/v1/workspace/processes/{esaote_state['process_id']}/conformance",
            headers=headers,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "drafted", body
    report = body["conformance"]
    assert report["verdict"] == "conformant", report["findings"]
    assert report["llm_audit"] == "done"
    assert report["sources_audited"] == len(INTERVIEWS)
    assert body["metrics"]["conformance_repairs"] == 1

    # Il loop: il primo piano perdeva Paolo, il revisore l'ha citato, la prova
    # inventata e' stata scartata, e la nota verificata e' arrivata
    # all'estrazione della fonte giusta - e solo a quella.
    assert len(extractor.notes_received) == 1
    assert PAOLO_URGENT_QUOTE in extractor.notes_received[0]
    assert "nota di credito" not in extractor.notes_received[0]
    first_round = [item for item in auditor.requests if "steps:chiama_fornitore" not in {e["ref"] for e in item.plan_elements}]
    assert first_round, "il revisore deve aver visto il piano senza il percorso urgente"

    # Il piano adesso e' quello delle interviste.
    snapshot = build_process_snapshot(esaote_state["process_id"])
    assert snapshot is not None and snapshot.plan_is_current
    assert snapshot.version >= 3, "V1 vuoto -> sintesi -> riparazione"
    assert snapshot.provenance is not None
    assert snapshot.provenance.awaiting_confirmation == [], [
        (item.label, item.status) for item in snapshot.provenance.awaiting_confirmation
    ]
    assert snapshot.provenance.unused_sources == []

    # Il canvas salvato coincide nodo per nodo con cio' che il piano compila.
    saved = wd.get_bpmn_model(esaote_state["bpmn_model_id"])
    expected = semantic_model_to_bpmn_xml(BPMNSemanticModel.model_validate(snapshot.bpmn_semantic_model))
    assert flow_signature(saved["xml"]) == flow_signature(expected)
    names = " | ".join(_canvas_task_names(saved["xml"])).casefold()
    for label in ("richiesta", "autorizzazione", "ordine", "chiama direttamente il fornitore"):
        assert label in names, names
    assert _canvas_tags(saved["xml"]).count("exclusiveGateway") >= 1

    # Il documento che il consulente legge nella review e' quello del piano.
    review = wd.get_bpmn_review(esaote_state["bpmn_model_id"], include_approved=True)
    assert " ".join(review["bpmn_brief"].split()) == " ".join(
        render_process_review(ProcessUnderstanding.model_validate(snapshot.process_understanding)).split()
    )

    # Il rapporto e' registrato e vale per cio' che si vede adesso.
    assert status.status_code == 200, status.text
    assert status.json()["is_current"] is True
    assert status.json()["report"]["verdict"] == "conformant"


def test_the_canvas_chat_rebuilds_the_plan_before_it_reasons(esaote_state, extractor, auditor):
    """La chat del canvas: piano ricostruito prima del router, bozza raccontata con i numeri."""
    from backend.graphs.canvas_edit.graph import ensure_current_plan, generate_canvas_draft

    state = {
        "process_id": esaote_state["process_id"],
        "project_id": esaote_state["project_id"],
        "bpmn_model_id": esaote_state["bpmn_model_id"],
        "canvas_route": "construction",
    }
    with _bind_process_chat(esaote_state["project_id"], esaote_state["process_id"]):
        refreshed = ensure_current_plan(state)
        assert refreshed["plan_refresh"]["action"] == "synthesized", refreshed
        assert build_process_snapshot(esaote_state["process_id"]).plan_is_current

        # Un secondo turno sullo stesso stato non ricostruisce niente.
        assert ensure_current_plan(state) == {}

        drafted = generate_canvas_draft(state)

    message = drafted["messages"][0].content
    assert drafted["canvas_run_status"] == "done", message
    assert "attivita'" in message and "0 attivita'" not in message
    assert "verifica di conformita' e' passata" in message
    assert drafted["validation_report"]["conformance"]["verdict"] == "conformant"


def test_a_contradiction_that_repair_cannot_close_reaches_the_consultant(
    esaote_state, extractor
):
    """La bozza si consegna, ma non si racconta conforme: il rilievo arriva al consulente."""
    auditor = FakeAuditor(contradict="steps:crea_ordine")

    with _bind_process_chat(esaote_state["project_id"], esaote_state["process_id"]):
        result = generate_verified_bpmn_draft(esaote_state["process_id"], auditor=auditor)

    assert result.status == "drafted"
    assert result.conformance is not None
    assert result.conformance.verdict == "not_conformant"
    contradictions = [
        item for item in result.conformance.findings if item.layer == "source_contradiction"
    ]
    assert [item.element_ref for item in contradictions] == ["steps:crea_ordine"]
    assert result.conformance.discarded_findings >= 1, "il riferimento inventato va scartato"
    assert result.conformance_repairs == 1, "la riparazione si tenta una volta, non all'infinito"
    assert any("smentisce" in item for item in result.pending_verification)


def test_without_a_reviewer_the_draft_is_never_declared_conformant(esaote_state, extractor):
    """Nessun revisore disponibile: `incomplete`, detto, mai `conformant`."""
    with _bind_process_chat(esaote_state["project_id"], esaote_state["process_id"]):
        result = generate_verified_bpmn_draft(esaote_state["process_id"], auditor=None)

    assert result.status == "drafted"
    assert result.conformance is not None
    # Il piano estratto senza revisore perde Paolo: lo dice la provenance.
    assert result.conformance.verdict == "not_conformant"
    assert result.conformance.llm_audit == "skipped"
    assert any(item.code == "source_unused" for item in result.conformance.findings)


def test_a_canvas_edited_after_the_draft_is_no_longer_conformant(esaote_state, extractor, auditor):
    """Il revisore confronta il canvas salvato, non quello che il comando crede di aver scritto."""
    from backend.agents.conformance_audit import audit_process_conformance

    with _bind_process_chat(esaote_state["project_id"], esaote_state["process_id"]):
        result = generate_verified_bpmn_draft(esaote_state["process_id"], auditor=auditor)
    assert result.conformance is not None and result.conformance.verdict == "conformant"

    xml = wd.get_bpmn_model(esaote_state["bpmn_model_id"])["xml"]
    root = ET.fromstring(xml)
    task = next(element for element in root.iter() if element.tag.rsplit("}", 1)[-1] in TASK_TAGS)
    renamed_from = task.attrib["name"]
    task.set("name", "Passaggio aggiunto a mano")
    wd.update_bpmn_model(esaote_state["bpmn_model_id"], ET.tostring(root, encoding="unicode"))

    report = audit_process_conformance(esaote_state["process_id"], auditor=auditor)

    assert report is not None and report.verdict == "not_conformant"
    differs = [item for item in report.findings if item.code == "canvas_element_differs"]
    assert differs and renamed_from in differs[0].message


# --- 3. nessun percorso lascia il piano indietro -------------------------


def test_the_sweep_requeues_a_plan_that_no_write_had_flagged(esaote_state, extractor):
    """Fonti di prima della coda: lo sweep le trova, il worker ricostruisce il piano."""
    from backend.workers import plan_worker

    assert wd.plan_materialization_for(esaote_state["process_id"]) is None

    queued = wd.enqueue_stale_plan_materializations(only_tenant_id=get_current_tenant_id())

    mine = [row for row in queued if row["process_id"] == esaote_state["process_id"]]
    assert len(mine) == 1
    assert plan_worker._work_one(mine[0]) is True

    snapshot = build_process_snapshot(esaote_state["process_id"])
    assert snapshot is not None and snapshot.plan_is_current
    assert (snapshot.process_understanding or {}).get("steps")

    # Allineato: un secondo sweep non rimette in coda lo stesso processo.
    again = wd.enqueue_stale_plan_materializations(only_tenant_id=get_current_tenant_id())
    assert all(row["process_id"] != esaote_state["process_id"] for row in again)


def test_a_project_level_source_queues_every_process_of_the_project(empty_process):  # noqa: F811
    """Una fonte di progetto vale per tutti i processi: tutti i loro piani vanno rifatti."""
    other = wd.create_process(project_id=empty_process["project_id"], name=f"Ciclo attivo {uuid.uuid4().hex[:4]}")
    _forget_queue(empty_process)

    wd.create_project_source(
        project_id=empty_process["project_id"],
        name="Procedura acquisti aziendale",
        type="Documento",
        meta="Procedura valida per tutti i reparti.",
    )

    assert wd.plan_materialization_for(empty_process["process_id"]) is not None
    assert wd.plan_materialization_for(other["id"]) is not None
