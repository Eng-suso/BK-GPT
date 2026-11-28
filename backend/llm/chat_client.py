"""I due client della chat: gli unici che il gateway costruisce ma non esegue.

Tutti gli altri compiti passano da `llm.run()`, che fa la chiamata e scrive la
riga. La chat no, e la ragione non e' architetturale ma di forma: il modello lo
esegue LangGraph, dentro i nodi del grafo, e quello che esce e' uno stream di
pezzi verso il frontend. Un `run()` che restituisce il risultato finale qui non
serve a nessuno.

Quindi il gateway si divide in due:

- **costruisce il client** dal profilo del compito, ed e' questo modulo. Prima i
  parametri stavano scritti a mano in `agent.py` - `reasoning_effort="none"`,
  512 token per l'instradamento, i retry della chat - cioe' le stesse decisioni
  del registro dei compiti, scritte una seconda volta e libere di divergere;
- **registra il consumo** quando lo stream finisce, e quello lo fa
  `gateway.record_streamed_usage`, chiamato dal runtime che i token li ha gia'
  contati per il frontend.

`DeliRChatOpenAI` sta qui e non in `agent.py` anche per L1: la regola in CI
vieta `ChatOpenAI` fuori da `backend/llm/`, e una sottoclasse e' un client come
gli altri.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_openai import ChatOpenAI

from backend.llm.egress import Destination, require
from backend.llm.local_tracer import local_callbacks
from backend.llm.providers import Provider, provider_of
from backend.llm.tasks import LlmTask, profile_for
from backend.llm_streaming import TURN_METERED_TAG
from backend.llm_config import MissingProviderKey, timeout_for_input
from backend.settings import (
    effective_langsmith_model_name,
    langsmith_metadata,
    langsmith_tags,
    settings,
)


if TYPE_CHECKING:
    from backend.llm.claude_client import DeliRChatAnthropic


class DeliRChatOpenAI(ChatOpenAI):
    """`ChatOpenAI` che dice a LangSmith come si chiama davvero il modello."""

    langsmith_provider: str = "openai"
    langsmith_model_name: str | None = None

    def _get_ls_params(self, stop: list[str] | None = None, **kwargs):
        params = super()._get_ls_params(stop=stop, **kwargs)
        params["ls_provider"] = self.langsmith_provider or "openai"
        if self.langsmith_model_name:
            params["ls_model_name"] = self.langsmith_model_name
        return params


def chat_client(
    task: LlmTask,
    *,
    model_name: str,
    streaming: bool,
    tag: str,
    reasoning_effort: str | None = None,
) -> "DeliRChatOpenAI | DeliRChatAnthropic":
    """Il client di un compito di chat, costruito dal suo profilo.

    Un modello `claude-...` (scelto in `LLM_TASK_MODELS_JSON` per `chat_turn`)
    da' un client Claude, con la cache sulla parte fissa e sulla conversazione:
    vedi `backend/llm/claude_client.py`.

    Args:
        task: `CHAT_TURN` o `CONTEXT_ROUTING`. Il profilo decide ragionamento,
            tetto sull'uscita e retry: chi chiama non li passa, cosi' non li puo'
            divergere.
        model_name: Il modello gia' normalizzato dal runtime. Non viene dal
            profilo perche' qui e' il consulente a poterlo scegliere, ed e'
            l'unico caso in cui succede.
        streaming: Il turno strema verso il frontend, l'instradamento no.
        tag: L'etichetta LangSmith di questo client.
        reasoning_effort: Il livello scelto dal consulente per il turno di chat.
            `None` usa quello del profilo; l'instradamento non lo riceve mai.

    Raises:
        MissingProviderKey: Se non c'e' una chiave configurata. Senza,
            `langchain_openai` ricadrebbe sulla variabile d'ambiente e i test
            tornerebbero a pagare.
    """
    profile = profile_for(task)
    max_tokens = profile.output_cap
    max_retries = profile.max_retries
    # Il runtime somma nel registro solo i pezzi di questi client: sono gli
    # unici che non scrivono la loro riga da se'.
    tags = [*langsmith_tags("llm", tag), TURN_METERED_TAG]
    metadata = langsmith_metadata(model_name, delir_model_name=model_name)
    effort = reasoning_effort or profile.reasoning_effort
    if provider_of(model_name) is Provider.ANTHROPIC:
        from backend.llm.claude_client import claude_client
        from backend.llm.egress import EgressBlocked, route

        # La chat va ad Anthropic solo se chi installa l'ha scelto: e' allora che
        # l'inventario la elenca fra i compiti di `llm_claude`. Un nome arrivato
        # da altrove non sposta i dati di un cliente verso un altro fornitore.
        if LlmTask.CHAT_TURN not in route(Destination.LLM_CLAUDE).tasks:
            raise EgressBlocked(
                f"La chat su {model_name} non e' dichiarata: va scelta in LLM_TASK_MODELS_JSON (chat_turn)."
            )

        return claude_client(
            model=model_name,
            max_tokens=max_tokens,
            timeout=timeout_for_input(None),
            max_retries=max_retries,
            effort=effort,
            streaming=streaming,
            # Solo il turno rimanda il prompt di prima allungato: instradamento e
            # riassunto sono chiamate singole, e il segnalibro in fondo farebbe
            # pagare una scrittura che nessuno rilegge.
            cache_conversation=task is LlmTask.CHAT_TURN,
            stream_usage=True,
            metadata=metadata,
            tags=tags,
        )

    if not settings.openai_api_key:
        raise MissingProviderKey(
            "OPENAI_API_KEY non configurata: il client della chat non puo' essere costruito."
        )

    require(Destination.LLM_CHAT)
    kwargs: dict[str, Any] = {
        "model": model_name,
        "api_key": settings.openai_api_key,
        "temperature": settings.model_temperature,
        "max_tokens": max_tokens,
        "timeout": timeout_for_input(None),
        # `retry=True` nel profilo vuol dire "dietro non c'e' nessuna coda": un
        # 429 transitorio diventerebbe un errore in faccia al consulente a meta'
        # conversazione.
        "max_retries": max_retries,
        "streaming": streaming,
        "langsmith_provider": settings.langsmith_provider,
        "langsmith_model_name": effective_langsmith_model_name(model_name),
        "metadata": metadata,
        "tags": tags,
        "reasoning_effort": effort,
    }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    if streaming:
        # Senza questo i pezzi arrivano senza `usage_metadata` e il turno
        # risulterebbe da zero token: e' la stessa trappola delle chiamate
        # strutturate, in un'altra forma.
        kwargs["stream_usage"] = True
    # Come per gli altri compiti: se LangSmith e' spento la traccia la scriviamo
    # su file, cosi' un turno resta leggibile anche senza il servizio esterno.
    callbacks = local_callbacks()
    if callbacks:
        kwargs["callbacks"] = callbacks
    return DeliRChatOpenAI(**kwargs)
