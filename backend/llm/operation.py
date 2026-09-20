"""L'operazione corrente: a cosa serviva una chiamata al modello.

Un evento di consumo senza contesto dice «qualcuno ha speso 4.000 token». Non
serve a niente: non si sa per quale cliente, in quale lavoro, e se quel lavoro e'
poi arrivato da qualche parte. La domanda a cui questo modulo permette di
rispondere e' «dove sono andati i soldi ieri», e la risposta e' una query solo se
ogni chiamata porta con se' il lavoro che l'ha chiesta.

L'operazione la apre il **punto d'ingresso** - un turno di chat, «Genera BPMN»,
una passata di `plan_worker`, un eval - e la ereditano tutte le chiamate fatte
dentro, anche quelle dentro uno strumento.

I thread non ereditano niente da soli: un `ContextVar` nasce vuoto in un thread
nuovo, e il pool di estrazione gira su thread. Per quello c'e'
`inherit_operation`, che va usata **sempre** quando il lavoro passa a un pool,
altrimenti quelle chiamate - le piu' care che facciamo - risultano senza
operazione e il gateway le rifiuta.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar

from backend.security import get_current_tenant_id, reset_current_tenant_id, set_current_tenant_id

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class Operation:
    """Il lavoro dentro cui una chiamata al modello sta avvenendo.

    Attributes:
        kind: Il tipo di lavoro, da `OperationKind`. E' la dimensione con cui si
            legge la spesa: «quanto costa un turno di chat» e' un raggruppamento
            su questo campo.
        id: Identita' di *questa* esecuzione. Due ricostruzioni dello stesso
            piano sono due operazioni, ed e' cosi' che si vede il lavoro
            ripetuto.
        tenant_id: Sempre presente. La spesa non attribuibile a un tenant e' il
            problema da cui e' nato tutto questo.
        project_id: Il progetto, quando il lavoro ne ha uno.
        process_id: Il processo, quando il lavoro ne ha uno.
        parent_id: L'operazione dentro cui questa e' stata aperta, se c'era. Un
            «Genera BPMN» chiesto da una chat e' figlio di quel turno: cosi' si
            legge sia da solo sia dentro il turno che l'ha causato.
    """

    kind: str
    id: str
    tenant_id: str
    project_id: str | None = None
    process_id: str | None = None
    parent_id: str | None = None


class OperationKind:
    """I tipi di lavoro che aprono un'operazione.

    Non e' un enum perche' questi valori finiscono in una colonna e vengono
    raggruppati in query: restano stringhe, e aggiungerne uno non deve
    obbligare a migrare dei dati.
    """

    CHAT_TURN = "chat_turn"
    BPMN_DRAFT = "bpmn_draft"
    PLAN_SYNTHESIS = "plan_synthesis"
    CONFORMANCE_AUDIT = "conformance_audit"
    KG_INGESTION = "kg_ingestion"
    MEMORY_PROJECTION = "memory_projection"
    TRANSCRIPTION = "transcription"
    EVAL = "eval"


_current: ContextVar[Operation | None] = ContextVar("delir_llm_operation", default=None)


def current_operation() -> Operation | None:
    """L'operazione aperta, o `None` fuori da qualunque punto d'ingresso."""
    return _current.get()


@contextmanager
def operation(
    kind: str,
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    process_id: str | None = None,
) -> Iterator[Operation]:
    """Apre un'operazione per la durata del blocco.

    Args:
        kind: Uno dei valori di `OperationKind`.
        tenant_id: Il tenant. Omesso, si prende quello del contesto corrente -
            che e' il caso normale dentro una richiesta HTTP.
        project_id: Il progetto, quando il lavoro ne ha uno.
        process_id: Il processo, quando il lavoro ne ha uno.

    Yields:
        L'operazione aperta, se serve leggerne l'id (per esempio per scriverlo
        in un log applicativo e ritrovare la spesa di quella esecuzione).
    """
    parent = _current.get()
    opened = Operation(
        kind=kind,
        id=uuid.uuid4().hex,
        tenant_id=tenant_id or get_current_tenant_id(),
        project_id=project_id,
        process_id=process_id,
        parent_id=parent.id if parent else None,
    )
    token = _current.set(opened)
    # Il tenant dell'operazione **e'** il tenant del lavoro: si vincola anche il
    # contesto di sicurezza, cosi' i due non possono divergere. Senza questo, un
    # chiamante che passa `tenant_id` esplicito attribuirebbe la spesa a un
    # tenant e scriverebbe i dati in un altro.
    tenant_token = set_current_tenant_id(opened.tenant_id)
    try:
        yield opened
    finally:
        reset_current_tenant_id(tenant_token)
        _current.reset(token)


@contextmanager
def adopt(existing: Operation | None) -> Iterator[None]:
    """Riapre un'operazione gia' creata, in un altro thread.

    Serve a `inherit_operation` e ai worker che ricevono un'operazione da fuori.
    Non ne crea una nuova: il lavoro in un thread del pool e' *lo stesso*
    lavoro, e contarlo come operazione separata renderebbe illeggibile il costo
    per risultato.
    """
    if existing is None:
        yield
        return
    token = _current.set(existing)
    tenant_token = set_current_tenant_id(existing.tenant_id)
    try:
        yield
    finally:
        reset_current_tenant_id(tenant_token)
        _current.reset(token)


def inherit_operation(function: Callable[..., _T]) -> Callable[..., _T]:
    """Fa ereditare operazione e tenant al lavoro che passa a un altro thread.

    Da usare intorno alla funzione che si passa a un `ThreadPoolExecutor`. Il
    valore viene catturato **adesso**, nel thread che sta chiamando, e
    riapplicato dentro ogni thread del pool.

    Non si usa `contextvars.copy_context()`: lo stesso oggetto `Context` non puo'
    essere eseguito due volte in parallelo, e un pool e' esattamente il caso in
    cui succede.

    Il tenant non si cattura a parte: quello dell'operazione e' l'unico vero, e
    `adopt` lo rimette a posto. Una versione precedente lo prendeva da
    `get_current_tenant_id()` e sovrascriveva quello dell'operazione — cioe'
    lasciava che l'ambiente vincesse sul lavoro, che e' la precedenza sbagliata.
    """
    carried = _current.get()

    @wraps(function)
    def _inside_thread(*args: Any, **kwargs: Any) -> _T:
        with adopt(carried):
            return function(*args, **kwargs)

    return _inside_thread
