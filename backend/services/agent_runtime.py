from __future__ import annotations

from contextlib import nullcontext
from queue import Empty, Queue
from threading import Lock
from threading import Thread
from typing import Any, Iterator
from uuid import UUID

from backend.agent import get_agent, normalize_model_name
from backend.agents.chat_mode import bind_active_mode
from backend.agents.primary_scope import agent_scope_state
from backend.agents.run_context import bind_active_thread
from backend.agents.scope_guard import bind_active_scope
from backend.llm_streaming import (
    INTERNAL_STREAM_METADATA_KEY,
    INTERNAL_STREAM_METADATA_VALUE,
)
from backend.schemas.api import AgentStreamEvent, ApiError, TraceContext
from backend.services.agent_progress import (
    DRAFTING,
    UNDERSTANDING,
    ProgressNarrator,
)
from backend.schemas.chat import (
    DEFAULT_CHAT_MODE,
    ChatAttachment,
    ChatMode,
    ChatScope,
    chat_scope_key,
)
from backend.services.trace_recorder import elapsed_ms, new_trace_context, trace_event
from backend.settings import (
    effective_langsmith_model_name,
    langsmith_metadata,
    langsmith_tags,
    langsmith_tracing_enabled,
    settings,
)

try:
    import langsmith as ls
except ImportError:  # pragma: no cover - langsmith is provided by LangChain deps.
    ls = None


THREAD_LOCK_TIMEOUT_SECONDS = 30
# Il ciclo di lettura della coda si sveglia per accorgersi che il worker e' morto
# senza sentinella. Non e' piu' un battito che genera testo: il progresso esce
# quando cambia la fase, non allo scadere di un timer.
QUEUE_POLL_SECONDS = 1.0
# Agent work is visible by default. These two sets are the exceptions, so a node
# added to a graph reports progress without anyone remembering to register it -
# the previous allow-list of 44 node names silently swallowed every new node.
#
# Nodes whose work is plumbing, not the agent's answer: context loaders, routers,
# loop evaluators. They emit nothing.
INTERNAL_AGENT_NODES = {
    "summarize",
    "classify_and_select_context",
    "load_process_context",
    "load_canvas_context",
    "load_context",
    "consulting_router",
    "project_router",
    "process_router",
    "evaluate_process_iteration",
    "evaluate_canvas_completion",
    "refresh_canvas_context_after_work",
}

# Nodes that report progress but whose token stream is not an answer to the user:
# a router's structured decision, a subgraph wrapper replaying its child's tokens.
NON_DELTA_AGENT_NODES = {
    "canvas_router",
    "patch_edit_subgraph",
    "construction_subgraph",
    "layout_subgraph",
    "validation_subgraph",
}


def is_internal_agent_node(node_name: str) -> bool:
    """Determine whether an agent node should be excluded from the user-visible stream.
    
    Args:
        node_name (str): Untrusted node name to classify.
    
    Returns:
        bool: `True` if the node is an internal node or ends with ``"_tools"``,
            `False` otherwise.
    """
    return node_name in INTERNAL_AGENT_NODES or node_name.endswith("_tools")


_THREAD_LOCKS: dict[str, Lock] = {}
_THREAD_LOCKS_GUARD = Lock()


def merge_usage_metadata(
    totals: dict[str, Any],
    usage_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    if not usage_metadata:
        return totals

    for key, value in usage_metadata.items():
        if isinstance(value, bool):
            continue

        if isinstance(value, int | float):
            totals[key] = totals.get(key, 0) + value
            continue

        if isinstance(value, dict):
            nested = totals.setdefault(key, {})
            if isinstance(nested, dict):
                merge_usage_metadata(nested, value)

    return totals


def get_thread_lock(thread_id: str) -> Lock:
    with _THREAD_LOCKS_GUARD:
        if thread_id not in _THREAD_LOCKS:
            _THREAD_LOCKS[thread_id] = Lock()

        return _THREAD_LOCKS[thread_id]


def message_content_to_text(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))

        return "".join(parts)

    return str(content or "")


def is_internal_stream_metadata(metadata: dict[str, Any]) -> bool:
    if metadata.get(INTERNAL_STREAM_METADATA_KEY) == INTERNAL_STREAM_METADATA_VALUE:
        return True

    nested = metadata.get("metadata")
    if isinstance(nested, dict) and nested.get(INTERNAL_STREAM_METADATA_KEY) == INTERNAL_STREAM_METADATA_VALUE:
        return True

    tags = metadata.get("tags")
    return isinstance(tags, list) and INTERNAL_STREAM_METADATA_VALUE in tags


def progress_event(
    *,
    context: TraceContext,
    thread_id: str,
    payload: dict | None,
) -> AgentStreamEvent | None:
    """Confeziona un cambio di fase come evento di stream, o niente se non c'e'.

    Il nodo non viaggia nell'evento: il consulente non deve mai leggere un nome
    interno, e il livello di traccia lo riporta comunque a parte.
    """
    if not payload:
        return None

    return AgentStreamEvent(
        type="activity",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        message=payload["label"],
        payload=payload,
    )


def normalize_stream_event(event: Any) -> tuple[str, Any]:
    """Riporta un elemento dello stream a ``(modo, payload)``.

    Con piu' `stream_mode` LangGraph antepone il nome del modo; con uno solo
    consegna direttamente la coppia ``(chunk, metadata)``. Gli agenti finti dei
    test usano ancora la forma corta, e devono continuare a funzionare.
    """
    if (
        isinstance(event, tuple)
        and len(event) == 2
        and isinstance(event[0], str)
        and event[0] in {"messages", "updates", "values", "custom", "debug"}
    ):
        return event[0], event[1]

    if isinstance(event, tuple) and len(event) == 2:
        return "messages", event

    return "messages", (event, {})


def tool_calls_in_update(update: Any) -> list[dict]:
    """Raccoglie le chiamate a tool contenute in un aggiornamento di stato.

    LangGraph consegna gli update come mappa nodo -> stato parziale, e i
    sottografi possono annidarli. La ricerca e' strutturale invece che per
    percorso noto, cosi' un grafo nuovo non smette di raccontare cosa fa.

    Args:
        update: Aggiornamento di stato emesso dal grafo.

    Returns:
        list[dict]: Chiamate trovate, ognuna con ``name`` e ``args``.
    """
    found: list[dict] = []

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 4:
            return

        if isinstance(value, dict):
            for item in value.values():
                walk(item, depth + 1)
            return

        if isinstance(value, list | tuple):
            for item in value:
                walk(item, depth + 1)
            return

        calls = getattr(value, "tool_calls", None)
        if not calls:
            return

        for call in calls:
            if isinstance(call, dict):
                found.append({"name": call.get("name"), "args": call.get("args")})
            else:
                found.append(
                    {
                        "name": getattr(call, "name", None),
                        "args": getattr(call, "args", None),
                    }
                )

    walk(update)
    return found


def agent_checkpoint_thread_id(thread_id: str, scope_key: str | None) -> str:
    return f"{scope_key or 'consultant'}:{thread_id}"


def scope_fields(scope: ChatScope | None) -> dict[str, str | None]:
    key = chat_scope_key(scope)

    if scope is None:
        return {
            "scope_type": "consultant",
            "project_id": None,
            "process_id": None,
            "bpmn_model_id": None,
            "scope_key": key,
        }

    return {
        "scope_type": scope.type,
        "project_id": getattr(scope, "project_id", None),
        "process_id": getattr(scope, "process_id", None),
        "bpmn_model_id": getattr(scope, "bpmn_model_id", None),
        "scope_key": key,
    }


def build_trace_context(
    *,
    thread_id: str,
    model_name: str | None,
    scope: ChatScope | None,
) -> TraceContext:
    """Build trace metadata for a request and its scoped checkpoint thread.
    
    Args:
        thread_id (str): Untrusted request thread identifier.
        model_name (str | None): Model name to associate with the trace.
        scope (ChatScope | None): Optional scope used to derive scope type, scope key,
            and checkpoint thread identity.
    
    Returns:
        TraceContext: Trace context containing the request thread, scoped checkpoint
            thread, scope metadata, and model name.
    """
    fields = scope_fields(scope)
    checkpoint_thread_id = agent_checkpoint_thread_id(thread_id, fields["scope_key"])
    return new_trace_context(
        thread_id=thread_id,
        checkpoint_thread_id=checkpoint_thread_id,
        scope_type=fields["scope_type"],
        scope_key=fields["scope_key"],
        model_name=model_name,
    )


def _latest_user_message(messages: list[dict]) -> str:
    """Extract the most recent user message content.
    
    Args:
        messages (list[dict]): Untrusted message records to search in reverse order.
    
    Returns:
        str: The stripped content of the most recent user or human message, or an
            empty string when no such message exists.
    """
    for message in reversed(messages or []):
        role = message.get("role") or message.get("type")
        if role in {"user", "human"}:
            return str(message.get("content") or "").strip()
    return ""


def fake_agent_events(
    *,
    thread_id: str,
    messages: list[dict],
    scope: ChatScope | None,
    context: TraceContext,
) -> Iterator[AgentStreamEvent]:
    """Emits a deterministic fake agent stream without invoking an agent graph or language model.
    
    The stream preserves the standard event sequence: start, request-start trace,
    node, token deltas, and request-end trace. It uses the supplied scope and trace
    context consistently across all events and performs no external side effects or
    persistence.
    
    Args:
        thread_id (str): Untrusted thread identifier included in each emitted event.
        messages (list[dict]): Untrusted input messages used to identify the latest
            user message.
        scope (ChatScope | None): Optional scope associated with the request.
        context (TraceContext): Request and trace identifiers attached to each event.
    
    Returns:
        Iterator[AgentStreamEvent]: Deterministic fake agent stream events.
    """
    fields = scope_fields(scope)
    user_text = _latest_user_message(messages)
    reply = (
        f"[fake-llm] Ricevuto in scope '{fields['scope_type']}'. "
        f"Messaggio: {user_text or '(vuoto)'}"
    )

    yield AgentStreamEvent(
        type="start",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        payload={
            "scope_type": fields["scope_type"],
            "scope_key": fields["scope_key"],
            "fake_llm": True,
        },
    )
    yield AgentStreamEvent(
        type="trace",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        payload=trace_event(context, "request_start", message="Fake agent stream started.").model_dump(),
    )
    yield AgentStreamEvent(
        type="node",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        node="fake_agent",
        payload=trace_event(context, "node", node="fake_agent", message="Fake agent node.").model_dump(),
    )
    for token in reply.split(" "):
        yield AgentStreamEvent(
            type="delta",
            request_id=context.request_id,
            trace_id=context.trace_id,
            thread_id=thread_id,
            node="fake_agent",
            content=token + " ",
        )
    yield AgentStreamEvent(
        type="trace",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        payload=trace_event(context, "request_end", message="Fake agent stream completed.").model_dump(),
    )


def stream_agent_events(
    *,
    thread_id: str,
    model_name: str | None,
    messages: list[dict],
    scope: ChatScope | None = None,
    chat_mode: ChatMode | None = None,
    attachments: list[ChatAttachment] | None = None,
    trace_context: TraceContext | None = None,
    emit_activity: bool = True,
) -> Iterator[AgentStreamEvent]:
    """
    Stream scoped agent responses as structured events.
    
    The stream enforces one active request per scoped checkpoint thread and may persist
    agent checkpoint state. Busy sessions produce retryable error events; agent
    execution failures produce non-retryable error events.
    
    Args:
        thread_id: (Untrusted input.) Conversation identifier.
        model_name: (Untrusted input.) Requested model name, or ``None`` for the
            default model.
        messages: (Untrusted input.) Conversation messages supplied to the agent.
        scope: (Untrusted input.) Optional scope used to select the agent and
            checkpoint namespace.
        chat_mode: (Untrusted input.) Optional chat mode for the agent execution.
        attachments: (Untrusted input.) Optional attachments associated with the
            request.
        trace_context: Optional context used for emitted trace and lifecycle events.
        emit_activity: Whether to emit activity progress events while the agent runs.
    
    Yields:
        AgentStreamEvent: Lifecycle, node, text-delta, usage, trace, activity,
            warning, or error events.
    """
    fields = scope_fields(scope)
    selected_model = normalize_model_name(model_name)
    checkpoint_thread_id = agent_checkpoint_thread_id(thread_id, fields["scope_key"])
    context = trace_context or new_trace_context(
        thread_id=thread_id,
        checkpoint_thread_id=checkpoint_thread_id,
        scope_type=fields["scope_type"],
        scope_key=fields["scope_key"],
        model_name=model_name,
    )

    if settings.delir_fake_llm:
        yield from fake_agent_events(
            thread_id=thread_id,
            messages=messages,
            scope=scope,
            context=context,
        )
        return

    agent = get_agent(selected_model, scope_type=fields["scope_type"])
    thread_lock = get_thread_lock(checkpoint_thread_id)
    last_node = None
    first_token_recorded = False
    usage_totals: dict[str, Any] = {}
    narrator = ProgressNarrator()
    run_tags = langsmith_tags(
        "consultant-chat",
        f"scope:{fields['scope_type']}",
        f"scope_key:{fields['scope_key']}",
    )
    run_metadata = {
        **langsmith_metadata(
            selected_model,
            thread_id=thread_id,
            session_id=thread_id,
            conversation_id=thread_id,
            checkpoint_thread_id=checkpoint_thread_id,
            scope_type=fields["scope_type"],
            scope_key=fields["scope_key"],
            trace_id=context.trace_id,
            request_id=context.request_id,
        ),
        "delir_requested_model_name": model_name or "",
        "delir_model_name": selected_model,
        "delir_effective_langsmith_model_name": effective_langsmith_model_name(selected_model),
    }

    yield AgentStreamEvent(
        type="start",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        payload={
            "scope_type": fields["scope_type"],
            "scope_key": fields["scope_key"],
            "chat_mode": chat_mode or DEFAULT_CHAT_MODE,
            "checkpoint_thread_id": checkpoint_thread_id,
        },
    )
    yield AgentStreamEvent(
        type="trace",
        request_id=context.request_id,
        trace_id=context.trace_id,
        thread_id=thread_id,
        payload=trace_event(context, "request_start", message="Agent stream started.").model_dump(),
    )

    acquired = thread_lock.acquire(timeout=THREAD_LOCK_TIMEOUT_SECONDS)
    if not acquired:
        error = ApiError(
            code="agent_thread_busy",
            message="Sessione occupata. Riprova tra qualche secondo.",
            detail="A previous request is still running for this checkpoint thread.",
            request_id=context.request_id,
            trace_id=context.trace_id,
            origin="agent",
            retryable=True,
        )
        yield AgentStreamEvent(
            type="error",
            request_id=context.request_id,
            trace_id=context.trace_id,
            thread_id=thread_id,
            error=error,
        )
        yield AgentStreamEvent(
            type="trace",
            request_id=context.request_id,
            trace_id=context.trace_id,
            thread_id=thread_id,
            payload=trace_event(
                context,
                "error",
                status="error",
                message=error.message,
                payload=error.model_dump(),
            ).model_dump(),
        )
        return

    output_queue: Queue[AgentStreamEvent | None] = Queue()

    def enqueue(event: AgentStreamEvent) -> None:
        output_queue.put(event)

    def run_agent_stream() -> None:
        """Run the agent stream and enqueue node, content, usage, completion, or error events.
        
        The active scope, mode, and checkpoint thread remain bound for the duration of
        agent execution. Internal nodes and metadata, as well as non-delta nodes, are
        excluded from content events, while usage is aggregated across streamed
        chunks.
        
        Agent execution failures are converted into non-retryable error and trace
        events rather than propagated. The per-thread lock is always released, and a
        queue sentinel is always emitted to signal stream termination. This function
        does not persist results.
        """
        nonlocal last_node, first_token_recorded, usage_totals
        tracing_context = (
            ls.tracing_context(
                enabled=True,
                project_name=settings.langsmith_project,
                tags=run_tags,
                metadata=run_metadata,
            )
            if ls is not None and langsmith_tracing_enabled()
            else nullcontext()
        )

        try:
            with (
                tracing_context,
                bind_active_scope(scope),
                bind_active_mode(chat_mode),
                bind_active_thread(checkpoint_thread_id),
            ):
                events = agent.stream(
                    {
                        "messages": messages,
                        **agent_scope_state(
                            scope,
                            chat_mode,
                            attachments,
                            thread_id=checkpoint_thread_id,
                        ),
                    },
                    config={
                        "configurable": {
                            "thread_id": checkpoint_thread_id,
                        },
                        "run_id": UUID(context.trace_id),
                        "run_name": "DeliR scoped agent",
                        "tags": run_tags,
                        "metadata": run_metadata,
                    },
                    # "updates" porta le chiamate a tool: senza questo modo il
                    # consulente resta al buio proprio mentre l'agente cerca in
                    # memoria o rilegge le fonti, che e' l'attesa piu' lunga.
                    stream_mode=["messages", "updates"],
                )

                for event in events:
                    stream_mode_name, payload = normalize_stream_event(event)

                    if stream_mode_name == "updates":
                        if emit_activity:
                            for call in tool_calls_in_update(payload):
                                progress = progress_event(
                                    context=context,
                                    thread_id=thread_id,
                                    payload=narrator.enter_for_tool(
                                        call["name"], call["args"]
                                    ),
                                )
                                if progress is not None:
                                    enqueue(progress)
                        continue

                    chunk, metadata = payload

                    node_name = metadata.get("langgraph_node")
                    if node_name and is_internal_agent_node(node_name):
                        continue

                    if node_name and node_name != last_node:
                        last_node = node_name
                        if emit_activity:
                            progress = progress_event(
                                context=context,
                                thread_id=thread_id,
                                payload=narrator.enter_for_node(node_name),
                            )
                            if progress is not None:
                                enqueue(progress)
                        node_trace = trace_event(
                            context,
                            "node",
                            node=node_name,
                            message=f"Agent entered node: {node_name}",
                        )
                        enqueue(
                            AgentStreamEvent(
                                type="node",
                                request_id=context.request_id,
                                trace_id=context.trace_id,
                                thread_id=thread_id,
                                node=node_name,
                                payload=node_trace.model_dump(),
                            )
                        )

                    if getattr(chunk, "type", None) not in {"AIMessageChunk", "ai"}:
                        continue

                    usage_metadata = getattr(chunk, "usage_metadata", None)
                    if usage_metadata:
                        merge_usage_metadata(usage_totals, dict(usage_metadata))

                    content = message_content_to_text(getattr(chunk, "content", ""))

                    if is_internal_stream_metadata(metadata):
                        continue

                    if node_name and node_name in NON_DELTA_AGENT_NODES:
                        continue

                    if content and emit_activity:
                        # La risposta ha iniziato a formarsi: la fase e' questa,
                        # qualunque cosa il grafo stia facendo sotto.
                        progress = progress_event(
                            context=context,
                            thread_id=thread_id,
                            payload=narrator.enter(DRAFTING),
                        )
                        if progress is not None:
                            enqueue(progress)

                    if content and not first_token_recorded:
                        first_token_recorded = True
                        first_token_trace = trace_event(
                            context,
                            "first_token",
                            node=node_name,
                            message="First streamed model token received.",
                            payload={"ttft_ms": elapsed_ms(context.trace_id)},
                        )
                        enqueue(
                            AgentStreamEvent(
                                type="trace",
                                request_id=context.request_id,
                                trace_id=context.trace_id,
                                thread_id=thread_id,
                                payload=first_token_trace.model_dump(),
                            )
                        )

                    if content:
                        enqueue(
                            AgentStreamEvent(
                                type="delta",
                                request_id=context.request_id,
                                trace_id=context.trace_id,
                                thread_id=thread_id,
                                node=node_name,
                                content=content,
                            )
                        )

            if usage_totals:
                enqueue(
                    AgentStreamEvent(
                        type="trace",
                        request_id=context.request_id,
                        trace_id=context.trace_id,
                        thread_id=thread_id,
                        payload=trace_event(
                            context,
                            "usage",
                            message="Aggregated streamed model usage received.",
                            payload={"usage_metadata": usage_totals},
                        ).model_dump(),
                    )
                )

            enqueue(
                AgentStreamEvent(
                    type="trace",
                    request_id=context.request_id,
                    trace_id=context.trace_id,
                    thread_id=thread_id,
                    payload=trace_event(context, "request_end", message="Agent stream completed.").model_dump(),
                )
            )
        except Exception as exc:
            error = ApiError(
                code="agent_stream_failed",
                message="Errore durante l'esecuzione dell'agente.",
                detail=str(exc),
                request_id=context.request_id,
                trace_id=context.trace_id,
                origin="agent",
                retryable=False,
            )
            enqueue(
                AgentStreamEvent(
                    type="error",
                    request_id=context.request_id,
                    trace_id=context.trace_id,
                    thread_id=thread_id,
                    error=error,
                )
            )
            enqueue(
                AgentStreamEvent(
                    type="trace",
                    request_id=context.request_id,
                    trace_id=context.trace_id,
                    thread_id=thread_id,
                    payload=trace_event(
                        context,
                        "error",
                        status="error",
                        message=error.message,
                        payload=error.model_dump(),
                    ).model_dump(),
                )
            )
        finally:
            thread_lock.release()
            output_queue.put(None)

    worker = Thread(target=run_agent_stream, name=f"delir-agent-stream-{context.request_id}", daemon=True)
    worker.start()

    if emit_activity:
        # Il primo aggiornamento parte subito e senza modello: prima si vedeva
        # comparire il progresso solo se il narratore LLM rispondeva in tempo, e
        # spesso il turno finiva prima.
        initial_activity = progress_event(
            context=context,
            thread_id=thread_id,
            payload=narrator.enter(UNDERSTANDING),
        )
        if initial_activity is not None:
            yield initial_activity

    while True:
        try:
            queued = output_queue.get(timeout=QUEUE_POLL_SECONDS)
        except Empty:
            if not worker.is_alive() and output_queue.empty():
                break
            continue

        if queued is None:
            break
        yield queued

    worker.join(timeout=1)

    if worker.is_alive():
        yield AgentStreamEvent(
            type="warning",
            request_id=context.request_id,
            trace_id=context.trace_id,
            thread_id=thread_id,
            message="Agent stream worker still shutting down.",
        )


def stream_agent_deltas(
    *,
    thread_id: str,
    model_name: str | None,
    messages: list[dict],
    scope: ChatScope | None = None,
    chat_mode: ChatMode | None = None,
    attachments: list[ChatAttachment] | None = None,
) -> Iterator[str]:
    """
    Stream text deltas from an agent execution.
    
    Args:
        thread_id: Untrusted thread identifier used for checkpoint isolation.
        model_name: Untrusted model name, or `None` to use the default model.
        messages: Untrusted chat messages supplied to the agent.
        scope: Optional scope used to identify the execution context.
        chat_mode: Optional chat mode for the execution.
        attachments: Untrusted attachments associated with the chat request.
    
    Yields:
        Text content from each streamed agent delta.
    
    Raises:
        RuntimeError: If the agent emits an execution error.
    
    Side Effects:
        Runs the agent and may update its checkpoint state.
    """
    for event in stream_agent_events(
        thread_id=thread_id,
        model_name=model_name,
        messages=messages,
        scope=scope,
        chat_mode=chat_mode,
        attachments=attachments,
        emit_activity=False,
    ):
        if event.type == "delta" and event.content:
            yield event.content
        elif event.type == "error" and event.error:
            raise RuntimeError(event.error.message)


def stream_agent_text(
    *,
    thread_id: str,
    model_name: str | None,
    messages: list[dict],
    scope: ChatScope | None = None,
    chat_mode: ChatMode | None = None,
    attachments: list[ChatAttachment] | None = None,
) -> str:
    """Collect the agent's streamed text deltas into a complete response.
    
    Args:
        thread_id: (Untrusted input.) Identifier for the conversation thread.
        model_name: (Untrusted input.) Optional model name used for agent execution.
        messages: (Untrusted input.) Messages supplied to the agent.
        scope: Optional scope used for checkpoint isolation and execution context.
        chat_mode: Optional chat mode for the agent request.
        attachments: (Untrusted input.) Optional attachments associated with the request.
    
    Returns:
        The concatenated text emitted by the agent.
    
    Raises:
        RuntimeError: If the agent emits a streamed execution error.
    
    Side Effects:
        Executes the agent and may update its checkpoint state.
    """
    return "".join(
        stream_agent_deltas(
            thread_id=thread_id,
            model_name=model_name,
            messages=messages,
            scope=scope,
            chat_mode=chat_mode,
            attachments=attachments,
        )
    )
