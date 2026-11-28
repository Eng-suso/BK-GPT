"""kwargs condivisi per costruire `ChatOpenAI` dai settings.

Un solo posto per la policy sui parametri modello (reasoning controls, timeout,
streaming). Usato dai builder task-scoped (`process_understanding`,
`memory/procedural/extraction`). L'agente runtime (`backend/agent.py`) usa la
sottoclasse `DeliRChatOpenAI` con la sua config di streaming/langsmith e resta
separato di proposito.
"""

from __future__ import annotations

from typing import Any

from backend.settings import settings


class MissingProviderKey(RuntimeError):
    """Nessuna chiave del provider: il client non si costruisce.

    Non e' un errore di rete ne' un guasto transitorio: e' configurazione. Chi
    la intercetta la traduce nel proprio esito dichiarato (`configuration_error`),
    non la ritenta.
    """


def supports_reasoning_controls(model: str) -> bool:
    return model.lower().startswith(("gpt-5", "o1", "o3", "o4"))


def timeout_for_input(characters: int | None) -> int:
    """Timeout della chiamata, proporzionato alla lunghezza dell'input.

    Un timeout costante tarato sul caso breve e' un costo travestito da limite:
    l'estrazione di un'intervista di 4.000 caratteri scadeva a 45 s, il tempo
    speso veniva pagato, il risultato buttato e il tentativo rifatto. Il caso
    Esaote e' nato cosi'.

    Parameters:
        characters: Lunghezza dell'input in caratteri. `None` per i compiti la
            cui dimensione non si conosce prima: si usa il pavimento.

    Returns:
        Secondi, fra `model_timeout_seconds` e `model_timeout_max_seconds`.
    """
    floor = settings.model_timeout_seconds
    if not characters or characters <= 0:
        return floor
    scaled = floor + (characters * settings.model_timeout_per_1k_chars) // 1000
    return min(max(floor, scaled), settings.model_timeout_max_seconds)


def prompt_cache_body(task_name: str) -> dict[str, Any] | None:
    """Il `prompt_cache_key` di OpenAI per un compito, nel corpo della richiesta.

    OpenAI instrada sulla stessa cache le richieste con la stessa chiave: con
    piu' persone che mandano lo stesso prefisso (istruzioni e tool di un
    compito) il riuso sale e i token in ingresso si pagano a prezzo di cache.
    La chiave e' il compito, non la persona: il prefisso condiviso e' quello.

    Solo verso OpenAI: con `OPENAI_BASE_URL` puntato su un fornitore
    compatibile un campo sconosciuto potrebbe essere rifiutato. `None` = niente.
    """
    if settings.openai_base_url or not settings.llm_prompt_cache_key:
        return None
    return {"prompt_cache_key": f"delir:{task_name}"}


def chat_openai_kwargs(
    *,
    max_tokens: int | None = None,
    temperature: float = 0,
    reasoning_effort: str = "medium",
    verbosity: str = "low",
    input_characters: int | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """kwargs per `ChatOpenAI(**chat_openai_kwargs())` — non-streaming, task-scoped.

    `reasoning_effort` / `verbosity` sono applicati solo se il modello li
    supporta (`gpt-5*`, `o1/o3/o4*`).

    Args:
        input_characters: Lunghezza dell'input, quando chi chiama la conosce. Il
            timeout ne segue la scala (`timeout_for_input`). Omesso, si usa il
            pavimento: giusto per i compiti corti, non per un'intervista.
        model: Il modello, quando non e' quello di conversazione
            (`LLM_TASK_MODELS_JSON`). I parametri di ragionamento si decidono
            su questo, non sul modello di conversazione.

    Raises:
        MissingProviderKey: Se non c'e' una chiave configurata. Chi chiama non
            deve ricevere kwargs che *sembrano* validi: senza chiave
            `langchain_openai` ricadrebbe su `OPENAI_API_KEY` dell'ambiente, e
            l'errore arriverebbe dal provider invece che da qui.
        EgressBlocked: Se l'endpoint della chat e' esterno e non autorizzato
            (`backend/llm/egress.py`). E' una `MissingProviderKey`: stessa via.
    """
    from backend.llm.egress import Destination, require

    if not settings.openai_api_key:
        raise MissingProviderKey(
            "OPENAI_API_KEY non configurata: nessun client del modello puo' essere "
            "costruito. Nei test e' il comportamento atteso — un test che deve "
            "spendere si marca `live_llm` e gira con DELIR_LIVE_LLM=1."
        )
    require(Destination.LLM_CHAT)
    kwargs: dict[str, Any] = {
        "api_key": settings.openai_api_key,
        "model": model or settings.openai_model,
        "temperature": temperature,
        "timeout": timeout_for_input(input_characters),
        "max_retries": settings.model_max_retries,
        "streaming": False,
        "disable_streaming": True,
    }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if supports_reasoning_controls(kwargs["model"]):
        kwargs["reasoning_effort"] = reasoning_effort
        kwargs["verbosity"] = verbosity
    return kwargs
