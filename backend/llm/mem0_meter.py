"""Le chiamate di Mem0 nel registro dei consumi.

Mem0 e' l'unica parte di DeliR che parla col fornitore senza passare dal
gateway: `mem0.Memory` costruisce i suoi client OpenAI dentro la libreria, e
la regola L1 (niente client fuori da `backend/llm/`) non li vede. Ogni
`memory.add()` fa almeno un embedding e, quando l'estrazione dei fatti e'
accesa, una o due chiamate di chat; ogni `memory.search()` fa un embedding.
Nessuna di queste finiva nel registro: era spesa vera e invisibile, proprio
nella memoria che lavora in background.

Qui non si costruisce un client: si avvolgono i due metodi che Mem0 chiama sui
client che ha gia' costruito, e ogni chiamata lascia la sua riga come quelle
del gateway. La libreria resta com'e'; cambia solo che adesso si vede.
"""

from __future__ import annotations

import functools
import time
from typing import Any

from backend.llm import spend_cap
from backend.llm.operation import Operation, OperationKind, current_operation, new_operation
from backend.llm.tasks import LlmTask, profile_for
from backend.llm.usage import (
    Outcome,
    classify_failure,
    extract_embedding_tokens,
    extract_openai_chat_tokens,
    record,
)
from backend.services import degradation_counters

#: Il segno lasciato su un metodo gia' avvolto: `get_memory()` e' in cache, ma un
#: secondo `meter()` sulla stessa istanza non deve contare ogni chiamata due volte.
_METERED = "_delir_metered"


def _operation() -> Operation:
    """L'operazione a cui appartiene la chiamata.

    Il gateway rifiuta una chiamata senza operazione (L2). Qui non si puo': la
    chiamata la decide Mem0, e rifiutarla significherebbe rompere la memoria per
    un difetto di contabilita'. Si fa il contrario di sparire: la riga si scrive
    sotto un'operazione di proiezione della memoria, e il contatore di
    degradazione dice che un punto d'ingresso non ha dichiarato il suo lavoro.
    """
    current = current_operation()
    if current is not None:
        return current
    degradation_counters.bump("llm_usage", "mem0_call_without_operation")
    return new_operation(OperationKind.MEMORY_PROJECTION)


_TOKEN_READERS = {
    LlmTask.MEMORY_EXTRACTION: extract_openai_chat_tokens,
    LlmTask.MEMORY_EMBEDDING: extract_embedding_tokens,
}


def _wrap(method: Any, task: LlmTask) -> Any:
    if getattr(method, _METERED, False):
        return method
    read_tokens = _TOKEN_READERS[task]

    @functools.wraps(method)
    def metered(*args: Any, **kwargs: Any) -> Any:
        operation = _operation()
        started = time.perf_counter()
        response: Any = None
        outcome, error_kind = Outcome.OK, None
        try:
            # Il freno d'emergenza vale anche per i client di Mem0, che non
            # passano dal gateway: la riga dice `refused`, e chi legge o scrive
            # la memoria ripiega come per ogni altro guasto di Mem0.
            spend_cap.check()
            response = method(*args, **kwargs)
            return response
        except spend_cap.SpendCapReached as exc:
            outcome, error_kind = Outcome.REFUSED, type(exc).__name__
            raise
        except BaseException as exc:
            outcome, error_kind = classify_failure(exc)
            raise
        finally:
            record(
                operation=operation,
                task=task.value,
                # Il modello che ha risposto, se la risposta lo dice; altrimenti
                # quello chiesto, e solo in ultima istanza quello del profilo.
                model=str(
                    getattr(response, "model", None) or kwargs.get("model") or profile_for(task).model
                ),
                outcome=outcome,
                tokens=read_tokens(response) if response is not None else None,
                error_kind=error_kind,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

    setattr(metered, _METERED, True)
    return metered


def meter(memory: Any) -> Any:
    """Avvolge i client di un'istanza `mem0.Memory`. Restituisce la stessa istanza.

    Best-effort sulla forma: se una versione futura di Mem0 rinomina gli
    attributi, la memoria continua a funzionare e il contatore di degradazione
    dice che le sue chiamate sono tornate invisibili.
    """
    targets = (
        ("llm", ("chat", "completions"), LlmTask.MEMORY_EXTRACTION),
        ("embedding_model", ("embeddings",), LlmTask.MEMORY_EMBEDDING),
    )
    for component, path, task in targets:
        resource: Any = getattr(getattr(memory, component, None), "client", None)
        for name in path:
            resource = getattr(resource, name, None)
        create = getattr(resource, "create", None)
        if create is None:
            degradation_counters.bump("llm_usage", "mem0_unmetered", detail=component)
            continue
        resource.create = _wrap(create, task)
    return memory
