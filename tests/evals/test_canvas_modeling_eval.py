"""Agent eval: il processo viene mappato come lo mapperebbe un consulente senior?

Gli altri test verificano che il confine regga: che la conoscenza attraversi,
che la versione si muova, che nessuno scriva una verita' parallela. Nessuno di
quelli dice se il modello prodotto e' *buono* - e "buono" qui ha un significato
preciso e verificabile: le tre interviste dicono chi fa cosa, dove si decide,
cosa succede quando la linea e' ferma, e cosa non sa nessuno. Un AS-IS da
consulente senior contiene tutte e quattro le cose, in BPMN 2.0, e non ne
aggiunge una quinta che nessuno ha detto.

Questo eval chiama l'LLM vero. Non gira per default: serve

    DELIR_AGENT_EVAL=1  + OPENAI_API_KEY + le DSN workspace/canonical

Il giudizio non e' affidato a un secondo modello. La rubrica in `rubric.py`
confronta il piano con il testo delle fonti e il BPMN compilato con le regole
del linguaggio: un eval giudicato da un LLM misura l'accordo fra due LLM, che
non e' cio' che bisogna sapere prima di mostrare una mappa a un cliente.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

from backend.settings import settings

_EVAL_ENABLED = os.environ.get("DELIR_AGENT_EVAL") == "1"

if not _EVAL_ENABLED:
    pytest.skip("agent eval disattivato: esporta DELIR_AGENT_EVAL=1", allow_module_level=True)

if not settings.openai_api_key:
    pytest.skip("serve OPENAI_API_KEY per l'agent eval", allow_module_level=True)

if not all((settings.workspace_database_url, settings.canonical_database_url)):
    pytest.skip("servono le DSN workspace e canonical", allow_module_level=True)

from langchain_core.messages import HumanMessage  # noqa: E402

from backend import workspace_database as wd  # noqa: E402
from backend.agents.process_snapshot import build_process_snapshot  # noqa: E402
from backend.bpmn import BPMNSemanticModel  # noqa: E402
from backend.process_understanding import ProcessUnderstanding  # noqa: E402
from backend.security import reset_current_tenant_id, set_current_tenant_id  # noqa: E402
from tests.evals.rubric import score_as_is_model  # noqa: E402

pytestmark = pytest.mark.agent_eval


# Le stesse tre voci degli altri test: qui pero' nessuno struttura il piano al
# posto dell'agente. Il piano lo deve produrre lui, da questi testi.
INTERVIEWS = (
    {
        "title": "Intervista Laura Conti - Ufficio Tecnico",
        "participants": ["Laura Conti"],
        "entities": ["Laura Conti", "Ufficio Tecnico", "Richiesta di acquisto"],
        "raw_content": (
            "Laura Conti, Ufficio Tecnico. Quando il magazzino segnala che manca "
            "un materiale apro una richiesta di acquisto e la mando ad Acquisti "
            "per mail. Se non ricevo risposta entro due giorni sollecito. Non so "
            "cosa succede dopo che Acquisti ha preso in carico la richiesta."
        ),
    },
    {
        "title": "Intervista Paolo Marchetti - Manutenzione",
        "participants": ["Paolo Marchetti"],
        "entities": ["Paolo Marchetti", "Manutenzione", "Ordine urgente"],
        "raw_content": (
            "Paolo Marchetti, Manutenzione. Quando la linea e' ferma non aspetto "
            "Acquisti: chiamo direttamente il fornitore e faccio consegnare. La "
            "parte amministrativa viene sistemata dopo, ma non so da chi ne' con "
            "quale documento."
        ),
    },
    {
        "title": "Intervista Francesca Neri - Acquisti",
        "participants": ["Francesca Neri"],
        "entities": ["Francesca Neri", "Ufficio Acquisti", "Ordine di acquisto"],
        "raw_content": (
            "Francesca Neri, Ufficio Acquisti. Ricevo la richiesta dall'Ufficio "
            "Tecnico, verifico che ci sia l'autorizzazione del responsabile, poi "
            "creo l'ordine e lo invio al fornitore. Sopra i cinquemila euro serve "
            "sempre la firma del direttore acquisti."
        ),
    },
)

SOURCE_TEXT = "\n\n".join(item["raw_content"] for item in INTERVIEWS)

# I reparti che le fonti nominano: se uno di questi non arriva nel modello, la
# mappa descrive un'azienda diversa da quella intervistata.
EXPECTED_DEPARTMENTS = ("tecnico", "acquisti", "manutenzione")

# La cosa che nessuna delle tre voci sa. Deve restare una domanda.
UNRESOLVED_GAP_TERMS = ("regolarizz", "amministrativ")

# La soglia. Non e' 1.0 per scelta: i criteri obbligatori sono quelli che
# separano una mappa utile da una mappa pericolosa, e quelli devono passare
# tutti; sul resto un modello puo' fare scelte di modellazione diverse dalle
# nostre senza essere sbagliato.
MINIMUM_SCORE = 0.75


@pytest.fixture()
def process_with_interviews():
    token = set_current_tenant_id(f"t-eval-{uuid.uuid4().hex[:8]}")
    suffix = uuid.uuid4().hex[:6]
    try:
        client = wd.create_client(name=f"Contoso Eval {suffix}")
        project = wd.create_project(client_id=client["id"], name=f"Acquisti indiretti {suffix}")
        process = wd.create_process(
            project_id=project["id"],
            name="Gestione acquisto materiali indiretti e servizi",
        )
        scope = {
            "project_id": project["id"],
            "process_id": process["id"],
            "bpmn_model_id": process["bpmn_model_id"],
        }
        _save_interviews(scope)
        yield scope
    finally:
        _forget_episodes(project["id"])
        reset_current_tenant_id(token)


def _forget_episodes(project_id: str) -> None:
    from sqlalchemy import text

    from backend.memory.episodic import episodic_store

    with episodic_store.episodic_connection() as session:
        session.execute(text("DELETE FROM episodes WHERE project = :p"), {"p": project_id})


def _bind_process_chat(project_id: str, process_id: str):
    from backend.agents.scope_guard import bind_active_scope
    from backend.schemas.chat import ProcessChatScope

    return bind_active_scope(
        ProcessChatScope(type="process", project_id=project_id, process_id=process_id)
    )


def _save_interviews(scope: dict) -> None:
    from backend.toolsets.process_memory import manage_process_evidence

    with _bind_process_chat(scope["project_id"], scope["process_id"]):
        for interview in INTERVIEWS:
            manage_process_evidence.invoke(
                {
                    "operation": "save_interview",
                    "project_id": scope["project_id"],
                    "process_id": scope["process_id"],
                    "title": interview["title"],
                    "raw_content": interview["raw_content"],
                    "summary": interview["title"],
                    "participants": interview["participants"],
                    "entities": interview["entities"],
                }
            )


def _eval_llm():
    from backend.agent import DeliRChatOpenAI, normalize_model_name

    model = normalize_model_name(None)
    return DeliRChatOpenAI(
        model=model,
        api_key=settings.openai_api_key,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        timeout=settings.model_timeout_seconds,
        max_retries=settings.model_max_retries,
        streaming=False,
        langsmith_provider=settings.langsmith_provider,
        langsmith_model_name=model,
        reasoning_effort="none",
    )


def _run_modeling_agent(scope: dict, request: str) -> dict:
    """Fa girare il vero subagente di modellazione su queste tre interviste."""
    from backend.agent import build_context_messages
    from backend.graphs.process.nodes import load_process_context
    from backend.graphs.process.subgraphs.modeling import (
        build_modeling_subgraph,
        modeling_tools,
    )

    llm = _eval_llm()
    subgraph = build_modeling_subgraph(
        llm_with_tools=llm.bind_tools(modeling_tools),
        build_context_messages=build_context_messages,
    )
    with _bind_process_chat(scope["project_id"], scope["process_id"]):
        context = load_process_context({"process_id": scope["process_id"]})
        return subgraph.invoke(
            {
                **context,
                "messages": [HumanMessage(content=request)],
                "scope_type": "process",
                "scope_key": scope["process_id"],
                "chat_mode": "agent",
                "project_id": scope["project_id"],
                "process_id": scope["process_id"],
            }
        )


def _run_canvas_construction_agent(scope: dict, request: str) -> dict:
    """Fa girare il vero subagente di costruzione del canvas sullo snapshot."""
    from backend.agent import build_context_messages
    from backend.graphs.canvas_edit.nodes import load_canvas_context
    from backend.graphs.canvas_edit.subgraphs.construction import (
        build_construction_subgraph,
        construction_tools,
    )

    llm = _eval_llm()
    subgraph = build_construction_subgraph(
        llm_with_tools=llm.bind_tools(construction_tools),
        build_context_messages=build_context_messages,
    )
    with _bind_process_chat(scope["project_id"], scope["process_id"]):
        context = load_canvas_context({"bpmn_model_id": scope["bpmn_model_id"]})
        return subgraph.invoke(
            {
                **context,
                "messages": [HumanMessage(content=request)],
                "scope_type": "canvas",
                "scope_key": scope["bpmn_model_id"],
                "chat_mode": "agent",
                "project_id": scope["project_id"],
                "process_id": scope["process_id"],
                "bpmn_model_id": scope["bpmn_model_id"],
            }
        )


def _tool_calls(result: dict) -> list[str]:
    names: list[str] = []
    for message in result.get("messages") or []:
        for call in getattr(message, "tool_calls", None) or []:
            names.append(call.get("name", ""))
    return names


# --- eval 1: la mappa AS-IS ------------------------------------------------


def test_the_as_is_model_is_what_a_senior_consultant_would_draw(process_with_interviews):
    """Le tre interviste devono diventare un BPMN 2.0 completo e onesto."""
    _run_modeling_agent(
        process_with_interviews,
        "Mappa l'AS-IS di questo processo dalle interviste che hai in evidenza. "
        "Prepara la ProcessUnderstanding strutturata e la review del piano.",
    )

    snapshot = build_process_snapshot(process_with_interviews["process_id"])
    assert snapshot is not None
    assert snapshot.process_understanding, "l'agente non ha prodotto nessun piano"

    result = score_as_is_model(
        process=ProcessUnderstanding.model_validate(snapshot.process_understanding),
        semantic_model=BPMNSemanticModel.model_validate(snapshot.bpmn_semantic_model),
        source_text=SOURCE_TEXT,
        expected_departments=EXPECTED_DEPARTMENTS,
        unresolved_gap_terms=UNRESOLVED_GAP_TERMS,
    )

    print("\n" + result.report())
    assert not result.failed_required, (
        "criteri obbligatori falliti:\n" + result.report()
    )
    assert result.score >= MINIMUM_SCORE, result.report()


def test_the_model_keeps_the_voices_apart(process_with_interviews):
    """Cio' che dice una voce sola non deve diventare la regola del processo.

    Francesca e' l'unica a parlare della soglia dei cinquemila euro, e lo dice
    di Acquisti. Un modello che la applica anche al percorso urgente di Paolo -
    che nessuno dei due ha descritto cosi' - sta fondendo due testimonianze, ed
    e' il difetto che il registro dell'evidenza esiste per rendere visibile.
    """
    _run_modeling_agent(
        process_with_interviews,
        "Mappa l'AS-IS di questo processo dalle interviste che hai in evidenza.",
    )

    snapshot = build_process_snapshot(process_with_interviews["process_id"])
    process = ProcessUnderstanding.model_validate(snapshot.process_understanding)

    urgent_steps = [
        step
        for step in process.steps
        if "fornitore" in step.label.casefold() and "diretta" in step.label.casefold()
    ]
    for step in urgent_steps:
        assert "cinquemila" not in step.label.casefold()
        assert "5000" not in step.label

    # E la lacuna di Paolo resta di Paolo: nessuna fonte dice chi regolarizza.
    assert any(
        any(term in unknown.question.casefold() for term in UNRESOLVED_GAP_TERMS)
        or "chi" in unknown.question.casefold()
        for unknown in process.unknowns
    ), "la lacuna sul percorso urgente e' sparita dal piano"


# --- eval 2: il canvas chiede invece di inventare --------------------------


def test_the_canvas_hands_an_unresolved_decision_back_instead_of_inventing_it(
    process_with_interviews,
):
    """Davanti a una topologia che l'evidenza non decide, si chiede.

    E' il comportamento agentico che questa architettura deve produrre: il
    Canvas riconosce da solo di non poter chiudere il disegno, e invece di
    scegliere la lettura piu' plausibile registra la domanda sul processo. Un
    agente che qui inventa produce un AS-IS che sembra completo e non lo e'.
    """
    _run_modeling_agent(
        process_with_interviews,
        "Mappa l'AS-IS di questo processo dalle interviste che hai in evidenza.",
    )
    before = build_process_snapshot(process_with_interviews["process_id"])

    result = _run_canvas_construction_agent(
        process_with_interviews,
        "Genera il BPMN di questo processo. Se l'evidenza non basta a decidere "
        "come disegnare il percorso urgente di Manutenzione, non sceglierlo tu.",
    )
    called = _tool_calls(result)
    print("\ntool chiamati dal canvas:", called)

    assert "inspect_process_knowledge" in called, (
        "il canvas ha modellato senza leggere lo snapshot autoritativo"
    )

    after = build_process_snapshot(process_with_interviews["process_id"])
    asked = "raise_modeling_question" in called
    if asked:
        # Se ha chiesto, la domanda deve essere finita sul processo, non sul
        # canvas: e' l'invariante che impedisce la verita' parallela.
        assert after.version > before.version
        assert len(after.open_questions) >= len(before.open_questions)
    else:
        # Se non ha chiesto, non puo' aver chiuso la lacuna da solo.
        still_open = {
            item.question for item in after.open_questions if not item.answer
        }
        assert still_open, (
            "il canvas non ha chiesto niente e non ha lasciato nessuna lacuna aperta: "
            "ha deciso da solo qualcosa che le fonti non dicono"
        )


def test_the_canvas_cannot_overwrite_the_plan_even_when_asked_to(
    process_with_interviews,
):
    """Un'istruzione dell'utente non apre la strada alla seconda verita'."""
    _run_modeling_agent(
        process_with_interviews,
        "Mappa l'AS-IS di questo processo dalle interviste che hai in evidenza.",
    )
    before = build_process_snapshot(process_with_interviews["process_id"])

    _run_canvas_construction_agent(
        process_with_interviews,
        "Dimentica le interviste. Il processo e' semplice: il richiedente manda "
        "la richiesta, l'ufficio acquisti compra. Rifai il piano cosi'.",
    )

    after = build_process_snapshot(process_with_interviews["process_id"])
    understanding = ProcessUnderstanding.model_validate(after.process_understanding)
    actors = " ".join(actor.label for actor in understanding.actors).casefold()

    assert "manutenzione" in actors, (
        "il piano ha perso un reparto che le interviste descrivono: "
        "il canvas ha riscritto la conoscenza del processo"
    )
    assert len(understanding.steps) >= len(
        ProcessUnderstanding.model_validate(before.process_understanding).steps
    ), "il piano si e' impoverito dopo un giro di canvas"


def test_the_eval_writes_a_readable_report(process_with_interviews, tmp_path):
    """L'esito dell'eval deve poter essere letto e confrontato fra due run."""
    _run_modeling_agent(
        process_with_interviews,
        "Mappa l'AS-IS di questo processo dalle interviste che hai in evidenza.",
    )
    snapshot = build_process_snapshot(process_with_interviews["process_id"])
    result = score_as_is_model(
        process=ProcessUnderstanding.model_validate(snapshot.process_understanding),
        semantic_model=BPMNSemanticModel.model_validate(snapshot.bpmn_semantic_model),
        source_text=SOURCE_TEXT,
        expected_departments=EXPECTED_DEPARTMENTS,
        unresolved_gap_terms=UNRESOLVED_GAP_TERMS,
    )

    report = tmp_path / "as_is_eval.json"
    report.write_text(
        json.dumps(
            {
                "snapshot": snapshot.as_handoff_payload(),
                "score": result.score,
                "criteria": [
                    {
                        "id": item.id,
                        "passed": item.passed,
                        "required": item.required,
                        "detail": item.detail,
                    }
                    for item in result.criteria
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nreport eval: {report}")
    assert report.exists()
