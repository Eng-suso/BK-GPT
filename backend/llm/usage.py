"""Scrivere e leggere il registro dei consumi.

Una regola sola, e vale la pena dirla prima del codice: **il registro non fa
cadere il lavoro.** Se la scrittura dell'evento fallisce - database occupato,
migrazione a meta', disco pieno - il consulente deve comunque avere la sua
risposta. Un sistema di misura che rompe la cosa che misura viene spento al primo
incidente, e allora non misura piu' niente.

Il contrario - perdere l'evento in silenzio - e' altrettanto inaccettabile, ed e'
per questo che il fallimento si conta in `degradation_counters`: il registro puo'
perdere una riga, ma non puo' perderla di nascosto.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from backend.llm.operation import Operation
from backend.llm.prices import estimate_cost
from backend.services import degradation_counters

logger = logging.getLogger(__name__)


class Outcome:
    """Com'e' finita una chiamata.

    `CACHE_HIT` non e' un esito del fornitore: e' DeliR che ha evitato la
    chiamata perche' l'artefatto c'era gia'. E' il risultato migliore che
    possiamo avere, quindi ha bisogno di un nome e di una riga.
    """

    OK = "ok"
    TIMEOUT = "timeout"
    ERROR = "error"
    CACHE_HIT = "cache_hit"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """I token di una chiamata.

    `reasoning` e' un **sottoinsieme** di `output`, non un addendo: il fornitore
    fattura i token di ragionamento come uscita anche quando non li mostra.
    Sommarli a parte gonfierebbe ogni stima.
    """

    input: int = 0
    output: int = 0
    reasoning: int = 0
    cached_input: int = 0


def record(
    *,
    operation: Operation,
    task: str,
    model: str,
    outcome: str,
    tokens: TokenUsage | None = None,
    duration_ms: int = 0,
    prompt_version: str | None = None,
    reasoning_effort: str | None = None,
    error_kind: str | None = None,
    attempt: int = 1,
) -> None:
    """Scrive un evento di consumo. Non solleva mai.

    Args:
        operation: L'operazione dentro cui la chiamata e' avvenuta.
        task: Il compito, dal valore di `LlmTask`.
        model: Il modello, come lo nomina il fornitore.
        outcome: Uno dei valori di `Outcome`.
        tokens: I token consumati. Omessi per un `cache_hit` o per un rifiuto,
            dove non c'e' stata nessuna chiamata.
        duration_ms: Durata della chiamata. Per un `cache_hit` e' il tempo
            risparmiato solo in apparenza: si lascia a 0 e non si finge.
        prompt_version: La versione del prompt usato, quando il chiamante la
            conosce. Un cambio di prompt cambia la spesa, e senza questa colonna
            non si riesce a dire quale cambio l'ha cambiata.
        reasoning_effort: Il livello di ragionamento chiesto. Serve a misurare se
            abbassarlo su un compito ha davvero ridotto la spesa.
        error_kind: La classe del guasto, quando `outcome` non e' `ok`.
        attempt: Quale tentativo era. Un secondo tentativo e' una riga sua: e'
            cosi' che «quanto costano i retry» diventa una query.
    """
    counted = tokens or TokenUsage()
    cost = estimate_cost(
        model,
        input_tokens=counted.input,
        output_tokens=counted.output,
        cached_input_tokens=counted.cached_input,
    )

    try:
        from backend.workspace_storage import WorkspaceLlmUsage, workspace_connection

        with workspace_connection() as session:
            session.add(
                WorkspaceLlmUsage(
                    id=uuid.uuid4().hex,
                    tenant_id=operation.tenant_id,
                    operation_kind=operation.kind,
                    operation_id=operation.id,
                    parent_operation_id=operation.parent_id,
                    project_id=operation.project_id,
                    process_id=operation.process_id,
                    task=task,
                    model=model,
                    prompt_version=prompt_version,
                    reasoning_effort=reasoning_effort,
                    input_tokens=counted.input,
                    output_tokens=counted.output,
                    reasoning_tokens=counted.reasoning,
                    cached_input_tokens=counted.cached_input,
                    outcome=outcome,
                    error_kind=error_kind,
                    duration_ms=max(0, duration_ms),
                    attempt=attempt,
                    cost_estimate=str(cost) if cost is not None else None,
                    created_at=datetime.now(UTC).isoformat(),
                )
            )
    except Exception as exc:  # noqa: BLE001
        # Il registro non fa cadere il lavoro. Ma non perde una riga di nascosto:
        # il contatore di degradazione e' il posto dove questo si vede.
        degradation_counters.bump("llm_usage", "ledger_write_failed", detail=str(exc))
        logger.warning("registro dei consumi: evento perso (%s)", type(exc).__name__, exc_info=True)


def extract_tokens(response: object) -> TokenUsage:
    """Legge i token da una risposta langchain.

    `usage_metadata` c'e' gia' su ogni risposta: non serve telemetria nuova,
    serviva soltanto scriverla da qualche parte. La forma e'

        {"input_tokens": n, "output_tokens": n, "total_tokens": n,
         "input_token_details": {"cache_read": n},
         "output_token_details": {"reasoning": n}}

    Un fornitore che non li manda da' una risposta senza `usage_metadata`: si
    registrano zero token con l'esito vero, invece di non registrare niente. Una
    chiamata avvenuta e non contata e' peggio di una contata male: la prima non
    si vede, la seconda si corregge.
    """
    return tokens_from_usage_metadata(getattr(response, "usage_metadata", None))


def tokens_from_usage_metadata(metadata: object) -> TokenUsage:
    """Gli stessi token, quando chi chiama ha gia' il dizionario e non la risposta.

    E' il caso della chat: il runtime somma gli `usage_metadata` dei pezzi
    mentre li manda al frontend, e alla fine ha la somma, non un messaggio.
    """
    if not isinstance(metadata, dict):
        return TokenUsage()

    def _count(value: object) -> int:
        return value if isinstance(value, int) and value >= 0 else 0

    input_details = metadata.get("input_token_details")
    output_details = metadata.get("output_token_details")

    return TokenUsage(
        input=_count(metadata.get("input_tokens")),
        output=_count(metadata.get("output_tokens")),
        reasoning=_count((output_details or {}).get("reasoning") if isinstance(output_details, dict) else 0),
        cached_input=_count((input_details or {}).get("cache_read") if isinstance(input_details, dict) else 0),
    )


def extract_embedding_tokens(response: object) -> TokenUsage:
    """Legge i token da una risposta di embedding dell'SDK OpenAI.

    Forma diversa da quella di langchain, ed e' la ragione per cui questa
    funzione esiste invece di riusare `extract_tokens`: qui i token stanno in
    `response.usage.prompt_tokens`, non in `usage_metadata`. Leggere la risposta
    dell'embedding col lettore della chat avrebbe dato zero token su tutto il
    volume dell'ingestione, cioe' proprio dove il volume sta.

    Un embedding non produce token in uscita: `output` resta 0, e non e' un dato
    mancante.
    """
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    if not isinstance(prompt_tokens, int) or prompt_tokens < 0:
        return TokenUsage()
    return TokenUsage(input=prompt_tokens)


def extract_transcription_tokens(response: object) -> TokenUsage:
    """Legge i token da una risposta di trascrizione, quando ci sono.

    Terza forma dopo quella di langchain e quella degli embedding, e la ragione
    e' il listino: i modelli di trascrizione a token riportano
    `usage.input_tokens` / `usage.output_tokens`, mentre whisper si paga al
    minuto di audio e di token non ne dichiara nessuno. Zero token qui non vuol
    dire "gratis": vuol dire che questo modello non si misura cosi'. La riga
    resta, col modello e l'esito, perche' un'ora di audio senza traccia e'
    spesa invisibile.
    """
    usage = response.get("usage") if isinstance(response, Mapping) else getattr(response, "usage", None)
    if usage is None:
        return TokenUsage()

    def _campo(nome: str) -> object:
        # La rotta della trascrizione tratta gia' la risposta sia come oggetto
        # sia come dizionario (`openai_object_to_dict`): leggerla qui in un modo
        # solo perderebbe i token in silenzio sulla forma sbagliata, che e'
        # esattamente il guasto che questo modulo esiste per evitare.
        if isinstance(usage, Mapping):
            return usage.get(nome)
        return getattr(usage, nome, None)

    def _count(value: object) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    return TokenUsage(
        input=_count(_campo("input_tokens")),
        output=_count(_campo("output_tokens")),
    )
