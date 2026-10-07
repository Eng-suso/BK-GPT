import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph, MessagesState

from backend.agent_checkpoint import get_checkpointer

from backend.agents.context_budget import count_tokens
from backend.agents.primary_scope import build_scope_system_prompt, tool_scope_type
from backend.graphs.canvas_edit import build_canvas_subgraph
from backend.graphs.consulting import build_consulting_subgraph
from backend.graphs.process import build_process_subgraph
from backend.graphs.project import build_project_subgraph
from backend.bpmn import BPMNSemanticModel
from backend.schemas.chat import (
    DEFAULT_REASONING_EFFORT,
    PROVIDER_REASONING_EFFORT,
    ReasoningEffort,
)
from backend.process_understanding import (
    ProcessUnderstanding,
    ProcessUnderstandingDiagnostics,
    ProcessUnderstandingQualityReport,
)
from backend.llm import TRANSIENT_PROVIDER_ERRORS, LlmTask, chat_client
from backend.settings import (
    ALLOWED_MODELS,
    DEFAULT_OPENAI_MODEL,
    settings,
)
from backend.tools import tools_by_scope
from backend.memory.consultant_context_classifier import (
    classify_and_select_context,
    format_classification_context,
)
from backend.memory.procedural.playbook_context import build_playbook_context
from backend.memory.procedural.skill_loader import recent_user_text
from backend.llm_streaming import stream_to_text
from backend.services import degradation_counters


# Il nodo che instrada la richiesta. E' una costante e non una stringa sparsa
# perche' il registro dei consumi ci appoggia sopra un compito suo
# (`CONTEXT_ROUTING`): rinominare il nodo senza accorgersene farebbe ricadere
# la spesa dell'instradamento dentro quella del turno, in silenzio.
CONTEXT_ROUTER_NODE = "classify_and_select_context"

PROCEDURAL_MEMORY_PATH = Path(__file__).parent / "memory" / "procedural" / "how_to_act.md"
RECENT_MESSAGE_LIMIT = 8
RECENT_MESSAGE_SCAN_LIMIT = 24
SUMMARY_TRIGGER_MESSAGE_COUNT = 10
SUMMARY_KEEP_RECENT_MESSAGES = 6
# Anche pochi messaggi possono pesare molto (il risultato di un tool): oltre
# questi token di storia il riassunto parte comunque.
SUMMARY_TRIGGER_TOKENS = 24_000
# Il ripiego quando il modello di riassunto non risponde: un estratto, non un
# riassunto, e con un tetto, perche' finisce in ogni prompt successivo.
FALLBACK_LINE_CHARS = 300
FALLBACK_TOTAL_CHARS = 4_000
# Il tetto del riassunto intero quando ci si aggiunge un estratto: con il
# provider giu' per piu' turni gli estratti si accumulerebbero senza fine.
FALLBACK_SUMMARY_MAX_CHARS = 12_000
_OMITTED_EXTRACTS = "\n[... estratti precedenti omessi ...]"
# Il tetto del riassunto del modello: finisce in ogni prompt successivo, e un
# testo oltre questa misura non e' un riassunto (il modello che ripete la
# trascrizione). Oltre, si ripiega sull'estratto.
SUMMARY_MAX_TOKENS = 2_000

logger = logging.getLogger(__name__)


class ConsultantState(MessagesState):
    scope_type: str
    scope_key: str
    # Arrivano dal runtime con la richiesta, non dal modello. Dichiarati qui
    # perche' lo schema dello state e' il contratto di cio' che un nodo puo'
    # leggere: `pending_action` in particolare e' l'azione distruttiva che il
    # thread ha lasciato in sospeso, ed e' il motivo per cui una conferma non
    # va piu' ricostruita dal testo del turno.
    chat_mode: str
    # La postura scelta dal consulente ("auto" se lascia fare a DeliR) e quella
    # che il router ha usato davvero: la UI mostra la seconda.
    posture: str
    detected_posture: str | None
    attachments: list
    pending_action: dict | None
    project_id: str | None
    process_id: str | None
    bpmn_model_id: str | None
    process_name: str | None
    current_bpmn_xml: str | None
    process_understanding: ProcessUnderstanding | None
    process_understanding_diagnostics: ProcessUnderstandingDiagnostics | None
    process_quality_report: ProcessUnderstandingQualityReport | None
    bpmn_semantic_model: BPMNSemanticModel | None
    readiness_score: int | None
    missing_information: list[str]
    saved_bpmn_xml: str | None
    effective_bpmn_xml: str | None
    effective_bpmn_xml_source: str | None
    running_summary: str
    summarized_message_count: int
    consultant_context_category: str
    consultant_context_confidence: float
    memory_type: str
    should_save_memory: bool
    suggested_memory_category: str | None
    consultant_context_reason: str
    active_skill_names: list[str]
    skill_selection_reason: str
    active_skill_context: str

def load_procedural_memory() -> str:
    return PROCEDURAL_MEMORY_PATH.read_text(encoding="utf-8").strip()


def message_role(message) -> str:
    return str(getattr(message, "type", None) or getattr(message, "role", "") or "")


def ai_tool_call_ids(message) -> set[str]:
    tool_calls = getattr(message, "tool_calls", None) or []
    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    raw_tool_calls = additional_kwargs.get("tool_calls") or []
    ids = set()

    for tool_call in [*tool_calls, *raw_tool_calls]:
        if isinstance(tool_call, dict):
            tool_id = tool_call.get("id")
        else:
            tool_id = getattr(tool_call, "id", None)

        if tool_id:
            ids.add(str(tool_id))

    return ids


def tool_message_id(message) -> str | None:
    tool_call_id = getattr(message, "tool_call_id", None)
    if tool_call_id:
        return str(tool_call_id)

    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
    tool_call_id = additional_kwargs.get("tool_call_id")
    return str(tool_call_id) if tool_call_id else None


def recent_context_messages(messages: list, limit: int = RECENT_MESSAGE_LIMIT) -> list:
    """
    Keep recent chat context valid for OpenAI tool-calling.
    A ToolMessage is legal only when its matching AI tool_call message is included
    immediately before the group; naive tail slicing can create orphan tool messages.
    """
    candidates = messages[-RECENT_MESSAGE_SCAN_LIMIT:]
    groups: list[list[Any]] = []
    index = 0

    while index < len(candidates):
        message = candidates[index]
        role = message_role(message)

        if role == "tool":
            index += 1
            continue

        tool_call_ids = ai_tool_call_ids(message) if role in {"ai", "assistant"} else set()

        if not tool_call_ids:
            groups.append([message])
            index += 1
            continue

        group = [message]
        matched_tool_ids: set[str] = set()
        scan = index + 1

        while scan < len(candidates) and message_role(candidates[scan]) == "tool":
            tool_id = tool_message_id(candidates[scan])
            if tool_id in tool_call_ids:
                matched_tool_ids.add(tool_id)
                group.append(candidates[scan])
            scan += 1

        if tool_call_ids.issubset(matched_tool_ids):
            groups.append(group)

        index = scan

    selected_groups: list[list[Any]] = []
    selected_count = 0

    for group in reversed(groups):
        group_size = len(group)
        if selected_groups and selected_count + group_size > limit:
            break

        selected_groups.append(group)
        selected_count += group_size

        if selected_count >= limit:
            break

    selected = []
    for group in reversed(selected_groups):
        selected.extend(group)

    return selected


def build_context_messages(state: ConsultantState):
    messages = [
        SystemMessage(content=load_procedural_memory()),
        SystemMessage(content=build_scope_system_prompt(state)),
    ]
    classification_context = format_classification_context(state)
    skill_context = state.get("active_skill_context")

    if classification_context:
        messages.append(SystemMessage(content=classification_context))

    if skill_context:
        messages.append(SystemMessage(content=skill_context))

    running_summary = state.get("running_summary")

    if running_summary:
        messages.append(
            SystemMessage(
                content=(
                    "Running conversation summary. Use this as compressed "
                    "context from earlier in the thread, not as a substitute "
                    "for the user's latest instructions.\n\n"
                    f"{running_summary}"
                )
            )
        )

    return messages + recent_context_messages(state["messages"])


def message_to_summary_line(message) -> str:
    role = getattr(message, "type", None) or getattr(message, "role", "message")
    content = getattr(message, "content", "")

    if isinstance(content, list):
        content = " ".join(
            str(item.get("text") or item.get("content") or item)
            if isinstance(item, dict)
            else str(item)
            for item in content
        )

    return f"{role}: {str(content).strip()}"


def build_summary_prompt(existing_summary: str, messages_to_summarize: list) -> list:
    transcript = "\n".join(
        line
        for line in (message_to_summary_line(message) for message in messages_to_summarize)
        if line.strip()
    )

    return [
        SystemMessage(
            content=(
                "You maintain the working-memory running summary for a consultant assistant. "
                "Update the summary using only the new conversation messages. Keep it concise, "
                "operational, and useful for future turns. Preserve confirmed decisions, current "
                "goal, constraints, open questions, pending actions, and important context. "
                "Do not invent facts."
            )
        ),
        HumanMessage(
            content=(
                "Existing running summary:\n"
                f"{existing_summary or 'None yet.'}\n\n"
                "New messages to fold into the summary:\n"
                f"{transcript}\n\n"
                "Return the updated running summary with these sections when relevant:\n"
                "Current objective:\n"
                "Confirmed decisions:\n"
                "Important context:\n"
                "Open questions:\n"
                "Pending actions:"
            )
        ),
    ]

def _message_tokens(message) -> int:
    """Token che il messaggio pesa nel prompt: testo e argomenti dei tool call.

    `additional_kwargs["tool_calls"]` e' la forma grezza degli stessi tool call:
    si conta solo quando manca quella interpretata, per non contarli due volte.
    """
    tokens = count_tokens(message_to_summary_line(message))
    tool_calls = getattr(message, "tool_calls", None) or (
        (getattr(message, "additional_kwargs", None) or {}).get("tool_calls")
    )
    if tool_calls:
        tokens += count_tokens(json.dumps(tool_calls, ensure_ascii=False, default=str))
    return tokens


def _history_tokens(messages: list) -> int:
    return sum(_message_tokens(message) for message in messages)


def _extract_summary(existing_summary: str, messages: list) -> str:
    """Il ripiego deterministico: le righe dei messaggi tolti, accorciate.

    Dichiara di essere un estratto: il modello del turno dopo non deve
    leggerlo come una sintesi ragionata.
    """
    lines = []
    for message in messages:
        line = message_to_summary_line(message)
        lines.append(line if len(line) <= FALLBACK_LINE_CHARS else line[:FALLBACK_LINE_CHARS] + "...")
    extract = "\n".join(lines)
    if len(extract) > FALLBACK_TOTAL_CHARS:
        extract = "..." + extract[-FALLBACK_TOTAL_CHARS:]
    block = (
        "[Riassunto automatico non disponibile in questo turno: segue un estratto "
        f"dei {len(messages)} messaggi piu' vecchi, non una sintesi.]\n" + extract
    )
    # Il riassunto intero ha un tetto. Del precedente si tiene la testa (la
    # sintesi del modello, se c'e') e si omettono gli estratti di mezzo,
    # dichiarandolo; l'estratto nuovo entra intero.
    previous = existing_summary.strip()
    room = FALLBACK_SUMMARY_MAX_CHARS - len(block) - len("\n\n")
    if len(previous) > room:
        keep = room - len(_OMITTED_EXTRACTS)
        previous = previous[:keep] + _OMITTED_EXTRACTS if keep > 0 else ""
    return "\n\n".join(part for part in (previous, block) if part)


def _summary_rejection(summary_text: str) -> Literal["empty_summary", "oversized_summary"] | None:
    """Perche' il riassunto del modello non puo' entrare nello stato, o None."""
    if not summary_text.strip():
        return "empty_summary"
    if count_tokens(summary_text) > SUMMARY_MAX_TOKENS:
        return "oversized_summary"
    return None


def summarize_history(state: dict, summarize: Callable[[str, list], str]) -> dict:
    """Comprime la storia del thread quando e' troppo lunga, in numero o in token.

    `summarize(riassunto_esistente, messaggi)` produce il nuovo riassunto col
    modello. Se il provider ha un guasto transitorio (`TRANSIENT_PROVIDER_ERRORS`)
    o il testo non passa la validazione (vuoto, oltre `SUMMARY_MAX_TOKENS`), il
    turno non cade: il riassunto diventa un estratto
    dichiarato, contato in `degradation_counters`, e i messaggi vecchi escono
    comunque dallo stato, che altrimenti crescerebbe a ogni turno. Ogni altro
    errore (`OperationNotOpen`, un difetto nostro) si propaga.
    """
    messages = state["messages"]
    cutoff = max(len(messages) - SUMMARY_KEEP_RECENT_MESSAGES, 0)
    summarized_message_count = state.get("summarized_message_count", 0)
    if cutoff <= summarized_message_count:
        return {}
    messages_to_summarize = messages[summarized_message_count:cutoff]

    # La soglia in token misura la stessa fetta che il riassunto toglie: gli
    # ultimi messaggi restano interi comunque, e contarli farebbe ripartire il
    # riassunto a ogni turno senza ridurre nulla.
    too_many = len(messages) > SUMMARY_TRIGGER_MESSAGE_COUNT
    if not too_many and _history_tokens(messages_to_summarize) <= SUMMARY_TRIGGER_TOKENS:
        return {}

    existing = state.get("running_summary", "") or ""
    try:
        summary_text = summarize(existing, messages_to_summarize)
    except TRANSIENT_PROVIDER_ERRORS as exc:
        # Il riassunto e' manutenzione: un guasto del provider non fa cadere il
        # turno. Solo quello: un difetto nostro si propaga.
        logger.error("riassunto del thread fallito: ripiego su un estratto", exc_info=True)
        degradation_counters.bump("thread_summary", "fallback_extract", detail=type(exc).__name__)
        summary_text = _extract_summary(existing, messages_to_summarize)
    else:
        # L'uscita del modello e' non fidata: si valida prima che diventi stato.
        rejection = _summary_rejection(summary_text)
        if rejection is not None:
            logger.error("riassunto del thread scartato (%s): ripiego su un estratto", rejection)
            degradation_counters.bump("thread_summary", rejection)
            summary_text = _extract_summary(existing, messages_to_summarize)

    # Dopo il riassunto i messaggi vecchi escono dal checkpoint: il loro
    # contenuto vive in running_summary, e lo stato non cresce senza limite.
    # Uno senza id non si puo' togliere: resta in testa, e il contatore lo
    # salta al giro dopo invece di riassumerlo una seconda volta.
    summarized = messages[:cutoff]
    remove_ops = [RemoveMessage(id=m.id) for m in summarized if getattr(m, "id", None)]
    still_in_state = len(summarized) - len(remove_ops)
    if still_in_state:
        logger.warning("riassunto del thread: %d messaggi senza id restano nello stato", still_in_state)
    return {
        "running_summary": summary_text.strip(),
        "summarized_message_count": still_in_state,
        **({"messages": remove_ops} if remove_ops else {}),
    }


def normalize_model_name(model_name: str | None = None) -> str:
    if not model_name:
        return settings.openai_model

    model_name = model_name.strip()

    if model_name in ALLOWED_MODELS:
        return model_name

    return DEFAULT_OPENAI_MODEL


def build_agent(
    model_name: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
):
    """
    Build and compile the consultant workflow for a selected language model.
    
    Args:
        model_name (str | None): Untrusted requested model identifier. It is normalized
            against the configured allowed models before use; omitted values use the
            configured or default model.
        reasoning_effort: Quanto il modello deve pensare prima di rispondere,
            scelto dal consulente per questo turno.
    
    Returns:
        A compiled workflow that summarizes conversations, selects context, routes
        requests by scope, and executes the corresponding subgraph. The workflow is
        configured with the application's checkpointer for state persistence.
    """
    selected_model = normalize_model_name(model_name)

    # I parametri li decide il profilo del compito, non questo file: erano le
    # stesse scelte del registro (`reasoning_effort="none"`, 512 token per
    # l'instradamento, i retry della chat) scritte una seconda volta, libere di
    # divergere senza che nessuno se ne accorgesse.
    llm = chat_client(
        LlmTask.CHAT_TURN,
        model_name=selected_model,
        streaming=True,
        tag="agent-runtime",
        # Il livello scelto dal consulente vale per il turno; l'instradamento
        # resta al suo profilo (`reasoning_effort="none"`).
        reasoning_effort=PROVIDER_REASONING_EFFORT[reasoning_effort],
    )
    context_router_llm = chat_client(
        LlmTask.CONTEXT_ROUTING,
        model_name=selected_model,
        streaming=False,
        tag="context-router",
    )
    # Il riassunto del thread e' manutenzione, non la risposta: resta al livello
    # del profilo anche quando il consulente chiede di ragionare a fondo.
    summary_llm = chat_client(
        LlmTask.CHAT_TURN,
        model_name=selected_model,
        streaming=True,
        tag="thread-summary",
    )

    def summarize_node(state: ConsultantState, config: RunnableConfig):
        def summarize(existing_summary: str, messages_to_summarize: list) -> str:
            return stream_to_text(
                summary_llm,
                build_summary_prompt(
                    existing_summary=existing_summary,
                    messages_to_summarize=messages_to_summarize,
                ),
                config=config,
            )

        return summarize_history(state, summarize)

    def classify_and_select_context_node(state: ConsultantState, config: RunnableConfig):
        result = classify_and_select_context(
            state["messages"],
            classifier_llm=context_router_llm,
            config=config,
        )
        # L2: accanto alle repo-skill, i playbook appresi 'active' pertinenti al
        # turno (Postgres, INV-12). Best-effort: mai rompere il turno per questo.
        try:
            playbook_context = build_playbook_context(
                recent_user_text(state["messages"]),
                project_id=state.get("project_id"),
            )
            if playbook_context:
                existing = result.get("active_skill_context") or ""
                joiner = "\n\n---\n\n" if existing else ""
                result["active_skill_context"] = existing + joiner + playbook_context
        except Exception:  # noqa: BLE001
            pass
        return result

    def route_scope(state: ConsultantState):
        return tool_scope_type(state.get("scope_type"))

    workflow = StateGraph(ConsultantState)
    workflow.add_node("summarize", summarize_node)
    workflow.add_node(CONTEXT_ROUTER_NODE, classify_and_select_context_node)
    workflow.add_node(
        "consulting_subgraph",
        build_consulting_subgraph(
            tools=tools_by_scope["consultant"],
            llm=llm,
            llm_with_tools=llm.bind_tools(tools_by_scope["consultant"]),
            build_context_messages=build_context_messages,
        ),
    )
    workflow.add_node(
        "project_subgraph",
        build_project_subgraph(
            tools=tools_by_scope["project"],
            llm=llm,
            llm_with_tools=llm.bind_tools(tools_by_scope["project"]),
            build_context_messages=build_context_messages,
        ),
    )
    canvas_subgraph = build_canvas_subgraph(
        tools=tools_by_scope["canvas"],
        llm=llm,
        llm_with_tools=llm.bind_tools(tools_by_scope["canvas"]),
        build_context_messages=build_context_messages,
    )
    workflow.add_node(
        "process_subgraph",
        build_process_subgraph(
            tools=tools_by_scope["process"],
            llm=llm,
            llm_with_tools=llm.bind_tools(tools_by_scope["process"]),
            build_context_messages=build_context_messages,
            # An authorized canvas handoff runs the Canvas Macro Agent for real
            # instead of telling the user to reopen the request elsewhere.
            canvas_subgraph=canvas_subgraph,
        ),
    )
    workflow.add_node("canvas_subgraph", canvas_subgraph)

    workflow.add_edge(START, "summarize")
    workflow.add_edge("summarize", CONTEXT_ROUTER_NODE)
    workflow.add_conditional_edges(
        CONTEXT_ROUTER_NODE,
        route_scope,
        {
            "consultant": "consulting_subgraph",
            "project": "project_subgraph",
            "process": "process_subgraph",
            "canvas": "canvas_subgraph",
        },
    )
    workflow.add_edge("consulting_subgraph", END)
    workflow.add_edge("project_subgraph", END)
    workflow.add_edge("process_subgraph", END)
    workflow.add_edge("canvas_subgraph", END)

    return workflow.compile(checkpointer=get_checkpointer())


_AGENT_CACHE: dict[str, Any] = {}


def get_agent(
    model_name: str | None = None,
    scope_type: str | None = None,
    reasoning_effort: ReasoningEffort = DEFAULT_REASONING_EFFORT,
):
    """Il grafo compilato per questo modello e questo impegno di ragionamento.

    L'impegno entra nella chiave della cache e non nella chiamata: e' una
    proprieta' dell'LLM, fissata quando il grafo viene costruito. Le varianti
    sono tre per modello, compilate la prima volta che qualcuno le chiede.

    Args:
        model_name: Il modello richiesto, non affidabile; viene normalizzato.
        scope_type: Lo scope della chat, per ora non cambia il grafo.
        reasoning_effort: Quanto pensare prima di rispondere, scelto dal
            consulente per questo turno.
    """
    selected_model = normalize_model_name(model_name)
    effort: ReasoningEffort = (
        reasoning_effort if reasoning_effort in PROVIDER_REASONING_EFFORT else DEFAULT_REASONING_EFFORT
    )
    cache_key = f"{selected_model}:{effort}"

    if cache_key not in _AGENT_CACHE:
        _AGENT_CACHE[cache_key] = build_agent(selected_model, effort)

    return _AGENT_CACHE[cache_key]
