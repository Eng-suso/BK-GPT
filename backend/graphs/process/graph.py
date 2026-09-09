from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph

from backend.graphs.common import (
    artifact_field,
    artifact_for_prompt,
    artifact_is_present,
    build_tool_chat_subgraph,
    latest_user_text,
    message_text,
    recent_conversation_digest,
)
from backend.agents.evidence_brief import (
    ledger_vocabulary,
    question_is_grounded,
    render_divergences,
    render_ledger_lines,
    render_source_evidence,
    turn_evidence_ledger,
)
from backend.agents.process_snapshot import build_process_snapshot
from backend.memory import provenance
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.process.nodes import load_process_context
from backend.graphs.process.state import ProcessState
from backend.graphs.process.subgraphs.discovery import build_discovery_subgraph, discovery_tools
from backend.graphs.process.subgraphs.evidence import build_evidence_subgraph, evidence_tools
from backend.graphs.process.subgraphs.modeling import build_modeling_subgraph, modeling_tools
from backend.graphs.process.tools import PROCESS_TOOL_POLICY
from backend.graphs.routing_contracts import (
    ENGINEERING_LOOP_MAX_ITERATIONS,
    ProcessRoutingDecision,
    authorize_routing_decision,
    capability_menu,
    invalid_process_decision,
    parse_routing_decision,
    resolve_routing_decision,
)


SKILLS_DIR = Path(__file__).resolve().parent / "skills"

PROCESS_SUBGRAPH_CONTRACT = """
Process Macro Agent contract.

{tool_policy}

The Process Macro Agent is the semantic orchestrator for one process workspace.
It owns the transition from process conversation to evidence-backed
ProcessUnderstanding, then to BPMNSemanticModel, then to a narrow Canvas Macro
handoff.

ProcessUnderstanding is the canonical semantic context for AS-IS/BPMN work.
Do not produce BPMN directly from raw text. Discovery and evidence synthesis
must happen before modeling when the input is incomplete, weak, contradictory
or source-sensitive.

These artifact names are your internal vocabulary, not the consultant's. Reason
with them, never answer with them: the product-language rule in the scope
prompt governs what the consultant actually reads.

Use the preloaded process record, pending review, ProcessUnderstanding,
BPMNSemanticModel, missing information and saved BPMN XML before asking the
user to repeat context.

Enterprise Knowledge Graph retrieval is available through process KG tools.
Treat it as relation-heavy retrieval context and keep workspace DB records as
the authoritative operational state. The KG is a canonical Postgres store
projected to Neo4j; all reads go through the scoped gateway.

{skill_context}
""".format(
    tool_policy=PROCESS_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
).strip()


PROCESS_ROUTER_PROMPT_TEMPLATE = """
You are the Process graph router for DeliR.
You are the reasoning layer, not the execution controller.
Propose the next best engineering action using user goal and current process state.
Do not equate the user's goal with the next executable action.

Capabilities you may propose:
{capability_menu}

Return structured output matching the ProcessRoutingDecision schema.
Set goal, intent, next_action and suggested_capability separately.
Use workflow_scope=local_operation for narrow canvas/XML patch requests, single_step
for one bounded capability, and full_workflow only when the user asks for an
end-to-end engineering outcome.

You are re-invoked after every specialist pass in a full_workflow run. Keep
workflow_scope=full_workflow only while there is still epistemically necessary work
before an end-to-end outcome is reached (e.g. more evidence to gather, contradictions
to resolve, a semantic model still missing). Switch it to single_step, local_operation
or direct as soon as the remaining request can be answered without another pass -
you decide when the work is done. The runtime owns the pass budget and stops on
repeated no-progress passes; you do not set or negotiate that limit.

The evidence ledger below is what this process already knows, voice by voice.
Read it before routing: what is in the ledger is not missing, and a pass that
re-collects it is a wasted pass.

If you choose route=clarification, clarification_question must name the concrete
gap or contradiction in that ledger that makes the question necessary - who said
what, and what does not add up. A question that asks for a whole category the
ledger already covers ("which actors?", "which rules?", "how does the process
work?") is not a clarification: it is a restart, and the runtime will reject it
and route to evidence instead.
""".strip()


def process_router_prompt(chat_mode: str | None = None) -> str:
    """Build the process router prompt for the specified chat mode.
    
    Args:
        chat_mode (str | None): Untrusted chat-mode value used to select the
            capabilities presented to the router.
    
    Returns:
        str: A router prompt containing the capability menu for the selected chat
            mode.
    """
    return PROCESS_ROUTER_PROMPT_TEMPLATE.format(capability_menu=capability_menu("process", chat_mode))



def process_state_signature(state: dict) -> str:
    """Build a compact progress signature from the current process state.
    
    Args:
        state (dict): Untrusted process state containing artifact, readiness,
            diagnostic, quality, persistence, contradiction, claim, and gap data.
    
    Returns:
        str: A pipe-delimited signature representing the presence and counts of
            tracked process artifacts and issues.
    
    The function performs no side effects and does not persist state.
    """
    diagnostics = state.get("process_understanding_diagnostics")
    quality_report = state.get("process_quality_report")
    return "|".join(
        [
            str(artifact_is_present(state.get("process_understanding"))),
            str(artifact_is_present(state.get("bpmn_semantic_model"))),
            str(state.get("readiness_score")),
            str(len(state.get("missing_information") or [])),
            str(bool(artifact_field(diagnostics, "blocking"))),
            str(bool(artifact_field(diagnostics, "warnings"))),
            str(artifact_field(quality_report, "overall_score")),
            str(bool(state.get("saved_bpmn_xml"))),
            str(len(state.get("contradictions") or [])),
            str(len(state.get("process_claims") or [])),
            str(len(state.get("process_gaps") or [])),
            str((state.get("evidence_ledger") or {}).get("source_set_id") or ""),
            str((state.get("draft_readiness") or {}).get("status") or ""),
            str((state.get("validation_readiness") or {}).get("status") or ""),
        ]
    )


# La capability con cui il runtime rimpiazza un chiarimento non ancorato. Non e'
# una scelta di merito - quale evidenza serva lo decide lo specialista - ma il
# solo passo che ha senso quando la domanda proposta chiedeva cio' che il
# registro contiene gia'.
_EVIDENCE_CAPABILITY = "process.evidence"
_EVIDENCE_MODES = frozenset({"plan", "agent"})


def ungrounded_clarification(
    *, status: str, question: str | None, state: dict
) -> str | None:
    """Perche' questo chiarimento non si puo' consegnare, se non si puo'.

    Vale solo per il chiarimento che il router ha scelto (`clarification_required`):
    quello che il runtime impone per un prerequisito mancante o per una capability
    fuori modalita' e' un rifiuto motivato, e va detto al consulente cosi' com'e'.

    PROCESS-V2-12/15: con tre interviste agli atti il router proponeva ancora
    "quali attori?", "quali regole?", "quali soglie di approvazione?". Non sono
    domande, sono le categorie su cui l'evidenza era gia' stata raccolta: chi le
    riceve capisce che il lavoro fatto non e' arrivato da nessuna parte.

    Args:
        status: Lo stato dell'autorizzazione di routing.
        question: La domanda proposta dal router.
        state: Stato del turno, da cui si costruisce il registro.

    Returns:
        La ragione del rifiuto, o `None` se il chiarimento e' legittimo.
    """
    if status != "clarification_required":
        return None
    if state.get("chat_mode") and state["chat_mode"] not in _EVIDENCE_MODES:
        return None

    vocabulary = ledger_vocabulary(turn_evidence_ledger(state))
    if not vocabulary:
        return None
    if question_is_grounded(question or "", vocabulary):
        return None
    return (
        "Clarification refused: the proposed question asks for a category the "
        "evidence ledger already covers, without naming the gap or contradiction "
        f"behind it ({' '.join((question or 'nessuna domanda').split())[:200]})."
    )


def process_routing_state(
    decision: ProcessRoutingDecision,
    *,
    user_request: str = "",
    state: dict | None = None,
    parse_source: str = "structured",
    parse_error: str | None = None,
) -> dict:
    authorization = authorize_routing_decision(
        owner="process",
        decision=decision,
        state=state,
        parse_source=parse_source,
        parse_error=parse_error,
    )
    state = state or {}
    route = authorization["route"]
    target = authorization["target"]
    reason = decision.reason or decision.reasoning_summary or "Process router decision."

    refusal = ungrounded_clarification(
        status=authorization["status"],
        question=decision.clarification_question,
        state=state,
    )
    if refusal:
        route = "evidence"
        target = "evidence_subgraph"
        reason = refusal
        authorization = {
            **authorization,
            "route": route,
            "target": target,
            "status": "ungrounded_clarification",
            "authorized_capability": _EVIDENCE_CAPABILITY,
            "blocking_conditions": [*authorization["blocking_conditions"], refusal],
            "termination_reason": None,
        }
        decision = decision.model_copy(
            update={
                "needs_clarification": False,
                "clarification_question": None,
                "process_mode": "evidence",
            }
        )
    expected_result = decision.expected_result or ""
    process_mode = decision.process_mode or ("clarification" if route == "clarification" else route)
    process_objective = decision.process_objective or decision.goal or expected_result or None
    needs_clarification = bool(decision.needs_clarification or route == "clarification")
    delegation_payload = {
        "target": target,
        "route": route,
        "user_request": user_request,
        "entity_hints": decision.entity_hints,
        "expected_result": expected_result,
        "reason": reason,
        "goal": decision.goal,
        "intent": decision.intent,
        "next_action": decision.next_action,
        "workflow_scope": decision.workflow_scope,
        "authorized_capability": authorization["authorized_capability"],
    }
    routing_event = {
        "owner": "process",
        "route": route,
        "proposed_route": authorization["proposed_route"],
        "target": target,
        "confidence": decision.confidence,
        "needs_clarification": needs_clarification,
        "status": authorization["status"],
        "goal": decision.goal,
        "intent": decision.intent,
        "next_action": decision.next_action,
        "workflow_scope": decision.workflow_scope,
        "proposed_capability": authorization["proposed_capability"],
        "authorized_capability": authorization["authorized_capability"],
        "blocking_conditions": authorization["blocking_conditions"],
        "required_context": decision.required_context,
        "expected_next_state": decision.expected_next_state,
        "termination_reason": authorization["termination_reason"],
        "parse_source": authorization["parse_source"],
        "reason": reason,
        "reasoning_summary": decision.reasoning_summary,
    }

    return {
        "process_route": route,
        "process_mode": process_mode,
        "process_objective": process_objective,
        "process_phase": process_mode,
        "delegation_target": target,
        "delegation_reason": reason,
        "routing_confidence": decision.confidence,
        "needs_clarification": needs_clarification,
        "clarification_question": decision.clarification_question,
        "entity_hints": decision.entity_hints,
        "delegation_payload": delegation_payload,
        "routing_trace": [routing_event],
        "delegation_events": [delegation_payload] if target else [],
        "goal": decision.goal,
        "intent": decision.intent,
        "next_action": decision.next_action,
        "suggested_capability": authorization["proposed_capability"],
        "authorized_capability": authorization["authorized_capability"],
        "orchestration_status": authorization["status"],
        "termination_reason": authorization["termination_reason"],
        "blocking_conditions": authorization["blocking_conditions"],
        "required_context": decision.required_context,
        "reasoning_summary": decision.reasoning_summary,
        "workflow_scope": decision.workflow_scope,
        "engineering_loop_iteration": state.get("engineering_loop_iteration", 0),
        # Set once from server policy and preserved across router re-entry: the
        # router runs again after every specialist pass, so rewriting the budget
        # here would let it drift mid-run.
        "engineering_loop_max_iterations": (
            state.get("engineering_loop_max_iterations") or ENGINEERING_LOOP_MAX_ITERATIONS
        ),
        "process_progress_signature": process_state_signature(state),
        "process_continue_loop": False,
    }


def parse_process_router_json(content: str, user_request: str = "", state: dict | None = None) -> dict:
    decision, parse_source, parse_error = parse_routing_decision(
        content,
        ProcessRoutingDecision,
        invalid_process_decision,
    )
    return process_routing_state(
        decision,
        user_request=user_request,
        state=state,
        parse_source=parse_source,
        parse_error=parse_error,
    )


def build_process_router(llm):
    """
    Build a process-intent routing node.
    
    The returned node routes the latest user request using the supplied language
    model and converts both valid and invalid routing decisions into authorized
    process state. When no user message is available, it enforces the direct
    route. Unexpected routing failures are converted into an invalid decision
    instead of being propagated.
    
    Args:
        llm: Language model used to generate structured routing decisions.
    
    Returns:
        A routing node that accepts process state and runtime configuration and
        returns updated process routing state. The node invokes the language model
        but does not persist data.
    
    """
    def route_process_intent(state: ProcessState, config: RunnableConfig) -> dict:
        """
        Route the latest process request to the appropriate workflow.
        
        Args:
            state (ProcessState): Untrusted process state and user-request context used to
                construct the routing decision.
            config (RunnableConfig): Runtime configuration for the routing invocation.
        
        Returns:
            dict: Authorized process routing state, including the selected route and
                routing metadata. Falls back to a direct route when no user message is
                available or structured routing fails.
        
        Notes:
            The function does not persist state. It invokes the configured routing model
            and converts model failures into an invalid routing decision.
        """
        user_text = latest_user_text(state)
        if not user_text:
            return parse_process_router_json(
                '{"route":"direct","confidence":0,"reason":"No user message available."}'
            )

        try:
            decision, parse_source, parse_error = resolve_routing_decision(
                owner="process",
                llm=llm,
                model=ProcessRoutingDecision,
                messages=[
                    SystemMessage(content=process_router_prompt(state.get("chat_mode"))),
                    HumanMessage(
                        content=(
                            "Active scope: process\n\n"
                            f"project_id: {state.get('project_id')}\n"
                            f"process_id: {state.get('process_id')}\n"
                            f"process_name: {state.get('process_name')}\n"
                            f"readiness_score: {state.get('readiness_score')}\n"
                            f"missing_information: {state.get('missing_information') or []}\n"
                            f"has_process_understanding: {artifact_is_present(state.get('process_understanding'))}\n"
                            "process_understanding_diagnostics: "
                            f"{artifact_for_prompt(state.get('process_understanding_diagnostics'))}\n"
                            "process_quality_report: "
                            f"{artifact_for_prompt(state.get('process_quality_report'))}\n"
                            f"has_bpmn_semantic_model: {artifact_is_present(state.get('bpmn_semantic_model'))}\n"
                            f"has_saved_bpmn_xml: {bool(state.get('saved_bpmn_xml'))}\n"
                            f"draft_readiness: {(state.get('draft_readiness') or {}).get('status')}\n"
                            f"validation_readiness: {(state.get('validation_readiness') or {}).get('status')}\n\n"
                            # PROCESS-V2-13: il router decideva il passo
                            # successivo senza vedere una riga dell'evidenza,
                            # quindi mandava a raccogliere cio' che era gia'
                            # agli atti o chiedeva chiarimenti su cio' che il
                            # registro spiegava. Qui basta sapere quali fonti
                            # esistono: il testo integrale serve a chi risponde e
                            # a chi modella, non a chi sceglie il passo.
                            "Evidence ledger for this process:\n"
                            f"{render_source_evidence(state.get('evidence_ledger') or {}, include_content=False)}\n\n"
                            f"{render_ledger_lines(turn_evidence_ledger(state))}\n\n"
                            f"Recorded divergences:\n{render_divergences(state)}\n\n"
                            "Recent conversation (resolve references against this):\n"
                            f"{recent_conversation_digest(state)}\n\n"
                            # Le passate degli specialisti non stanno nel
                            # transcript: senza questo il router non saprebbe
                            # cosa e' gia' stato fatto in questo stesso turno.
                            "Work already done this turn:\n"
                            f"{specialist_findings_digest(state)}\n\n"
                            "Latest user request:\n"
                            f"{user_text}"
                        )
                    ),
                ],
                config=config,
                invalid_factory=invalid_process_decision,
                state=state,
            )
        except Exception:
            decision = invalid_process_decision("Structured router failed unexpectedly.")
            parse_source = "invalid"
            parse_error = "Structured router failed unexpectedly."

        return process_routing_state(
            decision,
            user_request=user_text,
            state=state,
            parse_source=parse_source,
            parse_error=parse_error,
        )

    return route_process_intent


def selected_process_route(state: ProcessState) -> str:
    return state.get("process_route") or "direct"


def ask_process_clarification(state: ProcessState) -> dict:
    return {
        "messages": [
            AIMessage(
                content=state.get("clarification_question")
                or "Mi serve un chiarimento sul processo o sull'obiettivo prima di procedere."
            )
        ]
    }


# A single pass with no state change is not proof the loop is stuck (a discovery/
# evidence pass can legitimately end in a question or an assessment without moving
# canonical state); require this many consecutive no-progress passes before the
# runtime treats it as a stall.
NO_PROGRESS_STOP_THRESHOLD = 2


def evaluate_process_iteration(state: ProcessState) -> dict:
    iteration = int(state.get("engineering_loop_iteration") or 0) + 1
    max_iterations = int(state.get("engineering_loop_max_iterations") or ENGINEERING_LOOP_MAX_ITERATIONS)
    previous_signature = state.get("process_progress_signature")
    current_signature = process_state_signature(state)
    no_progress_count = int(state.get("process_no_progress_count") or 0)

    if previous_signature == current_signature:
        no_progress_count += 1
    else:
        no_progress_count = 0

    workflow_scope = state.get("workflow_scope") or "single_step"
    # The agent's own decision: it asked to keep working (full_workflow) and did not
    # route into a terminal/handoff step. The runtime does not second-guess this -
    # it only enforces the budget and no-progress safety net below.
    agent_wants_to_continue = (
        workflow_scope == "full_workflow"
        and state.get("process_route") not in {"direct", "clarification", "delegate_canvas"}
    )
    within_budget = iteration < max_iterations
    making_progress = no_progress_count < NO_PROGRESS_STOP_THRESHOLD

    continue_loop = agent_wants_to_continue and within_budget and making_progress
    termination_reason = state.get("termination_reason")

    if not continue_loop:
        if agent_wants_to_continue and not within_budget:
            termination_reason = "SAFE_LIMIT_REACHED"
        elif agent_wants_to_continue and not making_progress:
            termination_reason = "BLOCKED_NO_PROGRESS"
        else:
            termination_reason = termination_reason or "DONE"

    return {
        "engineering_loop_iteration": iteration,
        "process_no_progress_count": no_progress_count,
        "process_progress_signature": current_signature,
        "process_continue_loop": continue_loop,
        "termination_reason": termination_reason,
        "routing_trace": [
            {
                "owner": "process",
                "event": "engineering_loop_evaluation",
                "iteration": iteration,
                "max_iterations": max_iterations,
                "no_progress_count": no_progress_count,
                "continue_loop": continue_loop,
                "termination_reason": termination_reason,
            }
        ],
    }


def specialist_findings_digest(state: dict, limit: int = 6) -> str:
    """Cosa hanno concluso gli specialisti in questo turno, in breve.

    Le loro passate non passano dal transcript (vedi `findings_channel` in
    `build_tool_chat_subgraph`), quindi chi deve decidere il passo successivo
    le legge da qui.
    """
    findings = state.get("specialist_findings") or []
    lines = [
        f"- [{item.get('owner') or 'passata'}] {' '.join(str(item.get('finding') or '').split())[:400]}"
        for item in findings[-limit:]
        if str(item.get("finding") or "").strip()
    ]
    return "\n".join(lines) or "nessuna passata conclusa in questo turno"


PROCESS_REPORT_PROMPT = """
Scrivi la risposta che il consulente legge alla fine di questo giro di lavoro.

Gli specialisti hanno gia' lavorato: quello che hanno concluso e' qui sotto. Non
e' un testo da consegnare, e' materiale. Tu scrivi UNA risposta sola, in prosa,
che tiene insieme le loro passate senza ripeterle: se due passate dicono la
stessa cosa, la dici una volta.

Sopra alle passate c'e' il REGISTRO DELL'EVIDENZA: le affermazioni raccolte,
ognuna con chi la dice, l'ambito che copre e un grado di sostegno gia'
calcolato. Il registro vince sulle passate. Dove le due cose divergono, vale il
registro - e' l'unico posto dove la provenance e' verificata.

Governance dell'evidenza - il punto su cui questa risposta si gioca:

- Attribuisci ogni affermazione alla voce che il registro le assegna, e a
  nessun'altra. Se il registro dice "Laura Conti", non puoi scrivere "secondo
  Paolo". Se una voce non c'e', dillo, non sceglierne una plausibile.
- Il grado di sostegno non lo decidi tu: e' nel registro.
  "riferito da una sola fonte" -> scrivi "X riferisce che...", "secondo X".
  "corroborato da piu' fonti" -> puoi dire che piu' fonti concordano, e citarle.
  "inferenza" -> dichiaralo come tua deduzione.
  "la fonte dichiara di non saperlo" -> e' un'informazione su quella persona,
  non una lacuna del processo.
  "Confermato" vale solo per cio' che il registro dichiara corroborato: non
  promuovere mai una fonte sola.
- Rispetta l'ambito (`scope_label`). Cio' che vale per un reparto vale per quel
  reparto: non estenderlo al processo intero. Due persone che, ciascuna per il
  proprio pezzo, dicono di non avere un dato non dimostrano che il processo non
  ce l'abbia: dicono che loro non ce l'hanno, e va scritto cosi'.
- Una frase attribuita a piu' voci puo' contenere SOLO cio' che tutte quelle
  voci reggono. Il registro lo dice riga per riga: cio' che segue "solo <voce>"
  e' di quella voce e non entra in una frase condivisa. Se serve dirlo, si dice
  a parte: "entrambi riferiscono X; <voce> aggiunge Y".
- Non rafforzare il testo originale. Se la fonte dice "puo' essere necessario
  chiedere conferma", non scrivere "deve confermare". Quando la citazione c'e',
  la tua frase non puo' dire piu' di quella.
- Fra virgolette ci va solo cio' che il registro riporta come "parole
  originali". Una riga marcata "nessuna citazione riscontrata" e' una
  riformulazione: raccontala, non citarla.
- Le divergenze sono gia' classificate. Chiama contraddizione solo cio' che il
  registro marca come incompatibilita' vera; una differenza di ambito, un
  diverso grado di formalizzazione o un "non lo so" si raccontano per quello
  che sono. Una contraddizione vera si dichiara e resta aperta: non la risolvi
  tu scegliendo la versione piu' plausibile.
- Non dichiarare mancante cio' che il registro contiene. Se c'e' ma lo dice una
  sola voce, e' evidenza non ancora corroborata, non un buco.
- Non aggiungere attori, soglie, sistemi o date che nel registro e nelle fonti
  non ci sono.

Struttura la risposta cosi', senza intestazioni tecniche:
cosa ci hanno detto - cosa resta incerto - cosa si contraddice - cosa chiedere
dopo, e a chi.

Non riscrivere il registro in fondo alla risposta: al lettore arriva gia'
stampato dal sistema, riga per riga. Tu scrivi la prosa.

Nessun nome interno di sistema, di agente o di passaggio: il consulente legge il
risultato del lavoro, non come e' organizzato.
""".strip()


def build_process_report(llm):
    """Il nodo che parla al consulente, uno solo per turno.

    Il giro di lavoro puo' durare piu' passate, e ogni specialista ne concludeva
    una in chat: il consulente si ritrovava quattro o cinque sintesi quasi
    identiche una dietro l'altra. Ora le passate lavorano in silenzio e qui si
    scrive la risposta, una volta, su quello che hanno prodotto.

    La prosa la scrive il modello; la tracciabilita' no. La sezione "Da dove
    viene" viene stampata dal runtime dal registro dell'evidenza: e' l'unica
    parte della risposta che non puo' essere riscritta piu' forte di quanto la
    fonte dica, e da' al consulente una riga da verificare per ogni
    affermazione.
    """

    def write_process_report(state: ProcessState, config: RunnableConfig) -> dict:
        findings = state.get("specialist_findings") or []
        if not findings:
            # Nessuno ha concluso niente: non c'e' una risposta da scrivere, e
            # inventarne una sarebbe peggio del silenzio.
            return {}

        dossier = "\n\n".join(
            f"[passata {index}] {item.get('finding', '')}".strip()
            for index, item in enumerate(findings, start=1)
            if str(item.get("finding") or "").strip()
        )
        ledger = turn_evidence_ledger(state)
        summary = provenance.summarize_ledger(ledger)
        brief = HumanMessage(
            content=(
                f"Processo: {state.get('process_name') or 'senza nome'}\n"
                f"Richiesta del consulente:\n{latest_user_text(state)}\n\n"
                "REGISTRO DELL'EVIDENZA (autoritativo su attribuzione e "
                "grado di sostegno):\n"
                f"{render_ledger_lines(ledger)}\n\n"
                f"Voci sentite finora: {', '.join(summary.voices) or 'nessuna'}\n"
                f"Divergenze registrate:\n{render_divergences(state)}\n\n"
                f"Cosa manca ancora: {state.get('missing_information') or []}\n\n"
                f"Conclusioni delle passate di lavoro:\n{dossier}"
            )
        )
        messages = [SystemMessage(content=PROCESS_REPORT_PROMPT), brief]
        response = llm.invoke(messages, config=config)

        # Il controllo di composizione viveva solo dentro il tool di sintesi,
        # che l'agente puo' non chiamare: la frase multi-fonte tornava a
        # formarsi qui, all'ultimo passaggio, dove nessuno la guardava.
        # Una correzione sola, poi si dice come stanno le cose.
        violations = provenance.audit_answer(message_text(response), ledger)
        if violations:
            response = llm.invoke(
                [
                    *messages,
                    response,
                    HumanMessage(content=_attribution_correction(violations)),
                ],
                config=config,
            )
            violations = provenance.audit_answer(message_text(response), ledger)

        parts = [
            message_text(response),
            provenance.render_attribution_notice(violations),
            provenance.render_provenance_section(ledger),
        ]
        response.content = "\n\n".join(part for part in parts if part.strip())
        return {"messages": [response]}

    return write_process_report


def _attribution_correction(violations: list[provenance.AnswerViolation]) -> str:
    """Cosa si chiede al modello quando ha fuso due fonti in una frase.

    Non "riscrivi tutto": si nomina la frase, l'attributo e il suo proprietario.
    La parte condivisa resta corroborata, l'attributo torna a chi lo ha detto.
    """
    lines = [
        "Una o piu' frasi attribuiscono a piu' fonti qualcosa che dice una sola "
        "voce. Riscrivi SOLO quelle frasi, tenendo il resto com'e':",
        "",
    ]
    lines += [f"- {item.as_dict()['message']}" for item in violations]
    lines += [
        "",
        "La parte che tutte le fonti reggono resta come accordo; cio' che "
        "aggiunge una sola voce si dice a parte, attribuito a lei. Non "
        "aggiungere nulla che non sia nel registro.",
    ]
    return "\n".join(lines)


def selected_process_loop_transition(state: ProcessState) -> str:
    """Selects the next process-graph transition from the loop continuation flag.
    
    Args:
        state: Process state containing the loop continuation decision.
    
    Returns:
        ``"continue"`` when ``process_continue_loop`` is truthy; otherwise,
        ``"end"``.
    """
    return "continue" if state.get("process_continue_loop") else "end"


def build_canvas_delegation_node(canvas_subgraph):
    """Create a process node that delegates authorized Canvas work.
    
    Args:
        canvas_subgraph: Optional Canvas graph used to process the delegation.
    
    Returns:
        A process-state handler that blocks delegation when the Canvas graph or BPMN
        model ID is unavailable; otherwise, it invokes the Canvas graph and merges
        its messages, BPMN XML, routing trace, and delegation status into the
        process state.
    
    The handler preserves existing BPMN XML when the Canvas graph provides none.
    It may trigger side effects performed by the delegated Canvas graph, including
    persistence of BPMN changes.
    """

    def delegate_to_canvas_macro(state: ProcessState, config: RunnableConfig) -> dict:
        """
        Delegate process work to the Canvas subgraph when the required BPMN model is available.
        
        Args:
            state (ProcessState): Untrusted process state containing the BPMN model identifier,
                process context, messages, and delegation intent.
            config (RunnableConfig): Runtime configuration passed to the Canvas subgraph.
        
        Returns:
            dict: Routing state containing Canvas messages, BPMN XML, routing traces, and a
                delegation event. The delegation is marked as blocked when the Canvas
                subgraph or BPMN model identifier is unavailable.
        
        Side Effects:
            Invokes the Canvas subgraph, which may update or persist Canvas-related process
            artifacts.
        """
        if canvas_subgraph is None or not state.get("bpmn_model_id"):
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "Non riesco ad aprire il canvas di questo processo: manca il modello BPMN "
                            "collegato. Creiamolo prima di lavorare sul disegno."
                        )
                    )
                ],
                "delegation_events": [
                    {
                        "target": "canvas_macro",
                        "status": "blocked",
                        "reason": "missing bpmn_model_id or canvas graph",
                    }
                ],
            }

        payload = state.get("delegation_payload") or {}
        # La versione di conoscenza che il Process Agent sta consegnando. Non e'
        # un dato in piu': e' cio' che rende l'handoff verificabile. Il Canvas
        # rilegge lo stesso stato dal database, ma parte dichiaratamente da
        # questa versione, quindi "il disegno viene da V17" si puo' dimostrare e
        # una V18 comparsa nel frattempo si vede.
        snapshot = build_process_snapshot(state["process_id"]) if state.get("process_id") else None
        result = canvas_subgraph.invoke(
            {
                "messages": state.get("messages") or [],
                "scope_type": "canvas",
                "scope_key": state.get("scope_key"),
                "project_id": state.get("project_id"),
                "process_id": state.get("process_id"),
                "bpmn_model_id": state.get("bpmn_model_id"),
                "process_name": state.get("process_name"),
                "current_bpmn_xml": None,
                "canvas_run_snapshot_id": snapshot.snapshot_id if snapshot else None,
                "goal": payload.get("goal") or state.get("goal"),
                "intent": payload.get("intent") or state.get("intent"),
                "next_action": payload.get("next_action") or state.get("next_action"),
                "workflow_scope": payload.get("workflow_scope") or state.get("workflow_scope"),
            },
            config=config,
        )

        return {
            "messages": result.get("messages") or [],
            "saved_bpmn_xml": result.get("saved_bpmn_xml") or state.get("saved_bpmn_xml"),
            "routing_trace": result.get("routing_trace") or [],
            "canvas_handoff_payload": snapshot.as_handoff_payload() if snapshot else None,
            "delegation_events": [
                {
                    "target": "canvas_macro",
                    "status": result.get("canvas_loop_status") or "completed",
                    "run_status": result.get("canvas_run_status"),
                    "canvas_route": result.get("canvas_route"),
                    "handoff_snapshot_id": snapshot.snapshot_id if snapshot else None,
                    "handoff_snapshot_label": snapshot.label if snapshot else None,
                    "reason": state.get("delegation_reason"),
                }
            ],
        }

    return delegate_to_canvas_macro


def build_process_subgraph(
    tools: list,
    llm,
    llm_with_tools,
    build_context_messages,
    canvas_subgraph=None,
):
    """
    Builds and compiles the process orchestration graph.
    
    The graph routes requests through context loading, process assistance, specialist
    subgraphs, clarification, or Canvas delegation, and enforces iteration and
    termination transitions for specialist workflows.
    
    Args:
        tools (list): Tools available to the process macro-agent.
        llm: Language model used for routing and process assistance.
        llm_with_tools: Language model configured for tool-enabled process assistance.
        build_context_messages: Callback that builds context messages for agent
            invocations.
        canvas_subgraph: Optional compiled Canvas graph used for delegation.
    
    Returns:
        A compiled process workflow graph.
    
    Side Effects:
        Constructs subgraphs and binds language-model tools during graph
        construction. Does not execute the workflow or persist process artifacts.
    """
    process_macro_agent = build_tool_chat_subgraph(
        state_schema=ProcessState,
        tools=tools,
        llm_with_tools=llm_with_tools,
        build_context_messages=build_context_messages,
        subgraph_contract=PROCESS_SUBGRAPH_CONTRACT + "\n\n" + tool_prompt_block(tools),
        agent_node_name="process_macro_agent",
        tool_node_name="process_macro_tools",
    )

    workflow = StateGraph(ProcessState)
    workflow.add_node("load_process_context", load_process_context)
    workflow.add_node("process_router", build_process_router(llm))
    workflow.add_node("process_macro_agent", process_macro_agent)
    workflow.add_node(
        "discovery_subgraph",
        build_discovery_subgraph(
            llm_with_tools=llm.bind_tools(discovery_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "evidence_subgraph",
        build_evidence_subgraph(
            llm_with_tools=llm.bind_tools(evidence_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "modeling_subgraph",
        build_modeling_subgraph(
            llm_with_tools=llm.bind_tools(modeling_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node("delegate_to_canvas_macro", build_canvas_delegation_node(canvas_subgraph))
    workflow.add_node("ask_process_clarification", ask_process_clarification)
    workflow.add_node("evaluate_process_iteration", evaluate_process_iteration)
    workflow.add_node("process_report", build_process_report(llm))

    workflow.add_edge(START, "load_process_context")
    workflow.add_edge("load_process_context", "process_router")
    workflow.add_conditional_edges(
        "process_router",
        selected_process_route,
        {
            "direct": "process_macro_agent",
            "discovery": "discovery_subgraph",
            "evidence": "evidence_subgraph",
            "modeling": "modeling_subgraph",
            "delegate_canvas": "delegate_to_canvas_macro",
            "clarification": "ask_process_clarification",
        },
    )
    workflow.add_edge("process_macro_agent", END)
    # Specialist tools write their judgments into typed state as they run, so the
    # loop evaluation below already sees what the pass produced.
    workflow.add_edge("discovery_subgraph", "evaluate_process_iteration")
    workflow.add_edge("evidence_subgraph", "evaluate_process_iteration")
    workflow.add_edge("modeling_subgraph", "evaluate_process_iteration")
    workflow.add_conditional_edges(
        "evaluate_process_iteration",
        selected_process_loop_transition,
        {
            "continue": "load_process_context",
            # Finito il giro, una risposta sola: le passate hanno lavorato in
            # silenzio proprio perche' a parlare sia questo nodo.
            "end": "process_report",
        },
    )
    workflow.add_edge("process_report", END)
    workflow.add_edge("delegate_to_canvas_macro", END)
    workflow.add_edge("ask_process_clarification", END)

    return workflow.compile()
