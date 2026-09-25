"""Il punto di passaggio unico per le chiamate al modello.

Chi chiama dichiara **un compito**, non un modello:

    from backend.llm import LlmTask, run

    piano = run(
        task=LlmTask.PLAN_EXTRACTION,
        messages=[SystemMessage(...), HumanMessage(...)],
        output=ProcessUnderstanding,
        input_characters=len(source_text),
    )

Quello che il gateway garantisce, e che prima non era garantito da nessuno:

- **L2**: nessuna chiamata senza un'operazione aperta. Non e' pedanteria: una
  chiamata senza operazione e' spesa non attribuibile, ed e' il difetto per cui
  il credito e' finito senza che si sapesse dove;
- **L4**: ogni chiamata lascia un evento di consumo, anche se fallisce;
- un solo livello di retry, deciso dal profilo del compito.

Un dettaglio che vale la pena conoscere, perche' non e' ovvio e costa tutta la
misura: `with_structured_output()` restituisce l'oggetto parsato e **perde**
`usage_metadata`, che vive sull'`AIMessage` grezzo. Siccome quasi tutte le nostre
chiamate sono strutturate, misurarle cosi' avrebbe dato zero token su tutto. Per
questo il gateway usa `include_raw=True` e tiene entrambi: restituisce il parsato
a chi chiama, e conta i token dal grezzo.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any, TypeVar, overload

from pydantic import BaseModel

from backend.llm.operation import current_operation
from backend.llm.tasks import LlmTask, TaskProfile, profile_for
from backend.llm.usage import (
    Outcome,
    TokenUsage,
    extract_embedding_tokens,
    extract_tokens,
    extract_transcription_tokens,
    record,
    tokens_from_usage_metadata,
)
from backend.llm_config import MissingProviderKey, chat_openai_kwargs, timeout_for_input
from backend.services import degradation_counters
from backend.settings import settings

_Output = TypeVar("_Output", bound=BaseModel)


class _Gateway:
    """Segnaposto per «il giudizio lo fa il gateway».

    Non e' un client e non si costruisce niente: il gateway sceglie il modello
    dal profilo del compito quando la chiamata parte. Esiste perche' diversi
    moduli distinguono «c'e' un modello disponibile» (un oggetto) da «no»
    (`None`), e da quella distinzione dipende se un lavoro best-effort si tenta.

    Stava scritto uguale in due moduli: ora e' uno solo, perche' due segnaposti
    che devono comportarsi allo stesso modo sono due cose che possono divergere.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - solo diagnostica
        return "<gateway>"


GATEWAY = _Gateway()


class OperationNotOpen(RuntimeError):
    """Una chiamata al modello fuori da qualunque operazione (L2).

    Non e' un errore di configurazione ne' un guasto: e' un punto d'ingresso che
    si e' dimenticato di dichiarare cosa sta facendo. Si risolve aprendo
    l'operazione dove il lavoro comincia, non passandola di mano in mano.

    Se succede dentro un `ThreadPoolExecutor`, la causa e' quasi sempre un'altra:
    i thread non ereditano i `ContextVar`. Vedi `operation.inherit_operation`.
    """


def _client(profile: TaskProfile, input_characters: int | None):
    """Il client per un compito, costruito dal suo profilo.

    `max_retries` si passa al **costruttore**, non con `bind`: `bind` aggiunge
    kwargs alla chiamata API, e il fornitore rifiuterebbe un parametro che non
    conosce. E' una policy del client, non un argomento della richiesta.
    """
    from langchain_openai import ChatOpenAI

    kwargs = chat_openai_kwargs(
        max_tokens=profile.max_output_tokens,
        reasoning_effort=profile.reasoning_effort,
        # Un compito che legge poco non guadagna niente da un timeout lungo:
        # lo allunga soltanto il tempo che ci vuole ad accorgersi del guasto.
        input_characters=input_characters if profile.scales_with_input else None,
    )
    kwargs["max_retries"] = _max_retries(profile)
    return ChatOpenAI(**kwargs)


def _max_retries(profile: TaskProfile) -> int:
    """Quanti tentativi concede l'SDK a questo compito.

    La regola e' quella di P0, qui applicata per compito invece che per modulo:
    si ritenta dove non c'e' nessun altro che ritenta. Un compito con una coda
    dietro fallisce e la coda lo riprende con il suo backoff; un turno di chat
    non ha niente dietro, e un rate limit transitorio diventerebbe un errore in
    faccia al consulente.
    """
    return settings.agent_max_retries if profile.retry else settings.model_max_retries


def _error_kind(exc: BaseException) -> tuple[str, str]:
    """Classifica un guasto in `(outcome, error_kind)`.

    Il timeout ha un esito suo perche' e' l'unico guasto che si paga per intero:
    il fornitore ha lavorato, noi abbiamo buttato il risultato. Tenerlo dentro
    `error` renderebbe invisibile proprio la voce che va sorvegliata.
    """
    name = type(exc).__name__
    lowered = name.lower()
    if isinstance(exc, TimeoutError) or "timeout" in lowered:
        return Outcome.TIMEOUT, name
    return Outcome.ERROR, name


@overload
def run(
    *,
    task: LlmTask,
    messages: Any,
    output: type[_Output],
    input_characters: int | None = ...,
    prompt_version: str | None = ...,
) -> _Output: ...


@overload
def run(
    *,
    task: LlmTask,
    messages: Any,
    output: None = ...,
    input_characters: int | None = ...,
    prompt_version: str | None = ...,
) -> Any: ...


def run(
    *,
    task: LlmTask,
    messages: Any,
    output: type[_Output] | None = None,
    input_characters: int | None = None,
    prompt_version: str | None = None,
) -> Any:
    """Esegue un compito e lascia un evento di consumo.

    Le due firme dichiarate sopra servono a chi chiama: con `output` si riceve
    quel modello pydantic, senza si riceve il messaggio grezzo. Prima era `Any`
    in entrambi i casi, e un errore di schema al punto di chiamata non lo
    vedeva nessuno fino a runtime.

    Args:
        task: Il compito. Il profilo decide modello, ragionamento, timeout e
            retry: chi chiama non li passa, cosi' non li puo' divergere.
        messages: I messaggi, nella forma che langchain accetta.
        output: Lo schema pydantic della risposta, per i compiti strutturati.
            Omesso, si ottiene l'`AIMessage` grezzo.
        input_characters: Lunghezza dell'input, per i compiti il cui timeout
            scala. Ometterla su un'estrazione lunga rimette il timeout al
            pavimento, ed e' il difetto che il caso Esaote ha mostrato.
        prompt_version: La versione del prompt, che finisce nel registro. Un
            cambio di prompt cambia la spesa: senza questo campo non si riesce a
            dire quale cambio l'ha cambiata.

    Returns:
        L'oggetto `output` quando e' richiesto, altrimenti l'`AIMessage`.

    Raises:
        OperationNotOpen: Se nessun punto d'ingresso ha aperto un'operazione (L2).
        MissingProviderKey: Se non c'e' una chiave configurata.
    """
    operation = current_operation()
    if operation is None:
        raise OperationNotOpen(
            f"il compito {task.value} e' stato chiesto fuori da un'operazione: "
            "apri `llm.operation(...)` nel punto d'ingresso, e usa "
            "`inherit_operation` se il lavoro passa a un thread."
        )

    profile = profile_for(task)
    model = profile.model

    try:
        client = _client(profile, input_characters)
    except MissingProviderKey:
        # Non e' una chiamata: e' una chiamata che non e' partita. Va comunque
        # registrata, altrimenti un'installazione senza chiave sembra
        # un'installazione che non spende perche' e' efficiente.
        record(
            operation=operation,
            task=task.value,
            model=model,
            outcome=Outcome.REFUSED,
            error_kind="MissingProviderKey",
            prompt_version=prompt_version,
            reasoning_effort=profile.reasoning_effort,
        )
        raise

    runnable = client if output is None else client.with_structured_output(output, include_raw=True)

    started = time.perf_counter()
    try:
        from backend.llm_streaming import stream_to_final

        result = stream_to_final(runnable, messages)
    except BaseException as exc:
        outcome, error_kind = _error_kind(exc)
        record(
            operation=operation,
            task=task.value,
            model=model,
            outcome=outcome,
            error_kind=error_kind,
            duration_ms=int((time.perf_counter() - started) * 1000),
            prompt_version=prompt_version,
            reasoning_effort=profile.reasoning_effort,
        )
        raise

    duration_ms = int((time.perf_counter() - started) * 1000)

    if output is None:
        record(
            operation=operation,
            task=task.value,
            model=model,
            outcome=Outcome.OK,
            tokens=extract_tokens(result),
            duration_ms=duration_ms,
            prompt_version=prompt_version,
            reasoning_effort=profile.reasoning_effort,
        )
        return result

    # `include_raw=True`: il grezzo porta i token, il parsato e' cio' che serve a
    # chi chiama. Senza questo, ogni chiamata strutturata - cioe' quasi tutte -
    # risulterebbe da zero token.
    raw = result.get("raw") if isinstance(result, dict) else None
    parsed = result.get("parsed") if isinstance(result, dict) else result
    parsing_error = result.get("parsing_error") if isinstance(result, dict) else None
    tokens = extract_tokens(raw) if raw is not None else TokenUsage()

    if parsing_error is not None or parsed is None:
        # Il fornitore ha risposto e va pagato: l'esito e' un errore *nostro*
        # sullo schema, non una chiamata che non e' avvenuta.
        record(
            operation=operation,
            task=task.value,
            model=model,
            outcome=Outcome.ERROR,
            tokens=tokens,
            error_kind="invalid_structured_output",
            duration_ms=duration_ms,
            prompt_version=prompt_version,
            reasoning_effort=profile.reasoning_effort,
        )
        if parsing_error is not None:
            raise parsing_error
        raise ValueError(f"{task.value}: risposta strutturata vuota")

    record(
        operation=operation,
        task=task.value,
        model=model,
        outcome=Outcome.OK,
        tokens=tokens,
        duration_ms=duration_ms,
        prompt_version=prompt_version,
        reasoning_effort=profile.reasoning_effort,
    )
    return parsed


@lru_cache(maxsize=1)
def _embedding_client() -> Any:
    """Il client dell'embedding: SDK OpenAI nudo, non langchain.

    Raises:
        MissingProviderKey: Se non c'e' una chiave configurata. Stessa regola di
            `chat_openai_kwargs`: senza chiave l'SDK ricadrebbe su
            `OPENAI_API_KEY` dell'ambiente, e i test tornerebbero a pagare.
    """
    if not settings.openai_api_key:
        raise MissingProviderKey(
            "OPENAI_API_KEY non configurata: nessun client di embedding puo' "
            "essere costruito."
        )
    from openai import OpenAI

    profile = profile_for(LlmTask.EMBEDDING)
    return OpenAI(
        api_key=settings.openai_api_key,
        max_retries=_max_retries(profile),
        timeout=timeout_for_input(None),
    )


def embed(*, texts: list[str], dimensions: int) -> list[list[float]]:
    """Calcola gli embedding di piu' testi, e lascia un evento di consumo.

    Sta qui e non in `memory/embeddings.py` per la stessa ragione di ogni altra
    chiamata: nell'ingestione del knowledge graph il volume sta negli embedding,
    quindi un registro che li salta racconta una spesa che non e' quella vera.

    Args:
        texts: I testi, gia' ripuliti da chi chiama.
        dimensions: La dimensione dei vettori. E' un contratto dello schema del
            database, non una scelta di questa chiamata: la decide
            `memory.embeddings`, che possiede l'invariante.

    Returns:
        Un vettore per testo, nello stesso ordine.

    Raises:
        OperationNotOpen: Se nessun punto d'ingresso ha aperto un'operazione (L2).
        MissingProviderKey: Se non c'e' una chiave configurata.
    """
    operation = current_operation()
    if operation is None:
        raise OperationNotOpen(
            "un embedding e' stato chiesto fuori da un'operazione: apri "
            "`llm.operation(...)` nel punto d'ingresso. Nell'ingestione KG e' "
            "la voce di spesa piu' grossa, e non attribuirla e' il difetto da "
            "cui e' nato il gateway."
        )

    profile = profile_for(LlmTask.EMBEDDING)
    model = profile.model

    try:
        client = _embedding_client()
    except MissingProviderKey:
        record(
            operation=operation,
            task=LlmTask.EMBEDDING.value,
            model=model,
            outcome=Outcome.REFUSED,
            error_kind="MissingProviderKey",
            reasoning_effort=profile.reasoning_effort,
        )
        raise

    started = time.perf_counter()
    try:
        response = client.embeddings.create(model=model, input=texts, dimensions=dimensions)
    except BaseException as exc:
        outcome, error_kind = _error_kind(exc)
        record(
            operation=operation,
            task=LlmTask.EMBEDDING.value,
            model=model,
            outcome=outcome,
            error_kind=error_kind,
            duration_ms=int((time.perf_counter() - started) * 1000),
            reasoning_effort=profile.reasoning_effort,
        )
        raise

    record(
        operation=operation,
        task=LlmTask.EMBEDDING.value,
        model=model,
        outcome=Outcome.OK,
        tokens=extract_embedding_tokens(response),
        duration_ms=int((time.perf_counter() - started) * 1000),
        reasoning_effort=profile.reasoning_effort,
    )
    return [item.embedding for item in response.data]


_transcription_client: Any | None = None
_transcription_client_key: str | None = None


def _transcription_client_for(api_key: str) -> Any:
    """Il client della trascrizione, ricostruito solo se la chiave cambia.

    Riusarlo tiene in piedi il pool di connessioni, che con un upload in corso
    conta. La chiave pero' fa parte dello stato e non e' un parametro qualunque:
    un client costruito prima di una rotazione continuerebbe a presentare la
    chiave vecchia per tutta la vita del processo, e il guasto si vedrebbe come
    un 401 che non passa mai.
    """
    global _transcription_client, _transcription_client_key

    if _transcription_client is None or _transcription_client_key != api_key:
        from openai import AsyncOpenAI

        _transcription_client = AsyncOpenAI(
            api_key=api_key,
            timeout=settings.openai_transcription_timeout_seconds,
            max_retries=settings.transcription_max_retries,
        )
        _transcription_client_key = api_key
    return _transcription_client


async def transcribe(*, file: Any, options: dict[str, Any]) -> Any:
    """Trascrive un audio e lascia un evento di consumo.

    E' l'unico punto di chiamata `async` che abbiamo, e per questo ha un
    ingresso suo invece di passare da `run()`.

    Sul conteggio: non tutti i modelli di trascrizione fatturano a token -
    whisper si paga al minuto di audio - quindi la riga puo' avere zero token.
    Si scrive lo stesso, con il modello e l'esito: «una trascrizione e'
    avvenuta» e' l'informazione che serve, e un'ora di audio che non lascia
    traccia e' spesa invisibile come lo erano gli embedding.

    Corollario per chi configura: un modello che fattura al minuto **non** va
    messo in `LLM_PRICES_JSON`. A listino, zero token darebbero un costo di
    zero - plausibile e falso, il tipo di numero su cui poi si fanno i budget.
    Fuori listino il costo resta `NULL`, che e' la verita': lo sappiamo dalla
    fattura, non da qui.

    Args:
        file: La tupla `(nome, contenuto, content_type)` che l'SDK si aspetta.
        options: Le opzioni gia' costruite da chi chiama. Dipendono dal modello
            (`response_format` e `chunking_strategy` esistono solo sui modelli
            che diarizzano), quindi chi le costruisce ha gia' dovuto sapere quale
            modello gira e lo lascia qui dentro: il registro scrive **quello**,
            non quello del profilo, cosi' la riga dice cosa e' girato davvero
            anche se le due fonti divergessero. Senza `model` si usa il profilo.

    Raises:
        OperationNotOpen: Se la rotta non ha aperto un'operazione (L2).
        MissingProviderKey: Se non c'e' una chiave configurata.
    """
    operation = current_operation()
    if operation is None:
        raise OperationNotOpen(
            "una trascrizione e' stata chiesta fuori da un'operazione: apri "
            "`llm.operation(OperationKind.TRANSCRIPTION)` nella rotta."
        )

    profile = profile_for(LlmTask.TRANSCRIPTION)
    model = str(options.get("model") or profile.model)
    options = {**options, "model": model}

    if not settings.openai_api_key:
        record(
            operation=operation,
            task=LlmTask.TRANSCRIPTION.value,
            model=model,
            outcome=Outcome.REFUSED,
            error_kind="MissingProviderKey",
            reasoning_effort=profile.reasoning_effort,
        )
        raise MissingProviderKey("OPENAI_API_KEY non configurata: trascrizione non eseguibile.")

    client = _transcription_client_for(settings.openai_api_key)

    started = time.perf_counter()
    try:
        risposta = await client.audio.transcriptions.create(file=file, **options)
    except BaseException as exc:
        outcome, error_kind = _error_kind(exc)
        record(
            operation=operation,
            task=LlmTask.TRANSCRIPTION.value,
            model=model,
            outcome=outcome,
            error_kind=error_kind,
            duration_ms=int((time.perf_counter() - started) * 1000),
            reasoning_effort=profile.reasoning_effort,
        )
        raise

    record(
        operation=operation,
        task=LlmTask.TRANSCRIPTION.value,
        model=model,
        outcome=Outcome.OK,
        tokens=extract_transcription_tokens(risposta),
        duration_ms=int((time.perf_counter() - started) * 1000),
        reasoning_effort=profile.reasoning_effort,
    )
    return risposta


def record_streamed_usage(
    task: LlmTask,
    usage_metadata: dict[str, Any] | None,
    *,
    model: str | None = None,
    duration_ms: int = 0,
) -> None:
    """Registra il consumo di una chiamata **stremata**, a stream finito.

    E' l'altra meta' di `chat_client`: la chat non passa da `run()` perche' il
    modello lo esegue LangGraph e il risultato esce a pezzi verso il frontend.
    I token pero' arrivano lo stesso - `stream_usage=True` li mette
    sull'ultimo pezzo - e il runtime li somma gia' per mandarli al frontend.
    Questa funzione prende quella somma e la scrive nel registro.

    Non solleva: un turno andato a buon fine non si rovina perche' la sua
    contabilita' non e' riuscita. Se manca l'operazione la riga si perde, ma lo
    dice il contatore di degradazione invece di sparire in silenzio.

    Args:
        task: `CHAT_TURN` per il turno, `CONTEXT_ROUTING` per l'instradamento.
            Il runtime li distingue per nodo del grafo: sono due compiti con due
            profili, e sommarli renderebbe invisibile il piu' economico dei due.
        usage_metadata: La somma dei token nella forma di langchain.
        model: Il modello che ha girato davvero. La chat e' l'unico compito in
            cui lo sceglie il consulente, quindi il modello del profilo qui
            sarebbe una supposizione - e il costo stimato verrebbe da un
            listino che non c'entra.
        duration_ms: Quanto e' durato lo stream.
    """
    if not usage_metadata:
        return

    operation = current_operation()
    if operation is None:
        degradation_counters.bump(
            "llm_usage",
            "streamed_usage_without_operation",
            detail=task.value,
        )
        return

    profile = profile_for(task)
    record(
        operation=operation,
        task=task.value,
        model=model or profile.model,
        outcome=Outcome.OK,
        tokens=tokens_from_usage_metadata(usage_metadata),
        duration_ms=duration_ms,
        reasoning_effort=profile.reasoning_effort,
    )


def record_avoided_call(task: LlmTask, *, prompt_version: str | None = None) -> None:
    """Registra una chiamata **non** fatta perche' l'artefatto c'era gia'.

    E' il numero piu' importante del piano e il piu' facile da dimenticare: senza
    questa riga, il lavoro di P2 - non rileggere le interviste che non sono
    cambiate - risulta come un'assenza di spesa indistinguibile dall'inattivita'.
    Un risparmio che non si misura non si difende.
    """
    operation = current_operation()
    if operation is None:
        raise OperationNotOpen(
            f"colpo di cache per {task.value} fuori da un'operazione: "
            "anche il lavoro evitato appartiene a un lavoro."
        )
    record(
        operation=operation,
        task=task.value,
        model=profile_for(task).model,
        outcome=Outcome.CACHE_HIT,
        prompt_version=prompt_version,
        reasoning_effort=profile_for(task).reasoning_effort,
    )
