"""SIM-14: uno scenario del workspace come patch sulla bozza AS-IS.

La bozza e' quella del pannello scenario (un oggetto JSON che il backend non
interpreta). Uno scenario alternativo ne tiene solo le differenze, come una
lista di operazioni leggibili ("Approvatori 2 -> 3"): cambiando l'AS-IS, cio'
che lo scenario non tocca lo segue.

Un passo del percorso e' una chiave di un oggetto, oppure ``{"id": ...}`` per
l'elemento di una lista con quell'``id`` (risorse, calendari, attributi): cosi'
la patch di una risorsa resta valida se l'AS-IS ne aggiunge un'altra.

- ``set``: scrive il valore nell'ultimo passo; un elemento ``{"id"}`` assente
  si aggiunge in fondo alla lista.
- ``remove``: toglie la chiave o l'elemento; se non c'e' piu', niente.
- ``order``: rimette la lista nell'ordine degli ``ids``; gli altri restano in
  fondo, nel loro ordine.

Se un passo intermedio non esiste piu' nell'AS-IS (l'attivita' o la risorsa e'
stata tolta), l'operazione non si applica: la si segnala come conflitto invece
di inventare un oggetto a meta'. La stessa logica vive in TypeScript
(``scenarioPatch.ts``); i casi di ``tests/fixtures/simulation/scenario_patch_cases.json``
valgono per entrambe.
"""

from __future__ import annotations

import copy
from typing import Any

PathStep = str | dict[str, str]


def _step_id(step: Any) -> str | None:
    """L'id di un passo ``{"id": ...}``, o ``None`` per una chiave."""
    if isinstance(step, dict) and isinstance(step.get("id"), str):
        return step["id"]
    return None


def _find_by_id(items: list[Any], item_id: str) -> int:
    for index, item in enumerate(items):
        if isinstance(item, dict) and item.get("id") == item_id:
            return index
    return -1


def _child(container: Any, step: PathStep) -> Any:
    """Il figlio per un passo intermedio, o ``None`` se non c'e'."""
    if (step_id := _step_id(step)) is not None:
        if not isinstance(container, list):
            return None
        index = _find_by_id(container, step_id)
        return container[index] if index >= 0 else None
    if isinstance(step, str) and isinstance(container, dict):
        return container.get(step)
    return None


def _apply_one(draft: dict[str, Any], op: dict[str, Any]) -> bool:
    """Applica un'operazione sul posto. ``False`` se il percorso non esiste piu'."""
    path: list[PathStep] = op["path"]
    parent: Any = draft
    for step in path[:-1]:
        parent = _child(parent, step)
        if not isinstance(parent, dict | list):
            return False
    last = path[-1]
    kind = op["op"]

    if kind == "order":
        target = _child(parent, last)
        if not isinstance(target, list):
            return False
        wanted = list(dict.fromkeys(i for i in op.get("ids") or [] if isinstance(i, str)))
        listed = [target[found] for i in wanted if (found := _find_by_id(target, i)) >= 0]
        rest = [item for item in target if not (isinstance(item, dict) and item.get("id") in wanted)]
        target[:] = listed + rest
        return True

    if (last_id := _step_id(last)) is not None:
        if not isinstance(parent, list):
            return False
        index = _find_by_id(parent, last_id)
        if kind == "remove":
            if index >= 0:
                parent.pop(index)
            return True
        value = copy.deepcopy(op.get("value"))
        if not (isinstance(value, dict) and value.get("id") == last_id):
            return False
        if index >= 0:
            parent[index] = value
        else:
            parent.append(value)
        return True

    if not isinstance(parent, dict) or not isinstance(last, str):
        return False
    if kind == "remove":
        parent.pop(last, None)
        return True
    parent[last] = copy.deepcopy(op.get("value"))
    return True


def apply_scenario_patch(baseline: dict[str, Any], ops: list[dict[str, Any]]) -> tuple[dict[str, Any], list[int]]:
    """La bozza dello scenario e gli indici delle operazioni che non si applicano piu'."""
    draft = copy.deepcopy(baseline)
    conflicts = [index for index, op in enumerate(ops) if not _apply_one(draft, op)]
    return draft, conflicts
