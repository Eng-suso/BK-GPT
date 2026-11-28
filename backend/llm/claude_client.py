"""I client Claude: Haiku e gli altri modelli Anthropic, nel gateway e nella chat.

Li costruiscono `gateway._client` e `chat_client`, quando il modello si chiama
`claude-...` (`backend/llm/providers.py`). Tre cose li distinguono dai client
OpenAI, ed e' per queste che esiste un modulo suo:

- **la cache non e' automatica.** Anthropic mette in cache solo dove la
  richiesta mette un segnalibro (`cache_control`), e fa pagare la scrittura 1,25
  volte l'ingresso. Un segnalibro va sempre alla fine del prompt di sistema, la
  parte fissa. Nella chat ce n'e' un secondo alla fine della conversazione: il
  passo dopo rilegge dalla cache tutto il passo prima e paga a prezzo pieno solo
  cio' che si e' aggiunto. In una chiamata singola del gateway quel secondo
  segnalibro farebbe pagare la scrittura su un contenuto che nessuno rilegge, e
  non c'e'. Sotto i 512 token (il minimo di Haiku 5.5) Anthropic non mette in
  cache e non fa pagare niente;
- **un solo messaggio di sistema in testa.** langchain-anthropic non unisce i
  messaggi di sistema consecutivi, e un secondo in testa lo rifiuta. Qui quelli
  iniziali si uniscono in uno. Quelli che arrivano dopo la conversazione (il
  contratto dello specialista, in coda al prompt della chat) restano al loro
  posto: Claude li accetta a meta' conversazione, ma solo dopo un turno
  dell'utente o di un tool. Dopo un turno dell'assistente diventano una
  richiesta, che e' cio' che sono;
- **ragionamento spento.** Con il ragionamento acceso langchain-anthropic non
  forza il tool dell'output strutturato (una risposta in prosa fallirebbe senza
  ripiego) e il ragionamento consuma `max_tokens` prima della risposta; nella
  chat i suoi blocchi finirebbero nella storia del thread. Il livello chiesto
  resta, come `effort`: dice quanto il modello spende.
"""

from __future__ import annotations

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from backend.llm.egress import ANTHROPIC_API_URL, Destination, require
from backend.llm.local_tracer import local_callbacks
from backend.llm_config import MissingProviderKey
from backend.settings import settings

#: Il segnalibro della cache: 5 minuti, la durata che costa 1,25x in scrittura.
CACHE_BREAKPOINT = {"type": "ephemeral"}

#: I livelli che Claude conosce con lo stesso nome. Con il ragionamento spento
#: Haiku 5.5 accetta fino a `high`. Gli altri (`none`, o un nome che Claude non
#: conosce) valgono `low`: costa meno, e non e' mai il caso di spendere di piu'
#: per un nome sbagliato.
_CLAUDE_EFFORTS = frozenset({"low", "medium", "high"})

#: Blocchi su cui Anthropic non accetta un segnalibro.
_UNMARKABLE_BLOCKS = frozenset({"thinking", "redacted_thinking"})


class DeliRChatAnthropic(ChatAnthropic):
    """`ChatAnthropic` che prepara i messaggi come li vuole Claude, e li segna.

    Attributes:
        cache_conversation: Se segnare anche la fine della conversazione, oltre al
            sistema. Vero per la chat, che a ogni passo rimanda il prompt di
            prima allungato di un pezzo.
    """

    cache_conversation: bool = False

    def _get_request_payload(self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any) -> dict:
        messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(merge_leading_system(messages), stop=stop, **kwargs)
        return with_cache_breakpoints(payload, conversation=self.cache_conversation)


def merge_leading_system(messages: list[BaseMessage]) -> list[BaseMessage]:
    """I messaggi di sistema iniziali uniti in uno; gli altri restano dove sono.

    Un messaggio di sistema subito dopo un turno dell'assistente diventa una
    richiesta: Claude non lo accetta li', e langchain-anthropic rifiuterebbe la
    richiesta intera.
    """
    lead = 0
    while lead < len(messages) and isinstance(messages[lead], SystemMessage):
        lead += 1
    head: list[BaseMessage] = (
        [SystemMessage(content=[block for m in messages[:lead] for block in _text_blocks(m.content)])]
        if lead > 1
        else list(messages[:lead])
    )
    rest: list[BaseMessage] = []
    for message in messages[lead:]:
        after_assistant = bool(rest) and isinstance(rest[-1], AIMessage)
        if isinstance(message, SystemMessage) and after_assistant:
            message = HumanMessage(content=message.content)
        rest.append(message)
    return [*head, *rest]


def with_cache_breakpoints(payload: dict, *, conversation: bool) -> dict:
    """I segnalibri della cache nella richiesta vera, dopo che langchain l'ha scritta.

    Si lavora sulla richiesta e non sui messaggi langchain perche' e' li' che le
    posizioni sono quelle che Claude vede: i messaggi dei tool diventano blocchi
    di un messaggio utente, i messaggi consecutivi si uniscono.
    """
    system = payload.get("system")
    if system:
        blocks = _text_blocks(system)
        _mark_last(blocks)
        payload["system"] = blocks
    if conversation:
        for message in reversed(payload.get("messages") or []):
            if message.get("role") not in ("user", "assistant"):
                continue
            blocks = _text_blocks(message.get("content"))
            if _mark_last(blocks):
                message["content"] = blocks
                break
    return payload


def _text_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    return [dict(block) if isinstance(block, dict) else {"type": "text", "text": str(block)} for block in content or []]


def _mark_last(blocks: list[dict[str, Any]]) -> bool:
    """Segna l'ultimo blocco che lo accetta. Falso se non ce n'e' nessuno."""
    for index in range(len(blocks) - 1, -1, -1):
        block = blocks[index]
        if block.get("type") in _UNMARKABLE_BLOCKS or (block.get("type") == "text" and not block.get("text")):
            continue
        blocks[index] = {**block, "cache_control": CACHE_BREAKPOINT}
        return True
    return False


def claude_client(
    *,
    model: str,
    max_tokens: int,
    timeout: float | None,
    max_retries: int,
    effort: str | None,
    streaming: bool = False,
    cache_conversation: bool = False,
    **extra: Any,
) -> DeliRChatAnthropic:
    """Un client Claude. Lo chiamano il gateway e `chat_client`, con i loro profili.

    Args:
        extra: Gli altri campi di `ChatAnthropic` che chi chiama decide (tag e
            metadati di LangSmith della chat).

    Raises:
        MissingProviderKey: Senza `ANTHROPIC_API_KEY`: la chiamata non parte e il
            registro lo dice, invece di ricadere in silenzio su OpenAI.
        EgressBlocked: Se api.anthropic.com non e' fra le destinazioni
            autorizzate. E' una `MissingProviderKey`: stessa via.
    """
    if not settings.anthropic_api_key:
        raise MissingProviderKey(
            f"ANTHROPIC_API_KEY non configurata: {model} e' scelto in LLM_TASK_MODELS_JSON."
        )
    require(Destination.LLM_CLAUDE)
    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": settings.anthropic_api_key,
        # L'host che il registro dichiara e autorizza. Senza, langchain-anthropic
        # lo leggerebbe da ANTHROPIC_BASE_URL, e i dati potrebbero uscire verso
        # un host che l'inventario non vede.
        "base_url": ANTHROPIC_API_URL,
        # Anthropic lo vuole sempre.
        "max_tokens": max_tokens,
        "timeout": timeout,
        "max_retries": max_retries,
        "effort": effort if effort in _CLAUDE_EFFORTS else "low",
        "thinking": {"type": "disabled"},
        "streaming": streaming,
        "cache_conversation": cache_conversation,
        **extra,
    }
    callbacks = local_callbacks()
    if callbacks:
        kwargs["callbacks"] = callbacks
    return DeliRChatAnthropic(**kwargs)
