import logging

from langchain_core.messages import AIMessage
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, END, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


def message_text(message) -> str:
    """The readable text of one message, whatever shape the provider used."""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "\n".join(part for part in parts if part).strip()
    return str(content or "").strip()


def latest_user_text(state: dict) -> str:
    """Finds the text of the most recent human or user message.
    
    Args:
        state (dict): Untrusted conversation state containing an optional ``messages`` sequence.
    
    Returns:
        str: The message content, or an empty string when no human or user message is present.
    """
    for message in reversed(state.get("messages", [])):
        role = getattr(message, "type", None) or getattr(message, "role", "")
        if role in {"human", "user"}:
            return message_text(message)

    return ""


# What a router gets to read of the conversation before it decides. Runtime
# policy, not a model field: enough turns to resolve a reference, few enough
# that routing stays a cheap decision.
ROUTER_DIGEST_MAX_TURNS = 8
ROUTER_DIGEST_MAX_CHARS = 4_000
ROUTER_DIGEST_MAX_CHARS_PER_TURN = 700


def recent_conversation_digest(
    state: dict,
    *,
    max_turns: int = ROUTER_DIGEST_MAX_TURNS,
    max_chars: int = ROUTER_DIGEST_MAX_CHARS,
    max_chars_per_turn: int = ROUTER_DIGEST_MAX_CHARS_PER_TURN,
) -> str:
    """The tail of the conversation, in the form a router can route on.

    A router that sees only the latest user message cannot resolve "aggiungi il
    processo": the referent was named one turn earlier, often by the assistant
    itself, so the turn ended in "quale processo?" while the answer sat in the
    transcript (PROJECT-04). Tool traffic stays out - the router routes the
    conversation, not the tool trace.
    """
    turns: list[str] = []
    for message in reversed(state.get("messages", [])):
        role = getattr(message, "type", None) or getattr(message, "role", "")
        if role not in {"human", "user", "ai", "assistant"}:
            continue

        text = message_text(message)
        if not text:
            continue
        if len(text) > max_chars_per_turn:
            text = text[:max_chars_per_turn] + " [...]"

        speaker = "utente" if role in {"human", "user"} else "DeliR"
        turns.append(f"{speaker}: {text}")
        if len(turns) >= max_turns:
            break

    # `turns` is newest-first; keep the newest turns that fit and restore order.
    digest = ""
    for turn in turns:
        candidate = f"{turn}\n{digest}" if digest else turn
        if len(candidate) > max_chars:
            break
        digest = candidate

    return digest


def validated_model(model_cls, value):
    """Re-validate a stored payload against a Pydantic model.
    
    Args:
        model_cls: Pydantic model class used for validation.
        value: Untrusted stored payload to validate.
    
    Returns:
        A validated model instance, or ``None`` for empty or invalid payloads.
    
    The function catches Pydantic validation errors, logs a warning, and does not
    persist or modify the payload.
    """
    if not value:
        return None

    try:
        return model_cls.model_validate(value)
    except ValidationError as exc:
        logger.warning(
            "stored %s payload failed validation: %s",
            model_cls.__name__,
            exc,
        )
        return None


def artifact_is_present(value) -> bool:
    """Determine whether an artifact contains usable data.
    
    Args:
        value: Untrusted artifact value to evaluate. Pydantic model instances are
            considered present; other values follow their boolean truth value.
    
    Returns:
        `True` if the artifact is present, `False` otherwise.
    """
    if value is None:
        return False
    if isinstance(value, BaseModel):
        return True
    return bool(value)


def artifact_field(value, field: str):
    """Retrieve a named field from a validated artifact value.
    
    Args:
        value: Untrusted artifact value, either a Pydantic model or dictionary.
        field: Name of the field to retrieve.
    
    Returns:
        The field value, or `None` when the artifact is absent, unsupported, or does not contain the field.
    """
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return getattr(value, field, None)
    if isinstance(value, dict):
        return value.get(field)
    return None


def artifact_for_prompt(value):
    """
    Convert an artifact into a value suitable for inclusion in a prompt.
    
    Args:
        value: Untrusted artifact value to normalize.
    
    Returns:
        A JSON-compatible dictionary for a Pydantic model, the original truthy
        value otherwise, or an empty dictionary for falsy values.
    """
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value or {}


def canonical_semantic_context(semantic_model_payload):
    """
    Extract the validated process understanding and semantic model from a canonical BPMN payload.
    
    A payload is canonical only when it contains both a compilation plan and source process
    understanding. Invalid, legacy, or incomplete semantic-model payloads produce no context.
    An invalid embedded process understanding produces a `None` understanding alongside the
    validated semantic model.
    
    Args:
        semantic_model_payload: Untrusted stored payload to validate as a BPMN semantic model.
    
    Returns:
        A tuple containing the validated process understanding, or `None` if invalid, and the
        validated semantic model. Returns `(None, None)` when the semantic-model payload is
        invalid, legacy, or incomplete. No persistence is performed.
    """
    from backend.bpmn import BPMNSemanticModel
    from backend.process_understanding import ProcessUnderstanding

    semantic_model = validated_model(BPMNSemanticModel, semantic_model_payload)
    if not semantic_model:
        return None, None
    if not semantic_model.compilationPlan or not semantic_model.sourceProcessUnderstanding:
        return None, None

    understanding = validated_model(
        ProcessUnderstanding,
        semantic_model.sourceProcessUnderstanding,
    )
    return understanding, semantic_model


class ConversationState(MessagesState):
    # The user's chat mode for this turn (plan / edit / agent). It arrives from the
    # UI with the request, never from the model, and narrows which capabilities the
    # router may propose.
    chat_mode: str
    # L'azione distruttiva in attesa di conferma su questo thread (o None).
    # Precaricata dal runtime: il subgrafo la vede prima di leggere il "si'"
    # dell'utente, invece di dover indovinare a cosa si riferisse.
    pending_action: dict | None
    running_summary: str
    consultant_context_category: str
    consultant_context_confidence: float
    memory_type: str
    should_save_memory: bool
    suggested_memory_category: str | None
    consultant_context_reason: str
    active_skill_names: list[str]
    skill_selection_reason: str
    active_skill_context: str


def build_tool_chat_subgraph(
    state_schema,
    tools: list,
    llm_with_tools,
    build_context_messages,
    subgraph_contract: str | None = None,
    preload_node=None,
    agent_node_name: str = "chatbot",
    tool_node_name: str = "tools",
):
    def agent_node(state, config: RunnableConfig):
        messages = build_context_messages(state)

        if subgraph_contract:
            messages = [*messages, SystemMessage(content=subgraph_contract)]

        response = None

        for chunk in llm_with_tools.stream(messages, config=config):
            response = chunk if response is None else response + chunk

        return {"messages": [response or AIMessage(content="")]}

    workflow = StateGraph(state_schema)
    workflow.add_node(agent_node_name, agent_node)
    workflow.add_node(tool_node_name, ToolNode(tools))

    if preload_node is None:
        workflow.add_edge(START, agent_node_name)
    else:
        workflow.add_node("load_context", preload_node)
        workflow.add_edge(START, "load_context")
        workflow.add_edge("load_context", agent_node_name)

    workflow.add_conditional_edges(
        agent_node_name,
        tools_condition,
        {
            "tools": tool_node_name,
            "__end__": END,
        },
    )
    workflow.add_edge(tool_node_name, agent_node_name)
    return workflow.compile()
