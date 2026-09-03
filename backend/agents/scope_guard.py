"""Runtime enforcement dello scope di progetto per un agent run.

Problema (review G3): i tool project/process ricevono `project_id` come
argomento *deciso dall'LLM* (`Field(description="Current project id.")`).
Lo scope autorizzato del thread arriva da UI/backend e vive nello state +
system prompt, ma niente impedisce a un tool call di portare un `project_id`
diverso — prompt injection in un documento caricato puo' spostare
letture/scritture su un altro cliente dello stesso consulente.

`bind_active_scope` fissa lo scope autorizzato in un `ContextVar` per la
durata dello stream dell'agente; `assert_project_in_scope` viene chiamato dai
chokepoint (`memory.scope.resolve`, `gateway.workspace_read`,
`graphs/project/tools._project_payload`) e solleva `ScopeViolation` se il
`project_id` non combacia.

Nota: e' una difesa in profondita', non il fix strutturale completo. Se
LangGraph esegue un nodo in un thread separato il ContextVar non propaga e il
guard degrada a no-op (fail-open, non falso positivo). Il fix definitivo e'
spostare `project_id`/`process_id` su `InjectedState` (pattern gia' usato in
`toolsets/bpmn.py`). Fuori da un agent run (worker, cutover, test) il guard e'
un no-op: quei chiamanti sono fidati e il payload e' gia' stato validato in
fase di enqueue dentro un run vincolato.
"""

from __future__ import annotations

import contextvars
import logging
from collections.abc import Iterator
from contextlib import contextmanager

from backend.schemas.chat import ChatScope

logger = logging.getLogger(__name__)

_active_scope: contextvars.ContextVar[ChatScope | None] = contextvars.ContextVar(
    "active_chat_scope", default=None
)


class ScopeViolation(RuntimeError):
    """Un tool ha usato un project_id fuori dallo scope autorizzato del thread."""


@contextmanager
def bind_active_scope(scope: ChatScope | None) -> Iterator[None]:
    token = _active_scope.set(scope)
    try:
        yield
    finally:
        _active_scope.reset(token)


def active_scope() -> ChatScope | None:
    return _active_scope.get()


def assert_project_in_scope(project_id: str | None) -> None:
    """Solleva se `project_id` non e' quello autorizzato per il run corrente.

    No-op quando non c'e' uno scope vincolato (worker/test/cutover).
    """
    scope = _active_scope.get()
    if scope is None:
        return

    bound = getattr(scope, "project_id", None)
    requested = str(project_id).strip() if project_id else ""

    if bound:
        if requested and requested != str(bound):
            raise ScopeViolation(
                f"tool con project_id={requested!r} fuori dallo scope autorizzato "
                f"(project_id={bound!r}, scope={scope.type})"
            )
        return

    # scope consultant/home: nessun progetto autorizzato. Un tool che passa un
    # project_id qui non dovrebbe nemmeno essere bindato: rifiuta.
    if requested:
        raise ScopeViolation(
            f"tool con project_id={requested!r} ma lo scope del thread e' "
            f"'{scope.type}' (nessun progetto autorizzato)"
        )
