"""Le tracce di un turno, tenute in memoria e potate.

La traccia serve a leggere cosa ha fatto l'agente subito dopo che l'ha fatto:
vive in memoria perche' e' materiale di diagnosi, non un archivio. Il prezzo di
tenerla in memoria e' che va potata, e non lo era: `_TRACE_EVENTS` cresceva a
ogni turno e nessuno chiamava mai `clear_trace`. Un processo che sta su per
giorni finiva per tenere in RAM ogni evento di ogni turno, payload compresi.

Qui i limiti sono due, entrambi dichiarati: quante tracce si ricordano
(`MAX_TRACES`, le piu' vecchie escono per prime) e quanti eventi per traccia
(`MAX_EVENTS_PER_TRACE`, il deque lascia cadere i piu' vecchi). Nessuno dei due
cambia cosa si legge subito dopo un turno, che e' l'unico momento in cui la
traccia viene guardata davvero.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from threading import Lock
from time import perf_counter
from uuid import uuid4

from backend.schemas.api import AgentTraceEvent, TraceContext
from backend.security import get_current_tenant_id


#: Quante tracce restano leggibili. Oltre, esce la piu' vecchia. Duecento turni
#: coprono una giornata di lavoro di piu' consulenti: chi guarda una traccia lo
#: fa entro pochi minuti dal turno, non il giorno dopo.
MAX_TRACES = 200

#: Quanti eventi si tengono per traccia. Un turno normale ne produce qualche
#: decina; oltre il migliaio c'e' un ciclo che non termina, e in quel caso
#: servono la coda e non l'inizio.
MAX_EVENTS_PER_TRACE = 1000

_TRACE_EVENTS: OrderedDict[str, deque[AgentTraceEvent]] = OrderedDict()
_TRACE_STARTS: dict[str, float] = {}
# Lo spazio di lavoro che ha generato la traccia. Il `trace_id` viaggia fino al
# client nell'evento `start`, quindi senza questo chiunque lo conosca puo'
# rileggere il turno di un altro: prompt, tool e argomenti compresi.
_TRACE_TENANTS: dict[str, str] = {}
# Gli eventi arrivano anche dal thread che esegue l'agente: l'inserimento e lo
# sfratto della traccia piu' vecchia sono due operazioni, e fra le due il
# dizionario non deve cambiare sotto i piedi.
_GUARD = Lock()


def _open_trace(trace_id: str) -> deque[AgentTraceEvent]:
    """Apre una traccia nuova, facendo posto se le tracce ricordate sono troppe."""
    events: deque[AgentTraceEvent] = deque(maxlen=MAX_EVENTS_PER_TRACE)
    _TRACE_EVENTS[trace_id] = events
    while len(_TRACE_EVENTS) > MAX_TRACES:
        evicted, _ = _TRACE_EVENTS.popitem(last=False)
        _TRACE_STARTS.pop(evicted, None)
        _TRACE_TENANTS.pop(evicted, None)
    return events


def new_trace_context(
    *,
    request_id: str | None = None,
    thread_id: str | None = None,
    checkpoint_thread_id: str | None = None,
    scope_type: str | None = None,
    scope_key: str | None = None,
    model_name: str | None = None,
) -> TraceContext:
    trace_id = str(uuid4())
    context = TraceContext(
        request_id=request_id or str(uuid4()),
        trace_id=trace_id,
        thread_id=thread_id,
        checkpoint_thread_id=checkpoint_thread_id,
        scope_type=scope_type,
        scope_key=scope_key,
        model_name=model_name,
    )
    with _GUARD:
        _open_trace(trace_id)
        _TRACE_STARTS[trace_id] = perf_counter()
        _TRACE_TENANTS[trace_id] = get_current_tenant_id()
    return context


def elapsed_ms(trace_id: str) -> int:
    started_at = _TRACE_STARTS.get(trace_id)
    if started_at is None:
        return 0
    return int((perf_counter() - started_at) * 1000)


def record_trace_event(event: AgentTraceEvent) -> AgentTraceEvent:
    """Aggiunge l'evento alla sua traccia, se quella traccia esiste ancora.

    Una traccia sfrattata non torna indietro. Ricrearla qui sembrava innocuo e
    non lo era: la riga nuova nasce senza lo spazio di lavoro di chi l'ha
    generata, quindi nessuno puo' piu' leggerla, e intanto occupa un posto -
    sfrattando una traccia viva al suo posto. Un turno lungo abbastanza da farsi
    sfrattare avrebbe riempito la memoria di tracce invisibili.
    """
    with _GUARD:
        events = _TRACE_EVENTS.get(event.trace_id)
        if events is not None:
            events.append(event)
    return event


def trace_event(
    context: TraceContext,
    event_type: str,
    *,
    node: str | None = None,
    route: str | None = None,
    tool_name: str | None = None,
    status: str = "ok",
    message: str | None = None,
    payload: dict | None = None,
) -> AgentTraceEvent:
    return record_trace_event(
        AgentTraceEvent(
            trace_id=context.trace_id,
            event_type=event_type,
            node=node,
            route=route,
            tool_name=tool_name,
            status=status,
            message=message,
            payload=payload or {},
            elapsed_ms=elapsed_ms(context.trace_id),
        )
    )


def read_trace(trace_id: str, *, tenant_id: str) -> list[AgentTraceEvent] | None:
    """Gli eventi della traccia, se e' di chi la chiede.

    Lo spazio di lavoro e' obbligatorio e non ha un default: una lettura senza
    controllo non deve essere la cosa piu' facile da scrivere.

    Args:
        trace_id: La traccia cercata.
        tenant_id: Lo spazio di lavoro del chiamante.

    Returns:
        list[AgentTraceEvent] | None: Gli eventi, oppure `None` se la traccia non
            esiste **o** e' di un altro spazio. I due casi rispondono uguale di
            proposito: chi prova un `trace_id` altrui non deve nemmeno scoprire
            che e' valido.
    """
    with _GUARD:
        if _TRACE_TENANTS.get(trace_id) != tenant_id:
            return None
        return list(_TRACE_EVENTS.get(trace_id, ()))


def clear_trace(trace_id: str) -> None:
    with _GUARD:
        _TRACE_EVENTS.pop(trace_id, None)
        _TRACE_STARTS.pop(trace_id, None)
        _TRACE_TENANTS.pop(trace_id, None)


def traced_count() -> int:
    """Quante tracce sono in memoria adesso. La misura del tetto di `MAX_TRACES`."""
    with _GUARD:
        return len(_TRACE_EVENTS)
