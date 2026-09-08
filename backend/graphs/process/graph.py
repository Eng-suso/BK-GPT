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
    recent_conversation_digest,
)
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
        ]
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
                            f"has_saved_bpmn_xml: {bool(state.get('saved_bpmn_xml'))}\n\n"
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

Governance dell'evidenza - il punto su cui questa risposta si gioca:

- Una cosa detta da una sola persona e' cio' che quella persona riferisce, non
  un fatto accertato. Scrivi "Laura riferisce che...", "secondo Paolo...".
  "Confermato" si usa solo per cio' che due fonti indipendenti dicono allo
  stesso modo, o che un documento mostra.
- Tieni separato cio' che una persona sa da cio' che dichiara di non sapere:
  "su questo dice di non avere visibilita'" e' un'informazione, non un buco.
- Una contraddizione fra fonti si dichiara e resta aperta. Non la risolvi tu
  scegliendo la versione piu' plausibile.
- Non trasformare in "lacuna emersa" un tema di cui nessuno ha parlato. Se e'
  una tua ipotesi di indagine, va fra le cose da chiedere dopo, detta come
  domanda tua.
- Non aggiungere attori, soglie, sistemi o date che nelle fonti non ci sono.

Struttura la risposta cosi', senza intestazioni tecniche:
cosa ci hanno detto - cosa resta incerto - cosa si contraddice - cosa chiedere
dopo, e a chi.

Nessun nome interno di sistema, di agente o di passaggio: il consulente legge il
risultato del lavoro, non come e' organizzato.
""".strip()


def build_process_report(llm):
    """Il nodo che parla al consulente, uno solo per turno.

    Il giro di lavoro puo' durare piu' passate, e ogni specialista ne concludeva
    una in chat: il consulente si ritrovava quattro o cinque sintesi quasi
    identiche una dietro l'altra. Ora le passate lavorano in silenzio e qui si
    scrive la risposta, una volta, su quello che hanno prodotto.
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
        contradictions = state.get("contradictions") or []
        response = llm.invoke(
            [
                SystemMessage(content=PROCESS_REPORT_PROMPT),
                HumanMessage(
                    content=(
                        f"Processo: {state.get('process_name') or 'senza nome'}\n"
                        f"Richiesta del consulente:\n{latest_user_text(state)}\n\n"
                        f"Contraddizioni registrate: {contradictions or 'nessuna'}\n"
                        f"Cosa manca ancora: {state.get('missing_information') or []}\n\n"
                        f"Conclusioni delle passate di lavoro:\n{dossier}"
                    )
                ),
            ],
            config=config,
        )
        return {"messages": [response]}

    return write_process_report


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
            "delegation_events": [
                {
                    "target": "canvas_macro",
                    "status": result.get("canvas_loop_status") or "completed",
                    "canvas_route": result.get("canvas_route"),
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
