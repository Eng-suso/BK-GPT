"""PROCESS-V2-01: la chat di processo parla al consulente, non al debugger.

Difetto osservato allo STEP 3 (chat di processo). Alla domanda "a che punto
siamo?" la risposta era tecnicamente corretta e commercialmente inutilizzabile:
`ProcessUnderstanding`, "XML validato semanticamente", "readiness 0%", "fonte
registrata" con il suo id, campi del workspace. Roba da vista Evidence/Audit,
non da default della chat principale.

Qui sotto le tre parti verificabili del fix:

- il rilevatore, che dice in modo deterministico se una prosa parla da sistema;
- il prompt di scope, che porta il contratto di lingua a ogni chat e marca lo
  stato tecnico come materiale di lavoro;
- il contatore, che rende misurabile una regressione invece di lasciarla al
  prossimo consulente che la nota.

In fondo il test end-to-end vero: turno reale sulla chat di processo, con
modello e database, e la risposta consegnata deve reggere il rilevatore.
"""

from __future__ import annotations

import json
import uuid

import pytest

from backend.agents.primary_scope import build_scope_system_prompt
from backend.agents.product_language import (
    INTERNAL_VOCABULARY,
    PRODUCT_LANGUAGE_CONTRACT,
    internal_language_leaks,
)
from backend.settings import settings


# La risposta osservata, ridotta all'essenziale. Ogni riga e' una fuga diversa.
DEVELOPER_FACING_ANSWER = """
Ho aggiornato la ProcessUnderstanding del processo (process_id: proc-8f21ac).
Il BPMNSemanticModel non e' ancora stato generato, quindi l'XML non risulta
validato semanticamente e la readiness e' 0%.
Fonte registrata: src-2b9910, confidence 0.4.
"""

# La stessa verita', detta a un consulente.
CONSULTANT_FACING_ANSWER = """
Al momento abbiamo definito il perimetro generale del processo, dal fabbisogno
interno fino alla verifica della fattura, ma non sappiamo ancora come il flusso
venga realmente eseguito.

Non abbiamo evidenze sufficienti su ruoli, attivita', approvazioni, sistemi,
eccezioni, tempi e criticita': il modello e' quindi ancora vuoto e non
rappresenta un As-Is affidabile.

Il prossimo passo e' raccogliere le interviste con chi esegue il processo e
confrontare le diverse versioni, evidenziando contraddizioni e informazioni
mancanti prima di costruire il modello.
"""


# --- il rilevatore ---------------------------------------------------------

def test_the_observed_answer_is_flagged_as_developer_facing():
    leaks = internal_language_leaks(DEVELOPER_FACING_ANSWER)

    assert "internal_artifact" in leaks
    assert "internal_identifier" in leaks
    assert "readiness_score" in leaks
    assert "bpmn_xml" in leaks
    assert "raw_score" in leaks
    assert "internal_validation" in leaks


def test_the_consulting_answer_passes_clean():
    """La prosa di consulenza non e' vaga: e' la stessa verita', tradotta."""
    assert internal_language_leaks(CONSULTANT_FACING_ANSWER) == []


def test_consulting_vocabulary_is_not_treated_as_internal():
    """BPMN, As-Is, evidenza, processo restano parole del mestiere."""
    text = (
        "Il modello BPMN dell'As-Is non regge: le evidenze raccolte in due "
        "interviste si contraddicono sull'approvazione dell'ordine."
    )

    assert internal_language_leaks(text) == []


def test_the_detector_stays_quiet_on_what_the_consultant_asked_for():
    """Se il consulente chiede l'XML, dargli l'XML non e' una fuga."""
    answer = "Ecco l'XML del diagramma salvato, cosi' come sta nel modello."

    assert "bpmn_xml" in internal_language_leaks(answer)
    assert internal_language_leaks(answer, consultant_asked="mostrami l'XML") == []


def test_the_detector_reports_each_family_once_and_in_order():
    labels = [term.label for term in INTERNAL_VOCABULARY]
    leaks = internal_language_leaks(DEVELOPER_FACING_ANSWER)

    assert len(leaks) == len(set(leaks))
    assert leaks == [label for label in labels if label in leaks]


def test_an_empty_answer_has_nothing_to_leak():
    assert internal_language_leaks("") == []


# --- il contratto nel prompt ----------------------------------------------

def test_every_scope_carries_the_product_language_contract():
    """Il difetto e' nato nel processo, ma la regola non e' del processo."""
    for scope_type in ("consultant", "project", "process", "canvas"):
        prompt = build_scope_system_prompt({"scope_type": scope_type, "project_id": "p-1"})
        assert PRODUCT_LANGUAGE_CONTRACT in prompt


def test_the_contract_names_the_shape_of_a_status_answer():
    assert "perimetro" in PRODUCT_LANGUAGE_CONTRACT
    assert "As-Is affidabile" in PRODUCT_LANGUAGE_CONTRACT
    assert "prossimo passo" in PRODUCT_LANGUAGE_CONTRACT


def test_the_contract_keeps_the_technical_detail_available_on_request():
    """Un default di linguaggio, non una censura: il dettaglio resta ottenibile."""
    assert "se il consulente chiede il dettaglio tecnico" in PRODUCT_LANGUAGE_CONTRACT


def test_technical_state_is_announced_as_working_material():
    prompt = build_scope_system_prompt(
        {
            "scope_type": "process",
            "project_id": "p-1",
            "process_id": "pr-1",
            "readiness_score": 0,
        }
    )

    assert "Stato di lavoro interno" in prompt
    assert "readiness_score: 0" in prompt
    assert prompt.index("Stato di lavoro interno") < prompt.index("readiness_score: 0")


def test_a_scope_without_technical_state_gets_no_working_material_marker():
    prompt = build_scope_system_prompt({"scope_type": "process", "process_id": "pr-1"})

    assert "Stato di lavoro interno" not in prompt


# --- il contatore ----------------------------------------------------------

def test_a_leaking_answer_is_counted_as_a_degradation():
    from backend.api.routes.chat import record_product_language
    from backend.services import degradation_counters

    degradation_counters.reset()
    leaks = record_product_language(
        answer=DEVELOPER_FACING_ANSWER,
        asked="a che punto siamo?",
        scope_type="process",
    )

    assert leaks
    assert degradation_counters.snapshot()["product_language:internal_leak"] == 1


def test_a_clean_answer_is_not_counted():
    from backend.api.routes.chat import record_product_language
    from backend.services import degradation_counters

    degradation_counters.reset()
    leaks = record_product_language(
        answer=CONSULTANT_FACING_ANSWER,
        asked="a che punto siamo?",
        scope_type="process",
    )

    assert leaks == []
    assert degradation_counters.snapshot() == {}


# --- E2E: turno vero sulla chat di processo --------------------------------

_E2E_NEEDED = (settings.workspace_database_url, settings.openai_api_key)

STATUS_QUESTION = "A che punto siamo con questo processo?"
PERIMETER = "Dal fabbisogno interno alla verifica della fattura fornitore."
PROCESS_NAME = "Gestione acquisto materiali indiretti e servizi"


def _thin_understanding() -> dict:
    """Un As-Is appena abbozzato: due passi, nessuna approvazione, molti buchi.

    E' la forma che genera lo stato peggiore per il linguaggio: la review esiste,
    quindi il prompt porta ProcessUnderstanding, modello semantico, diagnostica,
    quality report e una readiness bassa. Prima del fix era esattamente questo
    elenco che il consulente si vedeva restituire.
    """
    from backend.process_understanding import ProcessActor, ProcessStep, ProcessUnderstanding

    return ProcessUnderstanding(
        title=PROCESS_NAME,
        actors=[ProcessActor(id="Richiedente", label="Richiedente", kind="role")],
        steps=[
            ProcessStep(id="Task_Need", label="Emerge il fabbisogno", actor_ids=["Richiedente"]),
            ProcessStep(id="Task_Invoice", label="Verifica fattura", actor_ids=["Richiedente"]),
        ],
        sequence=["Task_Need", "Task_Invoice"],
    ).model_dump(mode="json")


@pytest.mark.skipif(
    not all(_E2E_NEEDED), reason="serve WORKSPACE_DATABASE_URL + OPENAI_API_KEY"
)
def test_the_process_chat_answers_a_status_question_in_consulting_language():
    """Il test che vale: stato interno pieno, domanda di stato, prosa reale.

    Il processo ha perimetro e una review appena abbozzata, quindi il turno gira
    con readiness bassa, informazioni mancanti, diagnostica e modello semantico
    tutti nel prompt: e' la condizione in cui la chat rispondeva elencandoli. Se
    il contratto di lingua regge solo sulla carta, si rompe qui.

    I record restano sul tenant di default e non su uno isolato: l'agente gira
    in un thread proprio, che non eredita la contextvar del tenant, quindi un
    tenant di test renderebbe invisibile al turno il processo appena creato.
    """
    from fastapi.testclient import TestClient

    from backend import workspace_database as wd
    from backend.app import app
    from backend.graphs.project.tools import create_project_process
    from backend.services import degradation_counters

    client_record = wd.create_client(name=f"Esaote {uuid.uuid4().hex[:6]}")
    project = wd.create_project(
        client_id=client_record["id"], name=f"Acquisti {uuid.uuid4().hex[:6]}"
    )
    created = json.loads(
        create_project_process.invoke(
            {
                "project_id": project["id"],
                "name": PROCESS_NAME,
                "scope_note": PERIMETER,
            }
        ).split("\n", 1)[1]
    )
    process_id = created["payload"]["process_id"]
    review = wd.prepare_bpmn_review(
        bpmn_model_id=created["payload"]["bpmn_model_id"],
        process_description=PERIMETER,
        process_understanding=_thin_understanding(),
    )
    assert review["missing_information"], "il seed deve lasciare buchi dichiarati"
    scope = {"type": "process", "project_id": project["id"], "process_id": process_id}

    degradation_counters.reset()

    with TestClient(app) as http:
        session = http.post(
            "/v1/consultant-chat/sessions",
            json={"model_name": settings.openai_model, "scope": scope},
        )
        assert session.status_code == 200, session.text
        thread_id = session.json()["thread_id"]

        answered = http.post(
            f"/v1/consultant-chat/sessions/{thread_id}/messages",
            json={
                "message": STATUS_QUESTION,
                "model_name": settings.openai_model,
                "scope": scope,
                "mode": "plan",
            },
        )

    assert answered.status_code == 200, answered.text
    reply = answered.json()["message"]

    assert reply.strip(), "la chat non ha risposto"
    assert internal_language_leaks(reply, consultant_asked=STATUS_QUESTION) == [], reply
    assert "product_language:internal_leak" not in degradation_counters.snapshot()
