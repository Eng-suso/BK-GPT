from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph

from backend import workspace_database
from backend.agents.process_snapshot import ProcessKnowledgeSnapshot, build_process_snapshot
from backend.bpmn import BPMNSemanticModel
from backend.process_understanding import ProcessUnderstanding
from backend.graphs.canvas_edit.nodes import load_canvas_context
from backend.graphs.canvas_edit.state import CanvasState
from backend.graphs.canvas_edit.subgraphs.construction import build_construction_subgraph, construction_tools
from backend.graphs.canvas_edit.subgraphs.layout import build_layout_subgraph
from backend.graphs.canvas_edit.subgraphs.patch_edit import build_patch_edit_subgraph, patch_edit_tools
from backend.graphs.canvas_edit.subgraphs.validation import build_validation_subgraph, validation_tools
from backend.graphs.canvas_edit.tools import CANVAS_TOOL_POLICY, canvas_macro_tools
from backend.graphs.common import (
    build_tool_chat_subgraph,
    canonical_semantic_context,
    latest_user_text,
    recent_conversation_digest,
)
from backend.graphs.consulting.skill_context import load_markdown_skills, tool_prompt_block
from backend.graphs.routing_contracts import (
    CanvasRoutingDecision,
    authorize_routing_decision,
    capability_menu,
    invalid_canvas_decision,
    parse_routing_decision,
    resolve_routing_decision,
)
from backend.workspace_services.bpmn_canvas_edit import validate_bpmn_xml
from backend.workspace_services.bpmn_canvas_validation import validate_canvas_against_process


SKILLS_DIR = Path(__file__).resolve().parent / "skills"
CANVAS_LOOP_MAX_ATTEMPTS = 2


def knowledge_drift(
    state: dict, current: ProcessKnowledgeSnapshot | None = None
) -> dict | None:
    """Il processo sa qualcosa che non sapeva quando questo run e' partito?

    Ha una causa sola, in questo disegno: il Canvas ha rimandato indietro una
    decisione con `raise_modeling_question`, e registrarla ha fatto salire la
    versione del piano. Da quel momento il disegno in corso descrive uno stato
    che non e' piu' quello ufficiale, e applicarlo lo renderebbe la verita' del
    processo - esattamente cio' che il confine esiste per impedire.

    Args:
        state: Lo stato del run, non affidabile. Serve `process_id` e la
            versione su cui il run e' partito.
        current: Lo snapshot corrente, quando chi chiama lo ha gia' letto. Lo
            snapshot carica fonti, testi e claim, e costruirlo due volte nello
            stesso nodo si paga due volte.

    Returns:
        Le due versioni a confronto, o ``None`` se la conoscenza e' ferma.

    Sola lettura.
    """
    started_on = state.get("canvas_run_snapshot_id")
    process_id = state.get("process_id")
    if not started_on or not process_id:
        return None

    if current is None:
        current = build_process_snapshot(process_id)
    if current is None or current.snapshot_id == started_on:
        return None
    return {
        "started_on": started_on,
        "current_snapshot_id": current.snapshot_id,
        "current_snapshot_label": current.label,
        "open_questions": [
            item.model_dump(mode="json")
            for item in current.open_questions
            if not item.answer
        ],
    }


def waiting_for_knowledge_state(drift: dict) -> dict:
    """Il run si ferma e dice cosa aspetta, invece di chiudere su dati vecchi."""
    pending = (drift.get("open_questions") or [None])[0]
    return {
        "canvas_loop_status": "blocked",
        "canvas_run_status": "waiting_for_user",
        "canvas_pending_question": pending,
        "process_snapshot_id": drift["current_snapshot_id"],
        "process_snapshot_label": drift["current_snapshot_label"],
        "blocking_conditions": [
            "Il piano del processo e' cambiato durante il lavoro sul canvas: "
            f"{drift['current_snapshot_label']} non e' la versione su cui questo "
            "disegno e' stato costruito."
        ],
        "canvas_task_log": [
            {
                "step": "knowledge_refresh",
                "status": "waiting_for_user",
                "owner": "canvas_loop",
                "summary": (
                    "Serve una decisione sul processo prima di chiudere il disegno: "
                    f"riprendo da {drift['current_snapshot_label']} quando arriva la risposta."
                ),
            }
        ],
    }


def _authoritative_semantic_context(
    state: dict, snapshot: ProcessKnowledgeSnapshot | None
) -> tuple[ProcessUnderstanding | None, BPMNSemanticModel | None]:
    """Il piano contro cui verificare il disegno, letto dall'autorita'.

    Lo stato del run puo' portarsi dietro un modello semantico vecchio o non
    portarne nessuno; lo snapshot del processo e' la versione che conta. Se
    l'autorita' non lo ha, si ricade sullo stato, ma la mancanza viene poi
    dichiarata da `_unverifiable_completion_issues` invece di sparire in un
    warning.

    Sola lettura.
    """
    if snapshot is not None and snapshot.bpmn_semantic_model:
        return canonical_semantic_context(snapshot.bpmn_semantic_model)
    return canonical_semantic_context(state.get("bpmn_semantic_model"))


def _unverifiable_completion_issues(
    state: dict,
    snapshot: ProcessKnowledgeSnapshot | None,
    empty_canvas_expected: bool,
) -> list[str]:
    """Cosa impedisce di dichiarare completata questa operazione.

    Non e' una verifica del disegno: e' la verifica che una verifica sia
    possibile. Un processo con evidenza agli atti e senza piano non offre niente
    contro cui confrontare il canvas, e "nessuna issue trovata" li' non significa
    "modello corretto" - significa "controllo non eseguito". Chiamarlo successo e'
    il modo in cui l'agente dichiarava writes che nessuno poteva smentire.

    Il controllo vale per la costruzione, che e' l'operazione che dichiara di aver
    modellato il processo. Una modifica locale su un canvas disegnato a mano si
    verifica contro l'XML e basta: pretendere li' un piano del processo sarebbe lo
    stesso difetto rovesciato, un fallimento dichiarato senza motivo.

    Sola lettura.
    """
    # La route con cui il run e' partito, non quella corrente: al primo giro di
    # correzione `evaluate_canvas_completion` riscrive `canvas_route` in
    # "patch_edit", e questo controllo spariva proprio nel momento in cui serviva.
    # Una costruzione che al primo tentativo non era verificabile diventava, al
    # secondo, una costruzione senza issue - cioe' completata.
    initial_route = state.get("canvas_initial_route") or state.get("canvas_route")
    if empty_canvas_expected or initial_route != "construction":
        return []

    if snapshot is None or snapshot.has_semantic_model or not snapshot.evidence_count:
        return []

    return [
        f"Il processo ha {snapshot.evidence_count} elementi di evidenza agli atti ma "
        "nessun piano strutturato: il canvas non e' confrontabile con cio' che "
        "sappiamo del processo, quindi non posso dichiararlo verificato."
    ]


def expects_empty_canvas(state: dict) -> bool:
    """Determine whether the requested end state is an empty canvas.
    
    Args:
        state (dict): Untrusted workflow state containing the expected canvas outcome.
    
    Returns:
        bool: `True` if the expected outcome is exactly ``"empty_canvas"``, `False`
            otherwise.
    """
    return state.get("canvas_expected_outcome") == "empty_canvas"


def _empty_canvas_completion_report(xml: str) -> dict:
    """
    Validate whether BPMN XML represents an empty canvas.
    
    Args:
        xml (str): Untrusted BPMN XML to validate.
    
    Returns:
        dict: A completion report containing validation status, technical validation
            details, flow-node and sequence-flow counts, issues, and warnings.
            The report is valid only when the XML is technically valid and contains
            no flow nodes or sequence flows.
    
    """
    validation = validate_bpmn_xml(xml)
    counts = validation.get("counts") or {}
    flow_nodes = int(counts.get("flow_nodes") or 0)
    sequence_flows = int(counts.get("sequence_flows") or 0)
    is_empty = flow_nodes == 0 and sequence_flows == 0
    issues = [] if is_empty and validation.get("valid") else (validation.get("issues") or ["Il canvas non e' vuoto."])
    return {
        "valid": bool(is_empty and validation.get("valid")),
        "technical": validation,
        "issues": issues,
        "warnings": [],
        "counts": {
            "flow_nodes": flow_nodes,
            "sequence_flows": sequence_flows,
        },
    }


CANVAS_SUBGRAPH_CONTRACT = """
Canvas Macro Agent contract.

{tool_policy}

ProcessUnderstanding and BPMNSemanticModel are the semantic base models for
generated or structural BPMN canvas changes. The live canvas XML is still the
source of truth for inspection and local patching.

Distinguish local patching from structural construction:
- local patch/edit: small deterministic changes to labels, documentation,
  element creation/removal, owners, lanes, or sequence flow connections.
- construction: build or rebuild a significant section of the canvas from
  ProcessUnderstanding/BPMNSemanticModel, discovery and evidence context.
- layout: repair visual readability without changing business semantics.
- validation: inspect XML and semantic coverage without mutating the model.

The macro agent should route work to a subagent whenever the request is not a
small read-only answer. It should not freely replace BPMN XML.

When answering the user, speak like a senior process consultant, not like a
developer. Prefer business words: passaggio, ruolo responsabile, punto di
decisione, documento, punto da verificare, problema da correggere. Do not expose
XML, ids, sourceRef, targetRef, BPMNSemanticModel, ProcessUnderstanding, DI,
node, gateway or sequenceFlow unless the user explicitly asks for technical BPMN
details.

{skill_context}

{tool_prompts}
""".format(
    tool_policy=CANVAS_TOOL_POLICY,
    skill_context=load_markdown_skills(SKILLS_DIR),
    tool_prompts=tool_prompt_block(canvas_macro_tools),
).strip()


CANVAS_ROUTER_PROMPT_TEMPLATE = """
You are the Canvas graph router for DeliR.
You are the reasoning layer, not the execution controller.
Propose exactly one route for the latest user request using canvas state, process
semantic context, traceability memory needs and ownership.

Capabilities you may propose:
{capability_menu}

Return structured output matching the CanvasRoutingDecision schema.
Set goal, intent, next_action and suggested_capability separately.
Set expected_canvas_outcome to empty_canvas when the request is satisfied only by
a canvas with no remaining elements or connections, and to updated_model in every
other case. The runtime verifies that outcome deterministically once the work is
done, so declare the end state you actually intend.
For small changes, still consider semantic context and traceability memory before
proposing patch_edit; do not treat local as context-free.
When you propose construction, set construction_kind to what the request actually
is: full_from_plan when the user asks to draw or redraw the process from what the
project already knows ("genera il BPMN", "disegna il processo", "rifai la mappa"),
partial_change when only a part of the existing drawing changes, and
from_user_description when the request carries a raw process description the user
just wrote and there is no plan yet. full_from_plan runs as a deterministic
command: the plan is compiled, validated, laid out and saved without another
agent pass, so do not choose it for a partial edit.
When has_prepared_preview_ready_to_apply is true and the user asks to apply, insert,
save or draw it ("inseriscila nel canvas", "salvala", "vai"), that is not an
ambiguous request: route to construction and apply the prepared preview. Asking
what to insert when a preview is already waiting is the wrong answer.
""".strip()


def canvas_router_prompt(chat_mode: str | None = None) -> str:
    """Build the canvas routing prompt for the specified chat mode.
    
    Args:
        chat_mode: Optional chat mode used to restrict the available canvas capabilities.
    
    Returns:
        The routing prompt with the capability menu for the selected chat mode.
    """
    return CANVAS_ROUTER_PROMPT_TEMPLATE.format(capability_menu=capability_menu("canvas", chat_mode))



def canvas_routing_state(
    decision: CanvasRoutingDecision,
    *,
    user_request: str = "",
    state: dict | None = None,
    parse_source: str = "structured",
    parse_error: str | None = None,
) -> dict:
    """Build the authorized canvas routing state for a workflow run.
    
    The resulting state preserves the proposed and authorized routing decision, initializes
    loop tracking, records routing and delegation traces, and carries forward the saved
    BPMN XML when available. It enforces the canvas owner and initializes an active loop
    only for patch editing, construction, or layout routes. This function does not persist
    state or perform external side effects.
    
    Args:
        decision: The router decision, treated as untrusted input before authorization.
        user_request: The original user request, treated as untrusted input.
        state: Existing workflow state used to preserve the saved BPMN XML.
        parse_source: Source category for the parsed routing decision.
        parse_error: Parsing error details associated with the decision, if any.
    
    Returns:
        A dictionary containing authorized routing metadata, workflow control fields,
        delegation information, trace events, and an initialized canvas task log.
    """
    authorization = authorize_routing_decision(
        owner="canvas",
        decision=decision,
        state=state,
        parse_source=parse_source,
        parse_error=parse_error,
    )
    route = authorization["route"]
    target = authorization["target"]
    reason = decision.reason or decision.reasoning_summary or "Canvas router decision."
    expected_result = decision.expected_result or ""
    canvas_mode = decision.canvas_mode or ("clarification" if route == "clarification" else route)
    canvas_objective = decision.canvas_objective or decision.goal or expected_result or None
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
        "owner": "canvas",
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
        "canvas_route": route,
        # La route del run, che non cambia. `canvas_route` invece si riscrive
        # durante il loop di correzione, e i controlli che devono sapere *come il
        # run e' nato* leggono questa.
        "canvas_initial_route": route,
        "canvas_mode": canvas_mode,
        "canvas_objective": canvas_objective,
        "canvas_expected_outcome": decision.expected_canvas_outcome,
        "canvas_construction_kind": decision.construction_kind,
        "canvas_loop_status": "running" if route in {"patch_edit", "construction", "layout"} else None,
        "canvas_loop_attempt": 0,
        "canvas_loop_max_attempts": CANVAS_LOOP_MAX_ATTEMPTS,
        "canvas_initial_saved_bpmn_xml": state.get("saved_bpmn_xml") if state else None,
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
        "canvas_task_log": [
            {
                "step": "route",
                "status": "completed",
                "owner": "canvas_router",
                "route": route,
                "summary": reason,
            }
        ],
    }


def parse_canvas_router_json(content: str, user_request: str = "", state: dict | None = None) -> dict:
    decision, parse_source, parse_error = parse_routing_decision(
        content,
        CanvasRoutingDecision,
        invalid_canvas_decision,
    )
    return canvas_routing_state(
        decision,
        user_request=user_request,
        state=state,
        parse_source=parse_source,
        parse_error=parse_error,
    )


def build_canvas_router(llm):
    """
    Create a routing function backed by the supplied language model.
    
    The returned function routes the latest canvas request into authorized workflow
    state. Missing user requests are routed directly, and routing or parsing
    failures produce an invalid decision without propagating the underlying
    exception. The function does not persist data or otherwise modify external
    state.
    
    Args:
        llm: Language model used to classify canvas requests.
    
    Returns:
        A function that accepts canvas state and runnable configuration and returns
        authorized canvas routing state.
    """
    def route_canvas_intent(state: CanvasState, config: RunnableConfig) -> dict:
        """
        Route the latest canvas request to the appropriate workflow handler.
        
        The function treats missing user text as a direct request and converts routing
        or parsing failures into an invalid routing decision without propagating the
        underlying exception. It does not persist state or perform external
        side effects beyond invoking the configured routing model.
        
        Args:
            state (CanvasState): Untrusted workflow state and user-provided context
                used to determine the routing decision.
            config (RunnableConfig): Runtime configuration for the routing model.
        
        Returns:
            dict: Authorized canvas routing state containing the selected route,
                routing metadata, and the original user request.
        """
        user_text = latest_user_text(state)
        if not user_text:
            return parse_canvas_router_json(
                '{"route":"direct","confidence":0,"reason":"No user message available."}'
            )

        try:
            decision, parse_source, parse_error = resolve_routing_decision(
                owner="canvas",
                llm=llm,
                model=CanvasRoutingDecision,
                messages=[
                    SystemMessage(content=canvas_router_prompt(state.get("chat_mode"))),
                    HumanMessage(
                        content=(
                            "Active scope: canvas\n\n"
                            f"project_id: {state.get('project_id')}\n"
                            f"process_id: {state.get('process_id')}\n"
                            f"bpmn_model_id: {state.get('bpmn_model_id')}\n"
                            f"process_name: {state.get('process_name')}\n"
                            f"readiness_score: {state.get('readiness_score')}\n"
                            f"missing_information: {state.get('missing_information') or []}\n"
                            f"has_process_understanding: {bool(state.get('process_understanding'))}\n"
                            f"has_bpmn_semantic_model: {bool(state.get('bpmn_semantic_model'))}\n"
                            f"has_effective_bpmn_xml: {bool(state.get('effective_bpmn_xml'))}\n"
                            f"effective_bpmn_xml_source: {state.get('effective_bpmn_xml_source')}\n"
                            f"has_prepared_preview_ready_to_apply: {bool(state.get('canvas_preview_xml'))}\n\n"
                            "Recent conversation (resolve references against this):\n"
                            f"{recent_conversation_digest(state)}\n\n"
                            "Latest user request:\n"
                            f"{user_text}"
                        )
                    ),
                ],
                config=config,
                invalid_factory=invalid_canvas_decision,
                state=state,
            )
        except Exception:
            decision = invalid_canvas_decision("Structured router failed unexpectedly.")
            parse_source = "invalid"
            parse_error = "Structured router failed unexpectedly."

        return canvas_routing_state(
            decision,
            user_request=user_text,
            state=state,
            parse_source=parse_source,
            parse_error=parse_error,
        )

    return route_canvas_intent


def draft_command_applies(state: CanvasState) -> bool:
    """Questa costruzione si puo' fare senza un agente?

    Si', quando la richiesta e' «disegna il processo che conosciamo» e il piano
    esiste: compilare il piano in BPMN e' un lavoro deterministico che il
    compilatore fa da solo, e farlo fare a un subagente costava sei-otto
    chiamate al modello per riottenere lo stesso XML.

    No in tre casi, e sono tre casi veri:

    - c'e' un'anteprima gia' preparata in attesa di essere applicata: quella va
      applicata, non sostituita con una rigenerazione;
    - la richiesta cambia una parte del disegno (`partial_change`): rigenerare
      tutto cancellerebbe il lavoro intorno;
    - la richiesta porta una descrizione del processo scritta dall'utente
      (`from_user_description`): li' il piano va costruito, e non e' lavoro del
      comando.

    Sola lettura.
    """
    if state.get("canvas_route") != "construction":
        return False
    if state.get("canvas_construction_kind") not in {None, "full_from_plan"}:
        return False
    if state.get("canvas_preview_xml"):
        return False
    if expects_empty_canvas(state):
        return False
    snapshot = state.get("process_snapshot") or {}
    return bool(state.get("process_id") and (snapshot.get("bpmn_semantic_model") or snapshot.get("sources")))


def selected_canvas_route(state: CanvasState) -> str:
    if draft_command_applies(state):
        return "draft_command"
    return state.get("canvas_route") or "direct"


def generate_canvas_draft(state: CanvasState) -> dict:
    """«Genera BPMN» eseguito come comando: compila, valida, dispone, salva.

    Nessuna chiamata al modello quando il piano e' materializzato, nessuna
    dipendenza da Mem0 o dal knowledge graph, nessun secondo consenso chiesto
    all'utente: la richiesta di generare **e'** l'autorizzazione alla bozza. Cio'
    che resta aperto esce come punto da verificare accanto al disegno, non al
    posto del disegno.
    """
    from backend.workspace_services.bpmn_draft import generate_bpmn_draft

    process_id = state.get("process_id")
    if not process_id:
        return {
            "canvas_loop_status": "blocked",
            "canvas_run_status": "failed",
            "blocking_conditions": ["Missing prerequisite: process_id"],
            "messages": [
                AIMessage(
                    content=(
                        "Non riesco a generare il disegno: questo canvas non e' collegato "
                        "a un processo."
                    )
                )
            ],
        }

    result = generate_bpmn_draft(process_id)
    log_entry = {
        "step": "draft_command",
        "status": "completed" if result.ok else "failed",
        "owner": "canvas_draft_command",
        "summary": result.reason,
        "metrics": result.metrics,
    }

    if not result.ok:
        content = (
            f"Non ho generato il disegno. {result.reason}"
            if result.status == "failed"
            else result.reason
        )
        if result.issues:
            content += "\n\n" + "\n".join(f"- {item}" for item in result.issues[:5])
        return {
            "canvas_loop_status": "blocked",
            "canvas_run_status": "failed" if result.status == "failed" else "waiting_for_user",
            "canvas_draft_metrics": result.metrics,
            "blocking_conditions": result.issues or [result.reason],
            "messages": [AIMessage(content=content)],
            "canvas_task_log": [log_entry],
        }

    content = (
        f"Ho disegnato la bozza del processo dal piano {result.snapshot_label} "
        "e l'ho riletta dal canvas salvato."
    )
    if result.pending_verification:
        content += "\n\nPunti ancora da verificare, che restano aperti sul piano:\n" + "\n".join(
            f"- {item}" for item in result.pending_verification[:5]
        )

    return {
        "saved_bpmn_xml": result.xml,
        "effective_bpmn_xml": result.xml,
        "effective_bpmn_xml_source": "bpmn_draft_command",
        "current_bpmn_xml": None,
        "canvas_loop_status": "completed",
        "canvas_run_status": "done",
        "canvas_draft_metrics": result.metrics,
        "canvas_warnings": result.pending_verification,
        "validation_report": {
            "process_snapshot_id": result.snapshot_id,
            "process_snapshot_label": result.snapshot_label,
            "objective": state.get("canvas_objective") or "Generazione bozza BPMN dal piano",
            "xml_valid": True,
            "semantic_valid": True,
            "issues": [],
            "warnings": result.pending_verification,
            "next_actions": [],
        },
        "messages": [AIMessage(content=content)],
        "canvas_task_log": [log_entry],
    }


def refresh_canvas_context_after_work(state: CanvasState) -> dict:
    # Prima di rileggere il canvas si guarda se il processo e' cambiato: un
    # disegno corretto su conoscenza superata resta un disegno da rifare, e
    # portarlo avanti fino al salvataggio e' il modo in cui il canvas
    # diventerebbe la fonte al posto del processo.
    drift = knowledge_drift(state)
    if drift:
        return waiting_for_knowledge_state(drift)

    bpmn_model_id = state.get("bpmn_model_id")
    if not bpmn_model_id:
        return {
            "canvas_loop_status": "blocked",
            "blocking_conditions": ["Missing prerequisite: bpmn_model_id"],
            "canvas_task_log": [
                {
                    "step": "refresh",
                    "status": "blocked",
                    "owner": "canvas_loop",
                    "summary": "Impossibile ricaricare il canvas: bpmn_model_id mancante.",
                }
            ],
        }

    refreshed = load_canvas_context({**state, "current_bpmn_xml": None})
    if refreshed.get("effective_bpmn_xml"):
        refreshed["effective_bpmn_xml_source"] = "saved_backend_after_canvas_work"

    # Il subagente ha lavorato e il canvas salvato e' identico a quello di
    # partenza: qualunque cosa creda di aver fatto, non e' arrivata al database.
    # Prima questo caso finiva nel report finale con lo stato del giro ancora
    # "running", e usciva come "ho preparato il lavoro sul canvas" - una frase
    # che non dice ne' fatto ne' fallito. Un write che non si rilegge e' un
    # write che non c'e' stato.
    #
    # Un'anteprima in attesa di approvazione e' l'eccezione, e va tenuta
    # separata: li' non aver scritto e' il comportamento voluto, e chiamarlo
    # fallimento sarebbe lo stesso difetto rovesciato.
    # Come il run e' nato, non com'e' adesso: dopo il primo giro di correzione
    # `canvas_route` vale "patch_edit", e il controllo spariva dal momento in cui
    # una costruzione poteva ancora non aver scritto niente.
    if (
        (state.get("canvas_initial_route") or state.get("canvas_route")) == "construction"
        and not state.get("canvas_preview_xml")
        and refreshed.get("saved_bpmn_xml") == state.get("canvas_initial_saved_bpmn_xml")
    ):
        return {
            **refreshed,
            "current_bpmn_xml": None,
            "canvas_loop_status": "blocked",
            "canvas_run_status": "failed",
            "blocking_conditions": [
                "Il canvas salvato e' identico a quello di partenza: la costruzione "
                "non e' stata persistita."
            ],
            "canvas_task_log": [
                {
                    "step": "refresh",
                    "status": "failed",
                    "owner": "canvas_loop",
                    "summary": (
                        "Rileggendo il canvas dal backend non risulta nessuna modifica: "
                        "l'operazione non e' completata."
                    ),
                }
            ],
        }

    return {
        **refreshed,
        "current_bpmn_xml": None,
        "canvas_task_log": [
            {
                "step": "refresh",
                "status": "completed",
                "owner": "canvas_loop",
                "summary": "Canvas ricaricato dal backend dopo il lavoro del subagent.",
            },
            {
                "step": "verification",
                "status": "running",
                "owner": "validation_subgraph",
                "summary": "Verifica tecnica e semantica del canvas aggiornata.",
            },
        ],
    }


def route_after_canvas_work(state: CanvasState) -> str:
    """Select the next workflow stage after canvas work.
    
    Args:
        state (CanvasState): Untrusted workflow state containing routing, loop, model,
            review, and saved-XML information.
    
    Returns:
        str: The next stage identifier: ``"completion_report"`` for blocked,
            unchanged, or incomplete work; ``"evaluate_canvas_completion"`` for
            empty-canvas outcomes; or ``"layout_subgraph"`` when layout is needed.
    
    This function reads BPMN review data from the workspace database and does not
    persist changes or raise errors explicitly.
    """
    if state.get("canvas_loop_status") == "blocked":
        return "completion_report"

    if expects_empty_canvas(state):
        return "evaluate_canvas_completion"

    if state.get("canvas_route") != "construction":
        return "layout_subgraph"

    bpmn_model_id = state.get("bpmn_model_id")
    if not bpmn_model_id:
        return "completion_report"

    review = workspace_database.get_bpmn_review(bpmn_model_id)
    if not review:
        return "layout_subgraph"

    initial_xml = state.get("canvas_initial_saved_bpmn_xml")
    saved_xml = state.get("saved_bpmn_xml")
    if initial_xml == saved_xml:
        return "completion_report"

    return "layout_subgraph"


def route_after_canvas_layout(state: CanvasState) -> str:
    """Route the workflow after canvas layout processing.
    
    Args:
        state: Workflow state containing layout, loop, and expected canvas outcome data.
    
    Returns:
        The next workflow node: ``"completion_report"`` for blocked work,
        ``"evaluate_canvas_completion"`` for an intended empty canvas, or
        ``"validation_subgraph"`` otherwise.
    """
    if state.get("canvas_layout_status") == "blocked" or state.get("canvas_loop_status") == "blocked":
        return "completion_report"

    if expects_empty_canvas(state):
        return "evaluate_canvas_completion"

    return "validation_subgraph"


def evaluate_canvas_completion(state: CanvasState) -> dict:
    """
    Evaluate whether the saved BPMN canvas satisfies the requested outcome.
    
    The function requires a BPMN model identifier and saved BPMN XML. It verifies
    empty-canvas requests by checking that no BPMN elements remain; other requests
    are validated against the canonical semantic context. It records validation
    results and returns a completed, fixable, or blocked workflow state according
    to the validation issues and remaining attempts. This function reads the BPMN
    model from persistence but does not modify it.
    
    Args:
        state (CanvasState): Untrusted workflow state containing the BPMN model
            identifier, expected canvas outcome, semantic context, objective, and
            validation-attempt counters.
    
    Returns:
        dict: Workflow-state updates containing validation results, warnings,
            follow-up actions, task-log entries, and a loop status of
            ``"completed"``, ``"needs_fix"``, or ``"blocked"``.
    """
    # Una lettura sola dell'autorita' per tutto il nodo: lo snapshot carica fonti,
    # testi e claim, e serve sia al controllo di deriva sia alla verifica finale.
    process_id = state.get("process_id")
    snapshot = build_process_snapshot(process_id) if process_id else None

    drift = knowledge_drift(state, snapshot)
    if drift:
        return waiting_for_knowledge_state(drift)

    bpmn_model_id = state.get("bpmn_model_id")
    if not bpmn_model_id:
        return {
            "canvas_loop_status": "blocked",
            "canvas_run_status": "failed",
            "blocking_conditions": ["Missing prerequisite: bpmn_model_id"],
            "canvas_task_log": [
                {
                    "step": "completion_check",
                    "status": "blocked",
                    "owner": "canvas_loop",
                    "summary": "Non posso verificare il completamento senza bpmn_model_id.",
                }
            ],
        }

    # Read-after-write: cio' che si verifica e' cio' che il database ha, mai cio'
    # che lo stato del run ricorda di aver prodotto. La differenza fra le due
    # cose e' esattamente la differenza fra un canvas aggiornato e un canvas
    # dichiarato aggiornato.
    model = workspace_database.get_bpmn_model(bpmn_model_id)
    xml = (model or {}).get("xml")
    if not xml:
        return {
            "canvas_loop_status": "blocked",
            "canvas_run_status": "failed",
            "blocking_conditions": [
                "Nessun canvas persistito da verificare: rileggendo il modello dal "
                "backend non c'e' XML salvato."
            ],
            "canvas_task_log": [
                {
                    "step": "completion_check",
                    "status": "failed",
                    "owner": "canvas_loop",
                    "summary": "Non esiste un canvas salvato da verificare.",
                }
            ],
        }

    # Two end states, two checks. An emptied canvas has nothing left to compare
    # against the semantic model, so it is verified as "no elements remain";
    # anything else is verified against ProcessUnderstanding/BPMNSemanticModel.
    empty_canvas_expected = expects_empty_canvas(state)
    if empty_canvas_expected:
        validation = _empty_canvas_completion_report(xml)
    else:
        # Il piano contro cui si verifica e' quello dell'autorita', non quello
        # che lo stato del run si porta dietro: uno stato che si valida da solo
        # verifica di aver avuto l'intenzione giusta. Quando il piano manca del
        # tutto, la validazione semantica degradava a warning e un start -> end
        # tecnicamente valido usciva senza issue, cioe' "completato".
        process_understanding, bpmn_semantic_model = _authoritative_semantic_context(
            state, snapshot
        )
        validation = validate_canvas_against_process(
            xml=xml,
            process_understanding=process_understanding,
            bpmn_semantic_model=bpmn_semantic_model,
        )

    # Due famiglie di problemi, e solo una si corregge disegnando. "Il processo
    # ha evidenza e nessun piano" non e' un difetto del disegno: e' l'assenza del
    # metro. Mandarlo al patch agent gli chiede di riparare una cosa che non e'
    # sul canvas, brucia un tentativo e finisce bloccato lo stesso - con in mezzo
    # una passata che puo' solo peggiorare il disegno.
    fixable_issues = list(validation.get("issues") or [])
    unverifiable_issues = _unverifiable_completion_issues(
        state, snapshot, empty_canvas_expected
    )
    issues = [*fixable_issues, *unverifiable_issues]
    validation = {**validation, "issues": issues}
    warnings = validation.get("warnings") or []
    next_attempt = int(state.get("canvas_loop_attempt") or 0) + 1
    max_attempts = int(state.get("canvas_loop_max_attempts") or CANVAS_LOOP_MAX_ATTEMPTS)

    if not issues:
        return {
            "canvas_loop_status": "completed",
            "canvas_run_status": "done",
            "canvas_loop_attempt": next_attempt,
            "canvas_last_validation": validation,
            "validation_report": {
                # Quale stato del processo questo disegno rappresenta. Senza
                # questo, "il canvas e' aggiornato" non e' un'affermazione
                # verificabile: aggiornato rispetto a cosa.
                "process_snapshot_id": state.get("canvas_run_snapshot_id"),
                "process_snapshot_label": state.get("process_snapshot_label"),
                "objective": state.get("canvas_objective")
                or ("Svuotamento canvas" if empty_canvas_expected else "Verifica completamento canvas"),
                "xml_valid": bool(validation.get("technical", {}).get("valid", validation.get("valid"))),
                "semantic_valid": None
                if empty_canvas_expected
                else bool(validation.get("semantic_valid", validation.get("valid"))),
                "issues": [],
                "warnings": warnings,
                "next_actions": [],
                **({"completion_kind": "empty_canvas"} if empty_canvas_expected else {}),
            },
            "canvas_warnings": warnings,
            "canvas_next_actions": [],
            "canvas_task_log": [
                {
                    "step": "completion_check",
                    "status": "completed",
                    "owner": "canvas_loop",
                    "summary": "Canvas vuoto verificato rispetto alla richiesta di cancellazione."
                    if empty_canvas_expected
                    else "La richiesta risulta completata e il canvas non ha problemi bloccanti.",
                }
            ],
        }

    if fixable_issues and not unverifiable_issues and next_attempt < max_attempts:
        return {
            "canvas_route": "patch_edit",
            "canvas_loop_status": "needs_fix",
            "canvas_loop_attempt": next_attempt,
            "canvas_last_validation": validation,
            "validation_report": {
                "process_snapshot_id": state.get("canvas_run_snapshot_id"),
                "process_snapshot_label": state.get("process_snapshot_label"),
                "objective": state.get("canvas_objective") or "Correzione post-validazione canvas",
                "xml_valid": bool(validation.get("technical", {}).get("valid", validation.get("valid"))),
                "semantic_valid": False,
                "issues": issues,
                "warnings": warnings,
                "next_actions": issues,
            },
            "canvas_warnings": warnings,
            "canvas_next_actions": [
                {
                    "owner": "patch_edit_subgraph",
                    "action": "fix_validation_issues",
                    "issues": issues,
                }
            ],
            "canvas_task_log": [
                {
                    "step": "completion_check",
                    "status": "needs_fix",
                    "owner": "canvas_loop",
                    "summary": "La verifica ha trovato problemi correggibili: rientro nel patch agent.",
                    "issues": issues,
                }
            ],
        }

    return {
        "canvas_loop_status": "blocked",
        "canvas_run_status": "failed",
        "canvas_loop_attempt": next_attempt,
        "canvas_last_validation": validation,
        "validation_report": {
            "process_snapshot_id": state.get("canvas_run_snapshot_id"),
            "process_snapshot_label": state.get("process_snapshot_label"),
            "objective": state.get("canvas_objective") or "Verifica completamento canvas",
            "xml_valid": bool(validation.get("technical", {}).get("valid", validation.get("valid"))),
            "semantic_valid": False,
            "issues": issues,
            "warnings": warnings,
            "next_actions": issues,
        },
        "canvas_warnings": warnings,
        "canvas_next_actions": [
            {
                "owner": "user_or_consultant",
                "action": "review_blocking_canvas_issues",
                "issues": issues,
            }
        ],
        "blocking_conditions": issues,
        "canvas_task_log": [
            {
                "step": "completion_check",
                "status": "blocked",
                "owner": "canvas_loop",
                "summary": "La richiesta non e' ancora chiudibile dopo i tentativi automatici.",
                "issues": issues,
            }
        ],
    }


def route_after_canvas_completion_check(state: CanvasState) -> str:
    if state.get("canvas_loop_status") == "needs_fix":
        return "patch_edit_subgraph"

    return "completion_report"


def route_after_validation_subgraph(state: CanvasState) -> str:
    if state.get("canvas_loop_status") in {"running", "needs_fix"}:
        return "evaluate_canvas_completion"

    return "end"


def canvas_completion_report(state: CanvasState) -> dict:
    status = state.get("canvas_loop_status")
    run_status = state.get("canvas_run_status")
    validation = state.get("canvas_last_validation") or {}
    report = state.get("validation_report") or {}
    issues = report.get("issues") or validation.get("issues") or []
    warnings = report.get("warnings") or validation.get("warnings") or []

    if run_status == "waiting_for_user":
        # Il run non e' fallito e non e' finito: ha trovato una cosa che non
        # poteva decidere e l'ha rimandata a chi la decide. Dirlo cosi' e' la
        # differenza fra un agente che aspetta e uno che ha inventato.
        pending = state.get("canvas_pending_question") or {}
        question = str(pending.get("question") or "").strip()
        content = (
            "Mi serve una decisione tua prima di chiudere il disegno: l'ho registrata "
            "sul processo, cosi' resta parte di quello che sappiamo e non solo del canvas."
        )
        if question:
            content += f"\n\n{question}"
        options = [
            str(option.get("label") or "").strip()
            for option in pending.get("options") or []
            if str(option.get("label") or "").strip()
        ]
        if options:
            content += "\n\n" + "\n".join(f"- {option}" for option in options)
        return {
            "messages": [AIMessage(content=content)],
            "canvas_task_log": [
                {
                    "step": "final_report",
                    "status": "waiting_for_user",
                    "owner": "canvas_loop",
                    "summary": content,
                }
            ],
        }

    if status == "completed":
        if report.get("completion_kind") == "empty_canvas":
            content = "Canvas svuotato. Ho verificato che non ci siano piu' elementi o collegamenti visibili."
        else:
            # "Aggiornato" senza dire rispetto a quale stato del processo e'
            # un'affermazione senza referente: il consulente non ha modo di
            # verificarla, ed e' proprio cosi' che un successo dichiarato passava.
            snapshot_label = report.get("process_snapshot_label")
            content = "Operazione completata. Ho aggiornato il disegno e l'ho verificato"
            content += (
                f" contro il piano {snapshot_label} del processo."
                if snapshot_label
                else " contro il piano del processo."
            )
        if warnings and report.get("completion_kind") != "empty_canvas":
            content += "\n\nPunti da verificare non bloccanti:\n" + "\n".join(f"- {item}" for item in warnings[:5])
    elif status == "blocked":
        if run_status == "failed" and not issues:
            # Un fallimento di persistenza non e' "la richiesta non e' ancora
            # chiudibile": e' che non e' stato scritto niente, e va detto cosi'.
            content = (
                "Non ho completato l'operazione: rileggendo il canvas dal backend non "
                "risulta salvata nessuna modifica. Non te lo racconto come fatto."
            )
            blocking = state.get("blocking_conditions") or []
            if blocking:
                content += "\n\n" + "\n".join(f"- {item}" for item in blocking[:5])
        else:
            content = "Ho lavorato sul canvas, ma la verifica finale indica che la richiesta non e' ancora chiudibile."
            if issues:
                content += "\n\nProblemi da correggere:\n" + "\n".join(f"- {item}" for item in issues[:5])
    else:
        content = (
            "Ho preparato il lavoro sul canvas, ma non l'ho verificato: non posso "
            "dichiararlo completato. Serve approvazione o contesto aggiuntivo."
        )

    return {
        "messages": [AIMessage(content=content)],
        "canvas_task_log": [
            {
                "step": "final_report",
                "status": status or "pending",
                "owner": "canvas_loop",
                "summary": content,
            }
        ],
    }


def ask_canvas_clarification(state: CanvasState) -> dict:
    return {
        "canvas_run_status": "waiting_for_user",
        "messages": [
            AIMessage(
                content=state.get("clarification_question")
                or "Mi serve un chiarimento sul canvas o sulla modifica richiesta prima di procedere."
            )
        ],
    }


def build_canvas_subgraph(tools: list, llm, llm_with_tools, build_context_messages):
    canvas_macro_agent = build_tool_chat_subgraph(
        state_schema=CanvasState,
        tools=canvas_macro_tools,
        llm_with_tools=llm.bind_tools(canvas_macro_tools),
        build_context_messages=build_context_messages,
        subgraph_contract=CANVAS_SUBGRAPH_CONTRACT,
        agent_node_name="canvas_macro_agent",
        tool_node_name="canvas_macro_tools",
    )

    workflow = StateGraph(CanvasState)
    workflow.add_node("load_canvas_context", load_canvas_context)
    workflow.add_node("canvas_router", build_canvas_router(llm))
    workflow.add_node("canvas_macro_agent", canvas_macro_agent)
    workflow.add_node("refresh_canvas_context_after_work", refresh_canvas_context_after_work)
    workflow.add_node("evaluate_canvas_completion", evaluate_canvas_completion)
    workflow.add_node("canvas_completion_report", canvas_completion_report)
    workflow.add_node("layout_subgraph", build_layout_subgraph(llm=llm))
    workflow.add_node(
        "patch_edit_subgraph",
        build_patch_edit_subgraph(
            llm_with_tools=llm.bind_tools(patch_edit_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "construction_subgraph",
        build_construction_subgraph(
            llm_with_tools=llm.bind_tools(construction_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "validation_subgraph",
        build_validation_subgraph(
            llm_with_tools=llm.bind_tools(validation_tools),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node("ask_canvas_clarification", ask_canvas_clarification)
    workflow.add_node("generate_canvas_draft", generate_canvas_draft)

    workflow.add_edge(START, "load_canvas_context")
    workflow.add_edge("load_canvas_context", "canvas_router")
    workflow.add_conditional_edges(
        "canvas_router",
        selected_canvas_route,
        {
            "direct": "canvas_macro_agent",
            "patch_edit": "patch_edit_subgraph",
            # Il disegno dal piano non passa da un agente: e' una compilazione.
            "draft_command": "generate_canvas_draft",
            "construction": "construction_subgraph",
            "layout": "layout_subgraph",
            "validation": "validation_subgraph",
            "clarification": "ask_canvas_clarification",
        },
    )
    workflow.add_edge("canvas_macro_agent", END)
    workflow.add_edge("patch_edit_subgraph", "refresh_canvas_context_after_work")
    workflow.add_edge("construction_subgraph", "refresh_canvas_context_after_work")
    workflow.add_conditional_edges(
        "refresh_canvas_context_after_work",
        route_after_canvas_work,
        {
            "layout_subgraph": "layout_subgraph",
            "evaluate_canvas_completion": "evaluate_canvas_completion",
            "completion_report": "canvas_completion_report",
        },
    )
    workflow.add_conditional_edges(
        "layout_subgraph",
        route_after_canvas_layout,
        {
            "validation_subgraph": "validation_subgraph",
            "evaluate_canvas_completion": "evaluate_canvas_completion",
            "completion_report": "canvas_completion_report",
        },
    )
    workflow.add_conditional_edges(
        "validation_subgraph",
        route_after_validation_subgraph,
        {
            "evaluate_canvas_completion": "evaluate_canvas_completion",
            "end": END,
        },
    )
    workflow.add_conditional_edges(
        "evaluate_canvas_completion",
        route_after_canvas_completion_check,
        {
            "patch_edit_subgraph": "patch_edit_subgraph",
            "completion_report": "canvas_completion_report",
        },
    )
    workflow.add_edge("canvas_completion_report", END)
    workflow.add_edge("ask_canvas_clarification", END)
    # Il comando si verifica da solo (validazione, layout, rilettura dal
    # database): mandarlo nel loop di verifica del canvas rimetterebbe in mezzo
    # i subagenti che esiste per togliere.
    workflow.add_edge("generate_canvas_draft", END)

    return workflow.compile()
