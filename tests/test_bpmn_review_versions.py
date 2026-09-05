"""La review BPMN e' versionata: un piano si itera, non si sovrascrive.

Prima esisteva un solo slot per `bpmn_model_id`: ogni `prepare` cancellava il
piano precedente, quindi non c'era modo di confrontare una revisione con cio'
che aveva sostituito, e l'unica modifica possibile era sul markdown *derivato* -
che non rientrava nella generazione, quindi la correzione veniva ignorata
all'approvazione successiva.
"""

from __future__ import annotations

import uuid

import pytest

from backend.settings import settings

if not settings.workspace_database_url:
    pytest.skip("serve WORKSPACE_DATABASE_URL", allow_module_level=True)

from backend import workspace_database as wd  # noqa: E402
from backend.process_understanding import (  # noqa: E402
    ProcessActor,
    ProcessDecision,
    ProcessStep,
    ProcessUnderstanding,
    ProcessUnknown,
    ProcessUnknownOption,
)
from backend.security import reset_current_tenant_id, set_current_tenant_id  # noqa: E402


def _understanding(title: str = "Order to Cash", extra_step: bool = False) -> dict:
    steps = [
        ProcessStep(id="Task_Receive", label="Ricevi ordine", actor_ids=["Sales"]),
        ProcessStep(id="Task_Check", label="Verifica credito", actor_ids=["Finance"]),
    ]
    sequence = ["Task_Receive", "Task_Check"]
    if extra_step:
        steps.append(ProcessStep(id="Task_Ship", label="Spedisci", actor_ids=["Ops"]))
        sequence.append("Task_Ship")

    return ProcessUnderstanding(
        title=title,
        actors=[
            ProcessActor(id="Sales", label="Sales", kind="team"),
            ProcessActor(id="Finance", label="Finance", kind="team"),
            ProcessActor(id="Ops", label="Ops", kind="team"),
        ],
        steps=steps,
        sequence=sequence,
        decisions=[
            ProcessDecision(id="Gateway_Credit", label="Credito approvato?", outcomes=["Si", "No"])
        ],
    ).model_dump(mode="json")


@pytest.fixture(autouse=True)
def _deterministic_quality_report(monkeypatch):
    """Niente valutatore LLM: qui si testa la versionatura, non la qualita'.

    `build_bpmn_review_draft` chiama l'LLM per il quality report quando una
    chiave OpenAI e' configurata. Su CI la chiave e' vuota e il codice prende il
    ramo deterministico: senza questo, questi test girerebbero su due percorsi
    diversi in locale e su GitHub - e in locale ci mettevano oltre due minuti
    per sei casi che non hanno nulla a che vedere con la valutazione.
    """
    monkeypatch.setattr(settings, "openai_api_key", None)


@pytest.fixture()
def review_model():
    """A real workspace process with its BPMN model, on an isolated tenant."""
    token = set_current_tenant_id(f"t-review-{uuid.uuid4().hex[:8]}")
    try:
        client = wd.create_client(name=f"Acme Review {uuid.uuid4().hex[:6]}")
        project = wd.create_project(client_id=client["id"], name="Mapping review")
        process = wd.create_process(project_id=project["id"], name="Order to Cash review")
        yield process["bpmn_model_id"]
    finally:
        reset_current_tenant_id(token)


def test_preparing_again_adds_a_version_instead_of_overwriting(review_model):
    first = wd.prepare_bpmn_review(
        bpmn_model_id=review_model,
        process_description="Sales riceve l'ordine, Finance verifica il credito.",
        process_understanding=_understanding(),
    )
    assert first["version"] == 1

    second = wd.prepare_bpmn_review(
        bpmn_model_id=review_model,
        process_description="Sales riceve l'ordine, Finance verifica, Ops spedisce.",
        process_understanding=_understanding(extra_step=True),
    )
    assert second["version"] == 2

    versions = wd.list_bpmn_review_versions(review_model)
    assert [item["version"] for item in versions] == [2, 1], "storico piu' recente prima"

    # Il piano sostituito resta leggibile e confrontabile: e' il punto della
    # versionatura, non solo un contatore che sale.
    previous = wd.get_bpmn_review_version(review_model, 1)
    assert "Ops" not in {
        actor["label"] for actor in previous["process_understanding"]["actors"]
    } or "Task_Ship" not in {
        step["id"] for step in previous["process_understanding"]["steps"]
    }
    assert "Task_Ship" in {
        step["id"] for step in versions[0]["process_understanding"]["steps"]
    }


def test_revising_the_understanding_regenerates_what_the_canvas_is_built_from(review_model):
    wd.prepare_bpmn_review(
        bpmn_model_id=review_model,
        process_description="Sales riceve l'ordine, Finance verifica il credito.",
        process_understanding=_understanding(),
    )

    revised = wd.revise_bpmn_review(
        review_model,
        process_understanding=_understanding(extra_step=True),
        change_summary="Aggiunta la spedizione",
    )

    assert revised["version"] == 2
    # Non solo il testo: il semantic model da cui nasce l'XML ha il passo nuovo.
    node_names = {node["name"] for node in revised["bpmn_semantic_model"]["flowNodes"]}
    assert "Spedisci" in node_names
    assert "Spedisci" in revised["bpmn_brief"]

    stored = wd.get_bpmn_review_version(review_model, 2)
    assert stored["change_summary"] == "Aggiunta la spedizione"
    assert stored["source"] == "revision"


def test_editing_only_the_brief_is_recorded_but_does_not_touch_the_model(review_model):
    prepared = wd.prepare_bpmn_review(
        bpmn_model_id=review_model,
        process_description="Sales riceve l'ordine, Finance verifica il credito.",
        process_understanding=_understanding(),
    )

    edited = wd.update_bpmn_review_brief(review_model, "# Piano rivisto a mano\n\nTesto.")

    assert edited["version"] == 2
    assert edited["bpmn_brief"].startswith("# Piano rivisto a mano")
    # Il brief e' la resa leggibile: da solo non cambia cio' che verrebbe generato.
    assert edited["bpmn_semantic_model"] == prepared["bpmn_semantic_model"]
    assert wd.get_bpmn_review_version(review_model, 2)["source"] == "brief_edit"


def test_approval_marks_the_version_it_generated_from(review_model):
    wd.prepare_bpmn_review(
        bpmn_model_id=review_model,
        process_description="Sales riceve l'ordine, Finance verifica il credito.",
        process_understanding=_understanding(),
    )

    result = wd.approve_bpmn_review(review_model, override=True)

    assert result["review"]["status"] == "approved"
    approved_version = result["review"]["version"]
    stored = wd.get_bpmn_review_version(review_model, approved_version)
    assert stored["status"] == "approved"

    # La versione del canvas dice da quale piano e' nata.
    latest_canvas = wd.list_bpmn_versions(review_model)[0]
    assert f"v{approved_version}" in latest_canvas["change_summary"]

    # Approvare non duplica la versione: cambia il suo stato.
    assert [item["version"] for item in wd.list_bpmn_review_versions(review_model)] == [1]


def test_revising_an_approved_review_reopens_it(review_model):
    wd.prepare_bpmn_review(
        bpmn_model_id=review_model,
        process_description="Sales riceve l'ordine, Finance verifica il credito.",
        process_understanding=_understanding(),
    )
    wd.approve_bpmn_review(review_model, override=True)

    revised = wd.revise_bpmn_review(review_model, process_understanding=_understanding(extra_step=True))

    # Un piano approvato che viene corretto e' una nuova proposta, non un piano
    # ancora approvato: il canvas salvato resta quello di prima finche' non si
    # approva di nuovo.
    assert revised["status"] == "pending"
    assert wd.get_bpmn_review(review_model) is not None


def test_versions_are_scoped_to_their_tenant(review_model):
    wd.prepare_bpmn_review(
        bpmn_model_id=review_model,
        process_description="Sales riceve l'ordine, Finance verifica il credito.",
        process_understanding=_understanding(),
    )

    other = set_current_tenant_id(f"t-other-{uuid.uuid4().hex[:8]}")
    try:
        assert wd.list_bpmn_review_versions(review_model) == []
        assert wd.get_bpmn_review_version(review_model, 1) is None
    finally:
        reset_current_tenant_id(other)


def _understanding_with_open_question() -> dict:
    """A plan that knows what it does not know, and what the answers could be."""
    understanding = ProcessUnderstanding.model_validate(_understanding())
    understanding.unknowns = [
        ProcessUnknown(
            question="Chi approva un ordine oltre 10k?",
            affects="decision",
            severity="blocking",
            options=[
                ProcessUnknownOption(
                    label="Direzione amministrativa",
                    implication="Aggiunge un passaggio di approvazione dopo la verifica credito",
                ),
                ProcessUnknownOption(
                    label="Il responsabile commerciale",
                    implication="L'approvazione resta dentro Sales, senza nuovo attore",
                ),
            ],
        )
    ]
    return understanding.model_dump(mode="json")


def test_open_questions_carry_the_alternatives_the_agent_proposed(review_model):
    review = wd.prepare_bpmn_review(
        bpmn_model_id=review_model,
        process_description="Sales riceve l'ordine, Finance verifica il credito.",
        process_understanding=_understanding_with_open_question(),
    )

    # `missing_information` resta la lista piatta leggibile; `open_questions` e'
    # la stessa lacuna in una forma su cui si puo' agire.
    assert any("10k" in item for item in review["missing_information"])

    question = next(q for q in review["open_questions"] if "10k" in q["question"])
    assert question["severity"] == "blocking"
    assert [option["label"] for option in question["options"]] == [
        "Direzione amministrativa",
        "Il responsabile commerciale",
    ]
    assert question["options"][0]["implication"]
    assert question["answer"] is None


def test_answering_a_question_records_the_decision_as_a_new_version(review_model):
    review = wd.prepare_bpmn_review(
        bpmn_model_id=review_model,
        process_description="Sales riceve l'ordine, Finance verifica il credito.",
        process_understanding=_understanding_with_open_question(),
    )
    question = review["open_questions"][0]

    answered = wd.answer_bpmn_review_question(
        review_model,
        question=question["question"],
        answer="Direzione amministrativa",
    )

    assert answered["version"] == review["version"] + 1
    stored = next(q for q in answered["open_questions"] if q["question_id"] == question["question_id"])
    assert stored["answer"] == "Direzione amministrativa"
    assert stored["answered_at"]
    assert wd.get_bpmn_review_version(review_model, answered["version"])["source"] == "answer"


def test_an_answer_can_be_someone_elses_words_not_only_a_proposed_option(review_model):
    review = wd.prepare_bpmn_review(
        bpmn_model_id=review_model,
        process_description="Sales riceve l'ordine, Finance verifica il credito.",
        process_understanding=_understanding_with_open_question(),
    )
    question = review["open_questions"][0]

    answered = wd.answer_bpmn_review_question(
        review_model,
        question=question["question"],
        answer="Dipende dal cliente: sopra 10k decide il CFO, sotto il commerciale.",
    )

    assert answered["open_questions"][0]["answer"].startswith("Dipende dal cliente")


def test_answering_twice_replaces_the_earlier_answer(review_model):
    review = wd.prepare_bpmn_review(
        bpmn_model_id=review_model,
        process_description="Sales riceve l'ordine, Finance verifica il credito.",
        process_understanding=_understanding_with_open_question(),
    )
    question = review["open_questions"][0]["question"]

    wd.answer_bpmn_review_question(review_model, question=question, answer="Direzione amministrativa")
    answered = wd.answer_bpmn_review_question(
        review_model, question=question, answer="Il responsabile commerciale"
    )

    # Una domanda ha una risposta corrente, non una pila di risposte; lo storico
    # conserva comunque il passaggio.
    assert len(answered["answers"]) == 1
    assert answered["answers"][0]["answer"] == "Il responsabile commerciale"
    assert len(wd.list_bpmn_review_versions(review_model)) == 3


def test_an_answer_survives_the_agent_rewriting_the_plan(review_model):
    wd.prepare_bpmn_review(
        bpmn_model_id=review_model,
        process_description="Sales riceve l'ordine, Finance verifica il credito.",
        process_understanding=_understanding_with_open_question(),
    )
    wd.answer_bpmn_review_question(
        review_model,
        question="Chi approva un ordine oltre 10k?",
        answer="Direzione amministrativa",
    )

    revised = wd.revise_bpmn_review(
        review_model, process_understanding=_understanding_with_open_question()
    )

    # La decisione umana e' registrata a parte da cio' che il modello estrae:
    # una riscrittura del piano non la cancella. L'id della domanda deriva dal
    # testo, quindi la risposta si riaggancia alla stessa domanda.
    assert revised["answers"][0]["answer"] == "Direzione amministrativa"
    assert revised["open_questions"][0]["answer"] == "Direzione amministrativa"
