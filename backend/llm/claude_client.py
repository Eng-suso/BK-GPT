"""Il client Claude del gateway: Haiku e gli altri modelli Anthropic.

Lo costruisce solo `gateway._client`, quando il modello del compito si chiama
`claude-...` (`backend/llm/providers.py`). Due cose lo distinguono dal client
OpenAI, ed e' per queste che esiste un modulo suo:

- **la cache non e' automatica.** Anthropic mette in cache solo dove la
  richiesta mette un segnalibro (`cache_control`), e fa pagare la scrittura 1,25
  volte l'ingresso. Il segnalibro va alla fine del prompt di sistema, cioe' della
  parte fissa del compito: messo alla fine della richiesta, ogni chiamata
  pagherebbe la scrittura su un contenuto che nessuno rilegge. Sotto i 512 token
  (il minimo di Haiku 5.5) Anthropic non mette in cache e non fa pagare niente;
- **un solo messaggio di sistema, in testa.** La versione di langchain-anthropic
  che regge il nostro langchain-core rifiuta un secondo messaggio di sistema.
  Qui i messaggi di sistema iniziali si uniscono in uno; uno che arriva piu'
  avanti resta al suo posto, come richiesta;
- **ragionamento spento.** Con il ragionamento acceso langchain-anthropic non
  forza piu' il tool dell'output strutturato: una risposta in prosa fallirebbe
  senza passare dal ripiego del JSON libero, e il ragionamento consumerebbe il
  tetto di `max_tokens` prima della risposta. Il livello del profilo resta, come
  `effort`: dice quanto il modello spende.

La chat non passa di qui: vedi `FIXED_MODEL_TASKS` in `backend/llm/tasks.py`.
"""

from __future__ import annotations

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from backend.llm.egress import ANTHROPIC_API_URL, Destination, require
from backend.llm.local_tracer import local_callbacks
from backend.llm.tasks import TaskProfile
from backend.llm_config import MissingProviderKey, timeout_for_input
from backend.settings import settings

#: Il segnalibro della cache: 5 minuti, la durata che costa 1,25x in scrittura.
CACHE_BREAKPOINT = {"type": "ephemeral"}

#: Il livello del profilo, nei termini di Claude. Con il ragionamento spento
#: Haiku 5.5 accetta fino a `high`. Un livello sconosciuto vale `low`: costa meno,
#: e non e' mai il caso di spendere di piu' per un nome sbagliato.
_EFFORT = {"none": "low", "minimal": "low", "low": "low", "medium": "medium", "high": "high"}


class DeliRChatAnthropic(ChatAnthropic):
    """`ChatAnthropic` che prepara i messaggi come li vuole Claude, e li segna."""

    def _get_request_payload(self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any) -> dict:
        messages = self._convert_input(input_).to_messages()
        return super()._get_request_payload(with_cached_system(messages), stop=stop, **kwargs)


def with_cached_system(messages: list[BaseMessage]) -> list[BaseMessage]:
    """I messaggi di sistema iniziali uniti in uno, con il segnalibro in fondo.

    Quelli iniziali sono la parte fissa del compito, ed e' li' che la cache rende.
    Un messaggio di sistema che arriva dopo la conversazione si riferisce a cio'
    che lo precede: resta al suo posto, come richiesta, invece di salire in testa
    e cambiare il prefisso a ogni chiamata.
    """
    lead = 0
    while lead < len(messages) and isinstance(messages[lead], SystemMessage):
        lead += 1
    blocks = [block for message in messages[:lead] for block in _text_blocks(message)]
    rest = [
        HumanMessage(content=message.content) if isinstance(message, SystemMessage) else message
        for message in messages[lead:]
    ]
    if not blocks:
        return rest
    blocks[-1] = {**blocks[-1], "cache_control": CACHE_BREAKPOINT}
    return [SystemMessage(content=blocks), *rest]


def _text_blocks(message: BaseMessage) -> list[dict[str, Any]]:
    content = message.content
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    return [dict(block) if isinstance(block, dict) else {"type": "text", "text": str(block)} for block in content]


def claude_client(profile: TaskProfile, *, input_characters: int | None, max_retries: int) -> DeliRChatAnthropic:
    """Il client Claude di un compito, dal suo profilo.

    Raises:
        MissingProviderKey: Senza `ANTHROPIC_API_KEY`: il compito non parte e il
            registro lo dice, invece di ricadere in silenzio su OpenAI.
        EgressBlocked: Se api.anthropic.com non e' fra le destinazioni
            autorizzate. E' una `MissingProviderKey`: stessa via.
    """
    if not settings.anthropic_api_key:
        raise MissingProviderKey(
            f"ANTHROPIC_API_KEY non configurata: il compito {profile.task.value} "
            f"e' assegnato a {profile.model} in LLM_TASK_MODELS_JSON."
        )
    require(Destination.LLM_CLAUDE)
    kwargs: dict[str, Any] = {
        "model": profile.model,
        "api_key": settings.anthropic_api_key,
        # L'host che il registro dichiara e autorizza. Senza, langchain-anthropic
        # lo leggerebbe da ANTHROPIC_BASE_URL, e i dati potrebbero uscire verso
        # un host che l'inventario non vede.
        "base_url": ANTHROPIC_API_URL,
        # Anthropic lo vuole sempre.
        "max_tokens": profile.max_output_tokens or settings.model_max_tokens,
        "timeout": timeout_for_input(input_characters if profile.scales_with_input else None),
        "max_retries": max_retries,
        "effort": _EFFORT.get(profile.reasoning_effort, "low"),
        "thinking": {"type": "disabled"},
    }
    callbacks = local_callbacks()
    if callbacks:
        kwargs["callbacks"] = callbacks
    return DeliRChatAnthropic(**kwargs)
