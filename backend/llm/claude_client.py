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
  Qui i messaggi di sistema si uniscono in uno, in testa, prima della richiesta:
  copre anche le istruzioni che il gateway aggiunge in coda (lo schema del JSON
  libero e la sua correzione).

La chat non passa di qui: vedi `FIXED_MODEL_TASKS` in `backend/llm/tasks.py`.
"""

from __future__ import annotations

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, SystemMessage

from backend.llm.egress import Destination, require
from backend.llm.local_tracer import local_callbacks
from backend.llm.tasks import TaskProfile
from backend.llm_config import MissingProviderKey, timeout_for_input
from backend.settings import settings

#: Il segnalibro della cache: 5 minuti, la durata che costa 1,25x in scrittura.
CACHE_BREAKPOINT = {"type": "ephemeral"}

#: Il livello di ragionamento del profilo, nei termini di Claude. `none` spegne
#: il ragionamento (Haiku 5.5 lo permette fino al livello `high`): sono i compiti
#: dove lo schema stretto fa il lavoro, e il tool forzato dell'output
#: strutturato non convive con il ragionamento acceso.
_EFFORT = {"none": "low", "low": "low", "medium": "medium", "high": "high"}


class DeliRChatAnthropic(ChatAnthropic):
    """`ChatAnthropic` che prepara i messaggi come li vuole Claude, e li segna."""

    def _get_request_payload(self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any) -> dict:
        messages = self._convert_input(input_).to_messages()
        return super()._get_request_payload(with_cached_system(messages), stop=stop, **kwargs)


def with_cached_system(messages: list[BaseMessage]) -> list[BaseMessage]:
    """I messaggi di sistema uniti in uno in testa, con il segnalibro in fondo.

    L'ordine dei testi di sistema resta quello in cui arrivano; gli altri
    messaggi restano dove sono. Senza messaggi di sistema non c'e' una parte
    fissa da mettere in cache, e la richiesta passa com'e'.
    """
    system = [message for message in messages if isinstance(message, SystemMessage)]
    if not system:
        return messages
    blocks: list[dict[str, Any]] = []
    for message in system:
        content = message.content
        if isinstance(content, str):
            if content:
                blocks.append({"type": "text", "text": content})
            continue
        for block in content:
            blocks.append(dict(block) if isinstance(block, dict) else {"type": "text", "text": str(block)})
    if not blocks:
        return [message for message in messages if not isinstance(message, SystemMessage)]
    blocks[-1] = {**blocks[-1], "cache_control": CACHE_BREAKPOINT}
    rest = [message for message in messages if not isinstance(message, SystemMessage)]
    return [SystemMessage(content=blocks), *rest]


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
    effort = profile.reasoning_effort
    kwargs: dict[str, Any] = {
        "model": profile.model,
        "api_key": settings.anthropic_api_key,
        # Anthropic lo vuole sempre; il ragionamento, quando c'e', sta dentro.
        "max_tokens": profile.max_output_tokens or settings.model_max_tokens,
        "timeout": timeout_for_input(input_characters if profile.scales_with_input else None),
        "max_retries": max_retries,
        "effort": _EFFORT.get(effort, "medium"),
        "thinking": {"type": "disabled"} if effort == "none" else {"type": "adaptive"},
    }
    callbacks = local_callbacks()
    if callbacks:
        kwargs["callbacks"] = callbacks
    return DeliRChatAnthropic(**kwargs)
