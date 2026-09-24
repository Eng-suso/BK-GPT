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

from typing import Any

from langchain_openai import ChatOpenAI

from backend.llm.tasks import LlmTask, profile_for
from backend.llm_config import MissingProviderKey, timeout_for_input
from backend.settings import (
    effective_langsmith_model_name,
    langsmith_metadata,
    langsmith_tags,
    settings,
)


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
) -> DeliRChatOpenAI:
    """Il client di un compito di chat, costruito dal suo profilo.

    Args:
        task: `CHAT_TURN` o `CONTEXT_ROUTING`. Il profilo decide ragionamento,
            tetto sull'uscita e retry: chi chiama non li passa, cosi' non li puo'
            divergere.
        model_name: Il modello gia' normalizzato dal runtime. Non viene dal
            profilo perche' qui e' il consulente a poterlo scegliere, ed e'
            l'unico caso in cui succede.
        streaming: Il turno strema verso il frontend, l'instradamento no.
        tag: L'etichetta LangSmith di questo client.

    Raises:
        MissingProviderKey: Se non c'e' una chiave configurata. Senza,
            `langchain_openai` ricadrebbe sulla variabile d'ambiente e i test
            tornerebbero a pagare.
    """
    if not settings.openai_api_key:
        raise MissingProviderKey(
            "OPENAI_API_KEY non configurata: il client della chat non puo' essere costruito."
        )

    profile = profile_for(task)
    max_tokens = profile.max_output_tokens or settings.model_max_tokens
    kwargs: dict[str, Any] = {
        "model": model_name,
        "api_key": settings.openai_api_key,
        "temperature": settings.model_temperature,
        "max_tokens": max_tokens,
        "timeout": timeout_for_input(None),
        # `retry=True` nel profilo vuol dire "dietro non c'e' nessuna coda": un
        # 429 transitorio diventerebbe un errore in faccia al consulente a meta'
        # conversazione.
        "max_retries": settings.agent_max_retries if profile.retry else settings.model_max_retries,
        "streaming": streaming,
        "langsmith_provider": settings.langsmith_provider,
        "langsmith_model_name": effective_langsmith_model_name(model_name),
        "metadata": langsmith_metadata(model_name, delir_model_name=model_name),
        "tags": langsmith_tags("llm", tag),
        "reasoning_effort": profile.reasoning_effort,
    }
    if streaming:
        # Senza questo i pezzi arrivano senza `usage_metadata` e il turno
        # risulterebbe da zero token: e' la stessa trappola delle chiamate
        # strutturate, in un'altra forma.
        kwargs["stream_usage"] = True
    return DeliRChatOpenAI(**kwargs)
