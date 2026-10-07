"""Agent Outcome Harness: un turno vero dell'agente, misurato dall'esterno (P1.4).

Le traiettorie (L3) guardano cosa l'agente chiede. Qui si guarda cosa succede:
il ciclo agente-tool che usa ogni specialista (`build_tool_chat_subgraph`)
gira con i tool veri e un modello a copione, e il turno si misura su quattro
cose:

- **lo stato prima e dopo**, letto da chi chiama (`observe`): canonico (il
  database), derivato (una proiezione, un report), o entrambi;
- **i tool chiesti** dal modello, nell'ordine;
- **i tool eseguiti**, con il loro esito: una chiamata chiesta e mai eseguita
  e' un confine che ha fermato il turno;
- **come finisce il turno**: risposta, o l'eccezione che l'ha fermato.

Il modello e' a copione perche' la domanda non e' se il modello si comporta
bene, ma se il runtime regge quando non lo fa: un modello che obbedisce a
un'injection, che punta un altro progetto, che scrive su un disegno vecchio.
Le garanzie che contano non devono dipendere dalla sua obbedienza.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from backend.graphs.common import ConversationState, build_tool_chat_subgraph
from tests.evals.trajectory_metrics import ToolCall, tool_calls

_SYSTEM = "Sei l'assistente del consulente. Usa i tool per agire sul workspace."


class ScriptedModel(BaseChatModel):
    """Un modello che risponde con le battute scritte, in ordine.

    Ricorda cosa ha ricevuto a ogni chiamata, cosi' il test puo' verificare
    cosa e' arrivato al modello (l'esito di un tool, un errore restituito).
    Finito il copione risponde con un testo e il turno si chiude.
    """

    script: list[AIMessage]
    received: list[list[BaseMessage]] = []

    def bind_tools(self, tools: Sequence[Any], **_kwargs: Any) -> ScriptedModel:
        return self

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **_: Any) -> ChatResult:
        self.received.append(list(messages))
        turn = len(self.received) - 1
        reply = self.script[turn] if turn < len(self.script) else AIMessage(content="Fatto.")
        return ChatResult(generations=[ChatGeneration(message=reply)])


def call(tool_name: str, /, **args: Any) -> AIMessage:
    """Una battuta del copione: il modello chiede un tool con questi argomenti."""
    return AIMessage(
        content="",
        tool_calls=[{"name": tool_name, "args": args, "id": f"call-{tool_name}", "type": "tool_call"}],
    )


@dataclass(frozen=True)
class ToolOutcome:
    name: str
    status: str
    content: str


@dataclass
class TurnOutcome:
    before: dict[str, Any]
    after: dict[str, Any]
    requested: list[ToolCall]
    executed: list[ToolOutcome]
    model_inputs: list[list[BaseMessage]]
    final_text: str | None = None
    error: BaseException | None = None
    messages: list[BaseMessage] = field(default_factory=list)

    @property
    def state_changed(self) -> bool:
        return self.before != self.after

    @property
    def not_executed(self) -> list[str]:
        """I tool chiesti che non hanno un esito: il turno si e' fermato prima."""
        done = [outcome.name for outcome in self.executed]
        missing = []
        for requested in self.requested:
            if requested.name in done:
                done.remove(requested.name)
            else:
                missing.append(requested.name)
        return missing

    def result_of(self, name: str) -> ToolOutcome:
        return next(outcome for outcome in self.executed if outcome.name == name)


def run_agent_turn(
    *,
    tools: list,
    script: list[AIMessage],
    observe: Callable[[], dict[str, Any]],
    user_message: str = "Procedi.",
    state: dict[str, Any] | None = None,
    bound: Callable[[], AbstractContextManager[Any]] = nullcontext,
) -> TurnOutcome:
    """Fa girare un turno e lo misura.

    Args:
        tools: I tool veri dello specialista.
        script: Le battute del modello, in ordine.
        observe: Legge lo stato che il turno potrebbe cambiare. Si chiama prima
            e dopo, fuori da `bound`.
        user_message: Il messaggio del consulente che apre il turno.
        state: Altri campi dello stato del grafo (modo della chat, ...).
        bound: I contesti del runtime per il turno (scope, modo, thread,
            versione di partenza del disegno), come li apre `agent_runtime`.
    """
    model = ScriptedModel(script=list(script), received=[])
    graph = build_tool_chat_subgraph(
        state_schema=ConversationState,
        tools=tools,
        llm_with_tools=model,
        build_context_messages=lambda graph_state: [SystemMessage(content=_SYSTEM), *graph_state["messages"]],
    )
    before = observe()
    initial: dict[str, Any] = {"messages": [HumanMessage(content=user_message)], **(state or {})}
    seen: list[BaseMessage] = []
    error: BaseException | None = None
    try:
        with bound():
            for update in graph.stream(initial, stream_mode="values"):
                seen = list(update.get("messages") or seen)
    except Exception as exc:  # noqa: BLE001 - l'esito del turno e' il dato da misurare
        error = exc
    after = observe()

    # Le battute davvero dette: tante quante le volte che il modello e' stato chiamato.
    requested = tool_calls(model.script[: len(model.received)])
    executed = [
        ToolOutcome(name=str(m.name), status=str(m.status), content=str(m.content))
        for m in seen
        if isinstance(m, ToolMessage)
    ]
    final = seen[-1] if seen and isinstance(seen[-1], AIMessage) and not seen[-1].tool_calls else None
    return TurnOutcome(
        before=before,
        after=after,
        requested=requested,
        executed=executed,
        model_inputs=model.received,
        final_text=str(final.content) if final is not None else None,
        error=error,
        messages=seen,
    )

