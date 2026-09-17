"""Togliere dal piano un elemento che il consulente ha rifiutato, senza rompere il flusso.

Il rapporto di provenance dice quali elementi nessuna fonte regge; il consulente
li rivede e ne rifiuta alcuni. Rifiutare un passaggio non e' cancellare una riga
dall'elenco `steps`: il passaggio e' citato dal percorso principale, dai rami,
dai flussi, dagli esiti delle decisioni, dalle eccezioni che gli si attaccano,
dai controlli e dai loop. Toglierlo solo da `steps` lascia riferimenti a un nodo
che non esiste, e il compilatore - giustamente - li rifiuta o li disegna male.

Qui la rimozione e' una trasformazione del piano, deterministica e completa:

- il passaggio esce da ogni percorso ordinato, che resta nell'ordine di prima;
- i flussi che lo attraversavano si **ricuciono** (`a -> x -> b` diventa
  `a -> b`): togliere un passaggio inventato non deve spezzare il processo in
  due;
- un esito di decisione o un ramo che finiva su di lui prosegue verso il suo
  unico successore, se ce n'e' uno, altrimenti perde la destinazione e il
  compilatore lo dichiara;
- le eccezioni attaccate a lui escono con lui: sono eccezioni *di quel*
  passaggio.

Nessun LLM, nessuna scrittura: chi chiama decide cosa fare del piano che torna.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from backend.agents.plan_provenance import ElementKind
from backend.process_understanding import ProcessFlowEdge, ProcessUnderstanding

RemovableKind = Literal["step", "event", "exception"]

REMOVABLE_KINDS: frozenset[str] = frozenset({"step", "event", "exception"})


class ElementNotRemovable(ValueError):
    """L'elemento non esiste nel piano, o non e' di un tipo che si toglie cosi'."""


def _without(items: list[str], element_id: str) -> list[str]:
    return [item for item in items if item != element_id]


def _single_successor(plan: ProcessUnderstanding, element_id: str) -> str | None:
    """Il passaggio che viene dopo, se e' uno solo.

    Con due o piu' successori non c'e' un "dopo" da scegliere senza inventarlo:
    meglio lasciare la destinazione vuota e farlo dire al compilatore.
    """
    successors = {edge.target_id for edge in plan.flow_edges if edge.source_id == element_id}
    for path in (plan.main_success_path, plan.sequence):
        if element_id in path:
            index = path.index(element_id)
            if index + 1 < len(path):
                successors.add(path[index + 1])
            break
    successors.discard(element_id)
    return next(iter(successors)) if len(successors) == 1 else None


def _merged(before: str | None, after: str | None) -> str | None:
    if not before or not after or before == after:
        return before or after
    return None


def _stitched(before: ProcessFlowEdge, after: ProcessFlowEdge) -> ProcessFlowEdge:
    """L'arco che sostituisce `before -> x -> after`.

    Condizioni diverse si compongono: lungo un percorso valgono entrambe, e
    tenerne una sola farebbe passare dal nuovo arco casi che prima non passavano.
    Tipo e percorso invece non si compongono: un flusso di messaggio seguito da
    uno di sequenza, o due rami diversi, non sono un arco solo, e ricucirli
    inventerebbe una connessione.
    """
    if before.kind != after.kind:
        raise ElementNotRemovable(
            f"I flussi intorno all'elemento sono di tipo diverso ({before.kind}, {after.kind}): "
            "togliendolo non si possono ricucire in un flusso solo."
        )
    if before.path_id and after.path_id and before.path_id != after.path_id:
        raise ElementNotRemovable(
            "I flussi intorno all'elemento appartengono a percorsi diversi: "
            "togliendolo non si possono ricucire senza inventare un collegamento."
        )
    condition = _merged(before.condition, after.condition)
    if condition is None and before.condition and after.condition:
        condition = f"{before.condition}; {after.condition}"
    return ProcessFlowEdge(
        id=f"{before.id}__{after.id}",
        source_id=before.source_id,
        target_id=after.target_id,
        label=after.label or before.label,
        condition=condition,
        kind=before.kind,
        path_id=before.path_id or after.path_id,
        source_evidence=[*before.source_evidence, *after.source_evidence],
    )


def _rewire_flow_edges(plan: ProcessUnderstanding, element_id: str) -> list[ProcessFlowEdge]:
    incoming = [edge for edge in plan.flow_edges if edge.target_id == element_id]
    outgoing = [edge for edge in plan.flow_edges if edge.source_id == element_id]
    kept = [
        edge
        for edge in plan.flow_edges
        if edge.source_id != element_id and edge.target_id != element_id
    ]
    existing = {(edge.source_id, edge.target_id) for edge in kept}
    for before in incoming:
        for after in outgoing:
            pair = (before.source_id, after.target_id)
            if before.source_id == after.target_id or pair in existing:
                continue
            existing.add(pair)
            kept.append(_stitched(before, after))
    return kept


def remove_plan_element(
    understanding: ProcessUnderstanding | Mapping[str, object],
    *,
    kind: ElementKind,
    element_id: str,
) -> ProcessUnderstanding:
    """Il piano senza l'elemento rifiutato, con il flusso ricucito.

    Args:
        understanding: Il piano corrente.
        kind: Il tipo dell'elemento, come lo dichiara il rapporto di provenance.
        element_id: L'id dell'elemento nel piano.

    Returns:
        Una copia del piano senza l'elemento e senza riferimenti a lui.

    Raises:
        ElementNotRemovable: Se il tipo non si toglie con questa operazione -
            togliere un attore o una decisione cambia la struttura del processo
            e va rifatto sul piano, non con un click - o se l'elemento non c'e'.
    """
    if kind not in REMOVABLE_KINDS:
        raise ElementNotRemovable(
            f"Un elemento di tipo '{kind}' non si rimuove dalla revisione delle evidenze: "
            "cambia la struttura del processo e va corretto sul piano."
        )

    plan = (
        understanding.model_copy(deep=True)
        if isinstance(understanding, ProcessUnderstanding)
        else ProcessUnderstanding.model_validate(understanding)
    )

    if kind == "exception":
        if not any(item.id == element_id for item in plan.exceptions):
            raise ElementNotRemovable(f"Eccezione non trovata nel piano: {element_id}")
        plan.exceptions = [item for item in plan.exceptions if item.id != element_id]
        plan.flow_edges = _rewire_flow_edges(plan, element_id)
        return plan

    collection = plan.steps if kind == "step" else plan.events
    if not any(item.id == element_id for item in collection):
        raise ElementNotRemovable(f"Elemento non trovato nel piano: {element_id}")

    successor = _single_successor(plan, element_id)

    if kind == "step":
        plan.steps = [item for item in plan.steps if item.id != element_id]
    else:
        plan.events = [item for item in plan.events if item.id != element_id]

    plan.flow_edges = _rewire_flow_edges(plan, element_id)
    plan.sequence = _without(plan.sequence, element_id)
    plan.main_success_path = _without(plan.main_success_path, element_id)

    for paths in (plan.alternative_paths, plan.out_of_scope_alternatives):
        for path in paths:
            path.sequence = _without(path.sequence, element_id)
            if path.rejoins_at == element_id:
                path.rejoins_at = successor
            if path.ends_at == element_id:
                path.ends_at = successor

    for decision in plan.decisions:
        for outcome in decision.outcome_details:
            if outcome.target_ref == element_id:
                outcome.target_ref = successor
            if outcome.rejoins_at == element_id:
                outcome.rejoins_at = successor

    # Le eccezioni attaccate al passaggio sono eccezioni di quel passaggio.
    plan.exceptions = [item for item in plan.exceptions if item.attached_to_step_id != element_id]

    for control in plan.controls:
        control.subject_ids = _without(control.subject_ids, element_id)
        if control.pass_target_ref == element_id:
            control.pass_target_ref = successor
        if control.fail_target_ref == element_id:
            control.fail_target_ref = successor

    for loop in plan.loops:
        loop.repeated_steps = _without(loop.repeated_steps, element_id)
    plan.loops = [loop for loop in plan.loops if loop.repeated_steps]

    plan.input_outputs = [item for item in plan.input_outputs if item.step != element_id]
    plan.bpmn_modeling_hints = [
        item for item in plan.bpmn_modeling_hints if item.element != element_id
    ]
    plan.quality_report = None
    return plan
