"""Dal piano fuso per fonte a un piano solo: stessi passaggi uniti, ordine dedotto.

Il piano nasce da un'estrazione per fonte: ogni intervista viene letta intera e
da sola, poi i piani parziali si fondono. Sul processo reale di acquisto
materiali indiretti (piano V2, tre interviste) il percorso principale usciva
cosi':

    1. Fattura ricevuta da Amministrazione      <- il processo "inizia" dalla fattura
    9. Esigenza operativa e richiesta del reparto
   15. Inviare la richiesta ad Acquisti
   30. Inviare richiesta ad Acquisti            <- stesso passaggio, altra voce
   34. Selezionare il fornitore                 <- doppione di "Definire il fornitore"

37 passaggi dove il processo ne ha una quindicina. Due cause distinte, e due
rimedi distinti:

**Ordine.** I percorsi parziali si accodavano nell'ordine di lettura delle fonti,
che e' alfabetico per nome: la prima intervista in elenco decideva dove comincia
il processo. Qui l'ordine si deduce dai legami che il piano gia' dichiara - archi,
esiti delle decisioni, l'ordine in cui ogni voce racconta il suo pezzo - con un
ordinamento topologico. E' aritmetica, e resta del runtime: nessun modello.

**Doppioni.** Lo stesso passaggio raccontato da due voci arriva con id ed
etichette diversi, e il merge deduplica per id. Riconoscere che "Emettere
l'ordine" e "Creare l'ordine nel gestionale" sono lo stesso passaggio e' un
giudizio, e va all'LLM in forma tipizzata - una chiamata sola, sul piano fuso.
Le prove restano del runtime: un gruppo senza parole in comune, con attori
incompatibili, o fatto di passaggi che una voce racconta in sequenza si scarta e
si conta; nessun id sparisce senza traccia; i riferimenti si riscrivono
sull'elemento sopravvissuto e si rileggono; l'elemento unificato porta le
citazioni di tutte le voci. Se la riscrittura non si verifica, il piano resta
quello di prima: un doppione visibile si corregge, un passaggio perso no.
"""

from __future__ import annotations

import heapq
import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.agents.plan_provenance import content_stems
from backend.process_understanding import (
    ProcessUnderstanding,
    UnifiedElement,
    process_understanding_diagnostics,
)

logger = logging.getLogger(__name__)

ElementKind = Literal["actor", "step", "event", "decision"]
UnifierStatus = Literal["done", "skipped", "failed"]
StartBasis = Literal["agent", "reach", "none"]

# In quale lista del piano vive ogni tipo di elemento. L'ordine conta: gli attori
# si unificano per primi, perche' la compatibilita' fra due passaggi si giudica
# sugli attori gia' unificati - "acquisti" e "ufficio_acquisti" sono lo stesso
# responsabile, e due passaggi che li citano non sono incompatibili.
_KIND_FIELD: dict[str, str] = {
    "actor": "actors",
    "event": "events",
    "step": "steps",
    "decision": "decisions",
}
_NODE_KINDS = ("event", "step", "decision")

# L'id del rilievo con cui il piano dichiara il limite dell'ordine. Stabile, cosi'
# una ricostruzione lo sostituisce invece di accumularne uno per volta.
ORDER_FINDING_ID = "ordine_percorso_da_confermare"
# Quanti passaggi il rilievo nomina: oltre, il consulente legge un elenco e non
# una lacuna.
ORDER_FINDING_LABELS = 6
# Quanto di ogni citazione arriva al modello: gli serve a riconoscere il
# passaggio, non a rileggere l'intervista.
EVIDENCE_PREVIEW_CHARS = 160


# --- il contratto dell'agente --------------------------------------------


class SameElementGroup(BaseModel):
    """Elementi del piano che sono lo stesso elemento del processo."""

    kind: ElementKind = Field(description="Il tipo comune a tutti gli elementi del gruppo.")
    element_ids: list[str] = Field(
        description="Gli id degli elementi che sono la stessa cosa: almeno due, tutti dello stesso tipo."
    )
    reason: str = Field(description="Perche' sono lo stesso elemento, in una frase, in italiano.")


class PlanUnificationVerdict(BaseModel):
    """I doppioni trovati nel piano fuso, e dove comincia il processo."""

    groups: list[SameElementGroup] = Field(default_factory=list)
    process_start_id: str | None = Field(
        default=None,
        description=(
            "Fra i candidati_inizio, l'id dell'elemento da cui parte l'intero processo. "
            "null se le fonti non lo dicono."
        ),
    )


@dataclass(frozen=True)
class UnificationRequest:
    """Il piano fuso come lo legge l'agente: elementi, voci e percorsi per voce."""

    process_name: str
    elements: list[dict[str, Any]]
    start_candidates: list[dict[str, Any]]
    source_paths: dict[str, list[str]] = field(default_factory=dict)


PlanUnifier = Callable[[UnificationRequest], PlanUnificationVerdict]


UNIFIER_PROMPT = """
Sei il consolidatore del piano di processo di DeliR. Il piano e' stato estratto
intervista per intervista e poi fuso: ogni voce ha dato i suoi id e le sue
etichette, quindi lo stesso passaggio raccontato da due voci compare due volte.

1. groups: raggruppa gli elementi che sono LO STESSO elemento del processo
   raccontato da voci diverse - la stessa attivita' svolta dallo stesso ruolo
   nello stesso punto del processo, lo stesso attore chiamato in due modi, la
   stessa decisione, lo stesso evento. Solo elementi dello stesso tipo.
   NON raggruppare:
   - passaggi consecutivi (chi invia e chi riceve sono due passaggi);
   - passaggi simili svolti da ruoli diversi;
   - un passaggio e la sua variante d'urgenza o d'eccezione;
   - passaggi che la stessa voce racconta come distinti.
   Due voci raccontano spesso lo stesso passaggio con parole e dettaglio diversi:
   chi lo fa lo descrive nel dettaglio, chi lo vede passare lo nomina appena, e il
   ruolo puo' essere detto in modo generico ("il reparto") o specifico ("la
   manutenzione"). Se e' lo stesso momento del processo, e' lo stesso passaggio.
   Quando due voci non concordano davvero su chi lo fa o su quando avviene, non
   raggruppare: il disaccordo va mostrato, non nascosto.
2. process_start_id: fra i candidati_inizio, l'elemento da cui parte l'intero
   processo - il fabbisogno o l'evento che lo innesca - e non il punto in cui una
   singola voce entra in scena. null se le fonti non lo dicono.

Ogni gruppo viene verificato: etichette senza parole in comune, attori
incompatibili, elementi collegati fra loro o raccontati dalla stessa voce vengono
scartati. Liste vuote sono una risposta corretta.
""".strip()


def llm_plan_unifier() -> PlanUnifier | None:
    """Il consolidatore basato sul modello, se il modello e' configurato.

    Returns:
        Il consolidatore, o ``None`` quando manca la chiave: chi chiama deve
        poter dire "unificazione non eseguita" invece di scambiarla per
        "nessun doppione".
    """
    from backend.settings import settings

    if not settings.openai_api_key:
        return None

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    from backend.llm_config import chat_openai_kwargs
    from backend.llm_streaming import stream_to_final

    runnable = ChatOpenAI(**chat_openai_kwargs()).with_structured_output(PlanUnificationVerdict)

    def _unify(request: UnificationRequest) -> PlanUnificationVerdict:
        raw = stream_to_final(
            runnable,
            [
                SystemMessage(content=UNIFIER_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        {
                            "processo": request.process_name,
                            "elementi": request.elements,
                            "candidati_inizio": request.start_candidates,
                            "percorso_raccontato_da_ogni_voce": request.source_paths,
                        },
                        ensure_ascii=False,
                    )
                ),
            ],
        )
        return (
            raw
            if isinstance(raw, PlanUnificationVerdict)
            else PlanUnificationVerdict.model_validate(raw)
        )

    return _unify


# --- esito ---------------------------------------------------------------


@dataclass(frozen=True)
class DiscardedGroup:
    """Un gruppo proposto che il runtime non ha potuto accettare, e perche'."""

    kind: str
    element_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class PlanConsolidation:
    """Il piano consolidato e cio' che e' successo per arrivarci."""

    process: ProcessUnderstanding
    unified: list[UnifiedElement] = field(default_factory=list)
    discarded: list[DiscardedGroup] = field(default_factory=list)
    unifier_status: UnifierStatus = "skipped"
    unifier_note: str = ""
    llm_calls: int = 0
    start_id: str | None = None
    start_basis: StartBasis = "none"
    # I passaggi del percorso che nessun legame collega all'inizio: stanno in
    # coda, e il piano lo dichiara.
    unordered: list[str] = field(default_factory=list)

    def as_log_entry(self) -> dict[str, Any]:
        return {
            "unifier_status": self.unifier_status,
            "unifier_note": self.unifier_note,
            "unified": [item.model_dump(mode="json") for item in self.unified],
            "discarded_groups": len(self.discarded),
            "discarded": [
                {"kind": item.kind, "element_ids": list(item.element_ids), "reason": item.reason}
                for item in self.discarded
            ],
            "start_id": self.start_id,
            "start_basis": self.start_basis,
            "unordered": list(self.unordered),
            "llm_calls": self.llm_calls,
        }


# --- riferimenti -----------------------------------------------------------


def _dedupe(items: Iterable[Any]) -> list[Any]:
    seen: list[Any] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _remap(value: Any, alias: dict[str, str]) -> Any:
    return alias.get(value, value) if isinstance(value, str) else value


def _remap_list(values: Any, alias: dict[str, str]) -> list:
    return _dedupe(_remap(item, alias) for item in values or [])


def rewrite_references(
    data: dict[str, Any],
    node_alias: dict[str, str],
    actor_alias: dict[str, str],
) -> dict[str, Any]:
    """Riscrive sull'elemento sopravvissuto ogni riferimento a un id assorbito.

    L'elenco dei campi e' esplicito perche' ogni campo ha il suo spazio di nomi:
    un id di attore e un id di passaggio possono coincidere, e una sostituzione
    cieca su tutto il piano ne riscriverebbe uno con l'alias dell'altro. Cio' che
    l'elenco dimentica lo trova la verifica che segue (`_leftover_references`).
    """
    out = json.loads(json.dumps(data))
    n, a = node_alias, actor_alias

    for key in ("sequence", "main_success_path"):
        out[key] = _remap_list(out.get(key), n)

    edges: list[dict] = []
    seen_edges: dict[tuple, dict] = {}
    for edge in out.get("flow_edges") or []:
        original = (edge.get("source_id"), edge.get("target_id"))
        edge["source_id"] = _remap(edge.get("source_id"), n)
        edge["target_id"] = _remap(edge.get("target_id"), n)
        # Un arco fra due voci dello stesso passaggio diventa un anello su se'
        # stesso: non e' un flusso del processo, e' la traccia del doppione.
        if edge["source_id"] == edge["target_id"] and original[0] != original[1]:
            continue
        signature = (edge["source_id"], edge["target_id"], (edge.get("condition") or "").strip().casefold())
        if signature in seen_edges:
            kept = seen_edges[signature]
            kept["source_evidence"] = _dedupe([*(kept.get("source_evidence") or []), *(edge.get("source_evidence") or [])])
            continue
        seen_edges[signature] = edge
        edges.append(edge)
    out["flow_edges"] = edges

    for step in out.get("steps") or []:
        step["actor_ids"] = _remap_list(step.get("actor_ids"), a)
    for decision in out.get("decisions") or []:
        for outcome in decision.get("outcome_details") or []:
            outcome["target_ref"] = _remap(outcome.get("target_ref"), n)
            outcome["rejoins_at"] = _remap(outcome.get("rejoins_at"), n)
    for exception in out.get("exceptions") or []:
        exception["attached_to_step_id"] = _remap(exception.get("attached_to_step_id"), n)
    for key in ("alternative_paths", "out_of_scope_alternatives"):
        for path in out.get(key) or []:
            path["sequence"] = _remap_list(path.get("sequence"), n)
            path["rejoins_at"] = _remap(path.get("rejoins_at"), n)
            path["ends_at"] = _remap(path.get("ends_at"), n)
    for loop in out.get("loops") or []:
        loop["repeated_steps"] = _remap_list(loop.get("repeated_steps"), n)
    for control in out.get("controls") or []:
        control["pass_target_ref"] = _remap(control.get("pass_target_ref"), n)
        control["fail_target_ref"] = _remap(control.get("fail_target_ref"), n)
        control["subject_ids"] = _remap_list(control.get("subject_ids"), n)
        control["control_owner_actor_id"] = _remap(control.get("control_owner_actor_id"), a)
    for rule in out.get("structured_business_rules") or []:
        rule["applies_to_ids"] = _remap_list(rule.get("applies_to_ids"), n)
    for item in out.get("input_outputs") or []:
        item["step"] = _remap(item.get("step"), n)
    for handoff in out.get("handoffs") or []:
        handoff["from_actor_id"] = _remap(handoff.get("from_actor_id"), a)
        handoff["to_actor_id"] = _remap(handoff.get("to_actor_id"), a)
    for participant in out.get("participants") or []:
        participant["actor_id"] = _remap(participant.get("actor_id"), a)
    for item in out.get("document_requirements") or []:
        for key in ("provided_by_actor_id", "received_by_actor_id", "validation_owner_actor_id"):
            item[key] = _remap(item.get(key), a)
    for hint in out.get("bpmn_modeling_hints") or []:
        hint["element"] = _remap(_remap(hint.get("element"), n), a)
    boundaries = out.get("boundaries")
    if isinstance(boundaries, dict):
        for key in ("start_event", "success_end"):
            boundaries[key] = _remap(boundaries.get(key), n)
        for key in ("failure_ends", "terminating_ends"):
            boundaries[key] = _remap_list(boundaries.get(key), n)
    relationships: dict[str, dict] = {}
    for item in out.get("actor_relationships") or []:
        item["actor_id"] = _remap(item.get("actor_id"), a)
        item["organization_id"] = _remap(item.get("organization_id"), a)
        relationships.setdefault(item["actor_id"], item)
    if out.get("actor_relationships"):
        out["actor_relationships"] = list(relationships.values())
    topology = out.get("bpmn_topology")
    if isinstance(topology, dict):
        for pool in topology.get("pools") or []:
            pool["actor_ids"] = _remap_list(pool.get("actor_ids"), a)
        for lane in topology.get("lanes") or []:
            lane["actor_ids"] = _remap_list(lane.get("actor_ids"), a)
        for flow in topology.get("message_flows") or []:
            flow["from_actor_id"] = _remap(flow.get("from_actor_id"), a)
            flow["to_actor_id"] = _remap(flow.get("to_actor_id"), a)
            flow["source_ref"] = _remap(flow.get("source_ref"), n)
            flow["target_ref"] = _remap(flow.get("target_ref"), n)
    return out


def _leftover_references(data: dict[str, Any], absorbed: set[str]) -> list[str]:
    """Dove il piano nomina ancora un id che non esiste piu'.

    Scansione cieca di tutto il piano, al contrario della riscrittura: e' la
    rilettura dopo la scrittura. Un campo nuovo nello schema che la riscrittura
    non conosce lascerebbe un riferimento rotto, e qui lo si vede prima che il
    piano venga salvato.
    """
    found: list[str] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "unified_elements" or key == "id":
                    continue
                walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, str) and value in absorbed:
            found.append(f"{path}={value}")

    walk(data, "piano")
    for kind_field in _KIND_FIELD.values():
        for entry in data.get(kind_field) or []:
            if entry.get("id") in absorbed:
                found.append(f"{kind_field}.id={entry['id']}")
    return found


# --- unificazione ----------------------------------------------------------


def _fuse(survivor: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    """L'elemento sopravvissuto con cio' che l'altra voce aggiunge.

    Id ed etichetta restano del sopravvissuto; le liste si uniscono, cosi' le
    citazioni di tutte le voci restano attaccate al passaggio - e' cio' che fa
    risultare piu' sostenuto un passaggio confermato da due interviste.
    """
    fused = dict(survivor)
    for key, value in other.items():
        if key in {"id", "label"}:
            continue
        current = fused.get(key)
        if isinstance(value, list) and isinstance(current, list):
            if key == "outcome_details":
                labels = {str(item.get("label") or "").strip().casefold() for item in current}
                fused[key] = [
                    *current,
                    *(
                        item
                        for item in value
                        if str(item.get("label") or "").strip().casefold() not in labels
                    ),
                ]
            else:
                fused[key] = _dedupe([*current, *value])
        elif current in (None, "", []) and value not in (None, "", []):
            fused[key] = value
    return fused


def _labels_share_words(labels: list[str]) -> bool:
    """Ogni coppia di etichette ha almeno una parola di contenuto in comune."""
    stems = [content_stems(label) for label in labels]
    return all(
        stems[i] & stems[j]
        for i in range(len(stems))
        for j in range(i + 1, len(stems))
    )


def _linked_pairs(data: dict[str, Any], source_paths: dict[str, list[str]]) -> set[frozenset]:
    """Le coppie di elementi che il piano o una voce mettono uno dopo l'altro."""
    pairs: set[frozenset] = set()
    for edge in data.get("flow_edges") or []:
        pairs.add(frozenset((edge.get("source_id"), edge.get("target_id"))))
    for path in source_paths.values():
        for before, after in zip(path, path[1:]):
            pairs.add(frozenset((before, after)))
    return pairs


def _validate_group(
    group: SameElementGroup,
    *,
    data: dict[str, Any],
    claimed: set[str],
    actor_alias: dict[str, str],
    linked: set[frozenset],
    origins: dict[str, list[str]],
) -> tuple[list[str] | None, str]:
    """Il gruppo regge? Ritorna i membri in ordine di piano, o il motivo del rifiuto."""
    kind_field = _KIND_FIELD[group.kind]
    entries = data.get(kind_field) or []
    position = {entry.get("id"): index for index, entry in enumerate(entries)}
    ids = _dedupe(item for item in group.element_ids if item)
    if len(ids) < 2:
        return None, "meno di due elementi"
    missing = [item for item in ids if item not in position]
    if missing:
        return None, f"elementi non presenti fra i {kind_field}: {', '.join(missing)}"
    taken = [item for item in ids if item in claimed]
    if taken:
        return None, f"elementi gia' unificati in un altro gruppo: {', '.join(taken)}"
    # Il sopravvissuto e' il primo per id, non il primo letto: una regola che
    # dipendesse dall'ordine delle fonti darebbe un piano diverso a ogni fonte
    # rinominata.
    members = sorted(ids)
    by_id = {entry.get("id"): entry for entry in entries}

    if not _labels_share_words([str(by_id[item].get("label") or "") for item in members]):
        return None, "etichette senza parole in comune"

    for left in range(len(members)):
        for right in range(left + 1, len(members)):
            if frozenset((members[left], members[right])) in linked:
                return None, (
                    f"{members[left]} e {members[right]} sono collegati uno dopo l'altro: "
                    "una sequenza, non un doppione"
                )

    if group.kind == "actor":
        # La natura di un attore la sceglie ogni estrazione per conto suo: la
        # stessa "Acquisti" e' un ruolo per una voce e un ufficio per l'altra.
        # Un sistema invece non e' mai la persona che lo usa.
        kinds = {by_id[item].get("kind") for item in members}
        if "system" in kinds and len(kinds) > 1:
            return None, "un sistema e un attore umano: " + ", ".join(sorted(str(k) for k in kinds))
    if group.kind == "step":
        actor_sets = [
            {actor_alias.get(actor, actor) for actor in by_id[item].get("actor_ids") or []}
            for item in members
        ]
        declared = [actors for actors in actor_sets if actors]
        if any(
            not (declared[i] & declared[j])
            for i in range(len(declared))
            for j in range(i + 1, len(declared))
        ):
            return None, "attori incompatibili"

    voices = [origins.get(f"{group.kind}:{item}") for item in members]
    if all(voices) and len({voice for sources in voices for voice in sources}) < 2:
        return None, "tutti gli elementi vengono dalla stessa voce"
    return members, ""


def _elements_for_request(
    data: dict[str, Any], origins: dict[str, list[str]]
) -> list[dict[str, Any]]:
    actor_labels = {entry.get("id"): entry.get("label") for entry in data.get("actors") or []}
    elements: list[dict[str, Any]] = []
    for kind, kind_field in _KIND_FIELD.items():
        for entry in data.get(kind_field) or []:
            item: dict[str, Any] = {
                "tipo": kind,
                "id": entry.get("id"),
                "etichetta": entry.get("label"),
                "voci": origins.get(f"{kind}:{entry.get('id')}", []),
            }
            if kind == "actor":
                item["natura"] = entry.get("kind")
            if entry.get("description"):
                item["descrizione"] = entry["description"]
            if entry.get("question"):
                item["domanda"] = entry["question"]
            if entry.get("type"):
                item["natura"] = entry["type"]
            if entry.get("actor_ids"):
                item["attori"] = [actor_labels.get(actor, actor) for actor in entry["actor_ids"]]
            evidence = [str(text)[:EVIDENCE_PREVIEW_CHARS] for text in (entry.get("source_evidence") or [])[:2]]
            if evidence:
                item["citazioni"] = evidence
            elements.append(item)
    return elements


def _apply_groups(
    data: dict[str, Any],
    accepted: list[tuple[str, list[str], str]],
) -> tuple[dict[str, Any], dict[str, str], dict[str, str], list[UnifiedElement]]:
    node_alias: dict[str, str] = {}
    actor_alias: dict[str, str] = {}
    unified: list[UnifiedElement] = []
    out = json.loads(json.dumps(data))
    for kind, members, reason in accepted:
        kind_field = _KIND_FIELD[kind]
        by_id = {entry.get("id"): entry for entry in out.get(kind_field) or []}
        survivor_id, absorbed = members[0], members[1:]
        fused = by_id[survivor_id]
        for other in absorbed:
            fused = _fuse(fused, by_id[other])
        out[kind_field] = [
            fused if entry.get("id") == survivor_id else entry
            for entry in out.get(kind_field) or []
            if entry.get("id") not in absorbed
        ]
        alias = actor_alias if kind == "actor" else node_alias
        for other in absorbed:
            alias[other] = survivor_id
        unified.append(
            UnifiedElement(
                id=survivor_id,
                kind=kind,
                absorbed_ids=list(absorbed),
                absorbed_labels=[str(by_id[other].get("label") or "") for other in absorbed],
                reason=reason,
            )
        )
    return out, node_alias, actor_alias, unified


def _unify(
    data: dict[str, Any],
    verdict: PlanUnificationVerdict,
    *,
    origins: dict[str, list[str]],
    source_paths: dict[str, list[str]],
) -> tuple[dict[str, Any], dict[str, str], list[UnifiedElement], list[DiscardedGroup]]:
    """Applica i gruppi che reggono, e non dichiara riuscita una riscrittura che non si rilegge."""
    linked = _linked_pairs(data, source_paths)
    claimed: set[str] = set()
    actor_alias: dict[str, str] = {}
    accepted: list[tuple[str, list[str], str]] = []
    discarded: list[DiscardedGroup] = []

    ordered_groups = sorted(
        enumerate(verdict.groups), key=lambda pair: (list(_KIND_FIELD).index(pair[1].kind), pair[0])
    )
    for _index, group in ordered_groups:
        members, why = _validate_group(
            group,
            data=data,
            claimed=claimed,
            actor_alias=actor_alias,
            linked=linked,
            origins=origins,
        )
        if members is None:
            discarded.append(DiscardedGroup(group.kind, tuple(group.element_ids), why))
            continue
        claimed.update(members)
        accepted.append((group.kind, members, group.reason))
        if group.kind == "actor":
            for other in members[1:]:
                actor_alias[other] = members[0]

    if not accepted:
        return data, {}, [], discarded

    applied, node_alias, actor_alias, unified = _apply_groups(data, accepted)
    rewritten = rewrite_references(applied, node_alias, actor_alias)
    rewritten["unified_elements"] = [
        *(data.get("unified_elements") or []),
        *(item.model_dump(mode="json") for item in unified),
    ]

    # Rilettura: nessun id assorbito resta citato, e la riscrittura non ha
    # introdotto riferimenti rotti che prima non c'erano.
    leftovers = _leftover_references(rewritten, set(node_alias) | set(actor_alias))
    before = process_understanding_diagnostics(ProcessUnderstanding.model_validate(data)).blocking
    after = process_understanding_diagnostics(ProcessUnderstanding.model_validate(rewritten)).blocking
    if leftovers or len(after) > len(before):
        why = (
            "riferimenti ancora rivolti a id assorbiti: " + ", ".join(leftovers[:4])
            if leftovers
            else "la riscrittura introduce riferimenti rotti: " + "; ".join(after[:3])
        )
        logger.warning("unificazione del piano annullata: %s", why)
        discarded.extend(
            DiscardedGroup(kind, tuple(members), f"riscrittura non verificata: {why}")
            for kind, members, _reason in accepted
        )
        return data, {}, [], discarded
    return rewritten, node_alias, unified, discarded


# --- ordine ------------------------------------------------------------------


@dataclass
class _Graph:
    nodes: list[str]
    successors: dict[str, list[str]]
    predecessors: dict[str, set[str]]
    rank: dict[str, int]


def _build_graph(data: dict[str, Any], members: list[str], source_paths: dict[str, list[str]]) -> _Graph:
    """I legami che il piano dichiara, come grafo.

    Gli archi del piano, gli esiti delle decisioni e l'ordine in cui ogni voce
    racconta il suo pezzo. I flussi di dati no: dicono cosa passa, non cosa viene
    prima.
    """
    known: list[str] = list(members)
    for kind in _NODE_KINDS:
        for entry in data.get(_KIND_FIELD[kind]) or []:
            if entry.get("id"):
                known.append(entry["id"])
    for entry in data.get("exceptions") or []:
        if entry.get("id"):
            known.append(entry["id"])
    nodes = _dedupe(known)
    node_set = set(nodes)
    # Il rango e' l'ordine in cui il piano fuso elenca le cose. Decide solo fra
    # elementi che nessun legame ordina, cosi' due ricostruzioni sulle stesse
    # fonti danno lo stesso percorso.
    rank = {node: index for index, node in enumerate(nodes)}

    successors: dict[str, list[str]] = {node: [] for node in nodes}
    predecessors: dict[str, set[str]] = {node: set() for node in nodes}

    def link(source: Any, target: Any) -> None:
        if source in node_set and target in node_set and source != target and target not in successors[source]:
            successors[source].append(target)
            predecessors[target].add(source)

    for edge in data.get("flow_edges") or []:
        if edge.get("kind") != "data":
            link(edge.get("source_id"), edge.get("target_id"))
    for decision in data.get("decisions") or []:
        for outcome in decision.get("outcome_details") or []:
            link(decision.get("id"), outcome.get("target_ref"))
    # Un'eccezione accade durante il passaggio a cui e' attaccata: senza questo
    # legame sarebbe una radice isolata, e cio' verso cui rientra aspetterebbe
    # in coda un elemento che nessun inizio raggiunge.
    for exception in data.get("exceptions") or []:
        link(exception.get("attached_to_step_id"), exception.get("id"))
    sequences = [
        *source_paths.values(),
        *((path.get("sequence") or []) for path in data.get("alternative_paths") or []),
    ]
    for path in sequences:
        for before, after in zip(path, path[1:]):
            link(before, after)
    for node in nodes:
        successors[node].sort(key=lambda item: (rank[item], item))
    return _Graph(nodes=nodes, successors=successors, predecessors=predecessors, rank=rank)


def _reach(graph: _Graph, root: str) -> set[str]:
    seen = {root}
    frontier = [root]
    while frontier:
        node = frontier.pop()
        for nxt in graph.successors[node]:
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return seen


def _roots(graph: _Graph) -> list[str]:
    return [node for node in graph.nodes if not graph.predecessors[node]]


def _start_candidates(data: dict[str, Any], graph: _Graph) -> list[str]:
    starts = [
        entry["id"]
        for entry in data.get("events") or []
        if entry.get("type") == "start" and entry.get("id")
    ]
    return _dedupe([*starts, *(root for root in _roots(graph) if graph.successors[root])])


def _topological_order(graph: _Graph, anchor: str | None) -> list[str]:
    """Ordinamento topologico con un tie-break stabile, cicli compresi.

    Una visita in profondita' dall'inizio del processo, poi dalle altre radici,
    riconosce gli archi che tornano indietro - una rilavorazione, un "rimanda
    indietro la richiesta" - e li mette da parte: sono legami veri, ma non
    dicono cosa viene prima. Sul grafo che resta, l'ordine di scoperta della
    visita decide fra gli elementi pronti insieme: cio' che si raggiunge
    dall'inizio viene prima di cio' che non vi e' collegato.
    """
    roots = [anchor] if anchor else []
    roots += sorted(_roots(graph), key=lambda node: (graph.rank[node], node))
    roots += sorted(graph.nodes, key=lambda node: (graph.rank[node], node))

    discovery: dict[str, int] = {}
    back_edges: set[tuple[str, str]] = set()
    for root in roots:
        if root in discovery:
            continue
        discovery[root] = len(discovery)
        on_stack = {root}
        stack: list[tuple[str, int]] = [(root, 0)]
        while stack:
            node, index = stack[-1]
            nexts = graph.successors[node]
            if index >= len(nexts):
                stack.pop()
                on_stack.discard(node)
                continue
            stack[-1] = (node, index + 1)
            nxt = nexts[index]
            if nxt in on_stack:
                back_edges.add((node, nxt))
            elif nxt not in discovery:
                discovery[nxt] = len(discovery)
                on_stack.add(nxt)
                stack.append((nxt, 0))

    # Un pezzo che l'inizio non raggiunge ha una posizione che nessuno conosce, e
    # va in coda dichiarato. I suoi archi verso cio' che l'inizio raggiunge - una
    # voce che rimanda indietro la richiesta, per esempio - non possono tenere in
    # ostaggio la parte nota del percorso: la farebbero finire in coda con lui.
    reached = _reach(graph, anchor) if anchor else set()

    def orders(pred: str, node: str) -> bool:
        if (pred, node) in back_edges:
            return False
        return not (node in reached and pred not in reached)

    pending = {
        node: sum(1 for pred in graph.predecessors[node] if orders(pred, node))
        for node in graph.nodes
    }
    ready = [(discovery[node], node) for node, count in pending.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        _, node = heapq.heappop(ready)
        order.append(node)
        for nxt in graph.successors[node]:
            if not orders(node, nxt):
                continue
            pending[nxt] -= 1
            if pending[nxt] == 0:
                heapq.heappush(ready, (discovery[nxt], nxt))
    return order


def _labels_by_id(data: dict[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for kind_field in ("steps", "events", "decisions", "exceptions"):
        for entry in data.get(kind_field) or []:
            if entry.get("id"):
                labels[entry["id"]] = str(entry.get("label") or entry["id"])
    return labels


def _order_finding(labels: list[str], total: int) -> dict[str, Any]:
    named = ", ".join(f'"{label}"' for label in labels[:ORDER_FINDING_LABELS])
    more = f" e altri {total - ORDER_FINDING_LABELS}" if total > ORDER_FINDING_LABELS else ""
    return {
        "id": ORDER_FINDING_ID,
        "finding": (
            f"Le fonti non collegano all'inizio del processo {total} passaggi del percorso "
            f"principale ({named}{more}): la loro posizione non si deduce da cio' che le "
            "voci raccontano, e sono in coda al percorso."
        ),
        "category": "scope",
        "severity": "warning",
        "recommendation": "Conferma dove si collocano nel processo, o quale passaggio li precede.",
    }


def derive_path_order(
    data: dict[str, Any],
    *,
    source_paths: dict[str, list[str]] | None = None,
    start_id: str | None = None,
    start_basis: StartBasis = "none",
) -> tuple[dict[str, Any], str | None, StartBasis, list[str]]:
    """Il percorso principale nell'ordine che i legami del piano dicono.

    Args:
        data: Il piano, come dizionario.
        source_paths: Il percorso che ogni voce racconta, per nome di fonte.
        start_id: L'inizio del processo gia' giudicato, quando c'e'.
        start_basis: Da dove viene `start_id`.

    Returns:
        Il piano riordinato, l'inizio usato, su quale base, e i passaggi che
        nessun legame collega all'inizio.
    """
    paths = source_paths or {}
    out = json.loads(json.dumps(data))
    members = _dedupe([*(out.get("main_success_path") or []), *(out.get("sequence") or [])])
    if not members:
        return out, start_id, start_basis, []
    graph = _build_graph(out, members, paths)

    anchor = start_id if start_id in graph.predecessors else None
    basis: StartBasis = start_basis if anchor else "none"
    if anchor is None:
        # Senza un giudizio sull'inizio, conta cio' che il grafo dimostra:
        # l'inizio del processo e' l'elemento che precede la parte piu' grande
        # del percorso. A parita' vince l'inizio che il piano dichiara nei suoi
        # confini, poi il rango.
        member_set = set(members)
        declared = _declared_start(out)
        # Un evento d'inizio e' una dichiarazione delle fonti; una radice qualunque
        # e' solo un elemento senza predecessori, e un pezzo che rimanda indietro
        # una richiesta "raggiunge" molto proprio grazie al suo arco di ritorno.
        # Le radici contano solo quando nessuna voce dichiara un inizio.
        starts = [
            entry["id"]
            for entry in out.get("events") or []
            if entry.get("type") == "start" and graph.successors.get(entry.get("id"))
        ]
        candidates = starts or _start_candidates(out, graph)
        if candidates:
            anchor = min(
                candidates,
                key=lambda node: (
                    -len(_reach(graph, node) & member_set),
                    node not in declared,
                    graph.rank[node],
                ),
            )
            basis = "reach"

    order = _topological_order(graph, anchor)
    position = {node: index for index, node in enumerate(order)}
    for key in ("main_success_path", "sequence"):
        if out.get(key):
            out[key] = sorted(_dedupe(out[key]), key=lambda node: (position.get(node, len(order)), node))

    reached = _reach(graph, anchor) if anchor else set()
    unordered = [node for node in out.get("main_success_path") or out.get("sequence") or [] if node not in reached]

    findings = [item for item in out.get("consultant_findings") or [] if item.get("id") != ORDER_FINDING_ID]
    if unordered:
        labels = _labels_by_id(out)
        findings.append(_order_finding([labels.get(node, node) for node in unordered], len(unordered)))
    out["consultant_findings"] = findings
    return out, anchor, basis, unordered


def _declared_start(data: dict[str, Any]) -> set[str]:
    """Gli elementi che i confini del piano nominano come inizio, per id o etichetta."""
    boundaries = data.get("boundaries") or {}
    names = {
        " ".join(str(value).split()).casefold()
        for value in (boundaries.get("start_event"), boundaries.get("trigger"))
        if value
    }
    if not names:
        return set()
    declared: set[str] = set()
    for kind_field in ("events", "steps"):
        for entry in data.get(kind_field) or []:
            keys = {
                " ".join(str(entry.get("id") or "").split()).casefold(),
                " ".join(str(entry.get("label") or "").split()).casefold(),
            }
            if keys & names:
                declared.add(entry.get("id"))
    return declared


def _folded(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _boundaries_for_order(
    data: dict[str, Any],
    start_id: str | None,
    source_paths: dict[str, list[str]],
    partial_boundaries: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """L'inizio e la fine dichiarati dalle voci che li raccontano.

    Il merge per fonte tiene i confini dell'ultima voce letta, e l'ultima voce
    letta e' un fatto alfabetico: l'evento iniziale del disegno prendeva il nome
    da chi entra in scena per ultimo. Qui l'inizio viene dalla voce il cui
    racconto parte dall'inizio scelto, e la fine dalla voce il cui racconto
    finisce dove finisce il percorso. Il resto dei confini non cambia.
    """
    if not partial_boundaries:
        return None
    merged = dict(data.get("boundaries") or {})
    labels = _labels_by_id(data)
    changed = False

    if start_id:
        keys = {_folded(start_id), _folded(labels.get(start_id))}
        voice = next(
            (
                name
                for name, boundaries in partial_boundaries.items()
                if _folded(boundaries.get("start_event")) in keys
            ),
            None,
        ) or next(
            (name for name, path in source_paths.items() if path and path[0] == start_id),
            None,
        )
        declared = partial_boundaries.get(voice or "") or {}
        for key in ("start_event", "trigger"):
            if declared.get(key):
                merged[key] = declared[key]
                changed = True

    path = data.get("main_success_path") or data.get("sequence") or []
    if path:
        voice = next(
            (name for name, told in source_paths.items() if told and told[-1] == path[-1]),
            None,
        )
        end = (partial_boundaries.get(voice or "") or {}).get("success_end")
        terminating = {_folded(item) for item in merged.get("terminating_ends") or []}
        # Una fine di successo che un'altra voce dichiara come interruzione non
        # si sceglie qui: e' un disaccordo fra le fonti, non un nome da copiare.
        if end and _folded(end) not in terminating:
            merged["success_end"] = end
            changed = True
    return merged if changed else None


# --- ingresso ----------------------------------------------------------------


def consolidate_plan(
    plan: ProcessUnderstanding,
    *,
    process_name: str,
    origins: dict[str, list[str]] | None = None,
    source_paths: dict[str, list[str]] | None = None,
    partial_boundaries: dict[str, dict[str, Any]] | None = None,
    unifier: PlanUnifier | None = None,
    skip_note: str = "",
) -> PlanConsolidation:
    """Unifica i doppioni e deduce l'ordine del percorso principale.

    Args:
        plan: Il piano fuso dalle estrazioni per fonte.
        process_name: Il nome del processo, per l'agente.
        origins: Da quali fonti viene ogni elemento, per chiave ``tipo:id``.
        source_paths: Il percorso che ogni voce racconta, per nome di fonte.
        partial_boundaries: I confini dichiarati da ogni voce, per nome di fonte.
        unifier: Il giudizio sui doppioni. ``None`` salta l'unificazione, e il
            rapporto lo dice.
        skip_note: Perche' `unifier` manca, quando chi chiama lo sa: "modello
            non configurato" e "fonti non lette" sono due guasti diversi.

    Returns:
        Il piano consolidato, con cio' che e' stato unito, scartato e ordinato.

    Side effects:
        Chiama il modello una volta, quando `unifier` c'e'.
    """
    origins = origins or {}
    paths = {name: list(path) for name, path in (source_paths or {}).items()}
    data = plan.model_dump(mode="json")

    status: UnifierStatus = "skipped"
    note = skip_note or "unificazione dei doppioni non eseguita: modello non configurato"
    llm_calls = 0
    unified: list[UnifiedElement] = []
    discarded: list[DiscardedGroup] = []
    agent_start: str | None = None

    if unifier is not None:
        members = _dedupe([*(data.get("main_success_path") or []), *(data.get("sequence") or [])])
        graph = _build_graph(data, members, paths)
        candidates = _start_candidates(data, graph)
        labels = _labels_by_id(data)
        request = UnificationRequest(
            process_name=process_name,
            elements=_elements_for_request(data, origins),
            start_candidates=[{"id": node, "etichetta": labels.get(node, node)} for node in candidates],
            source_paths={name: [labels.get(node, node) for node in path] for name, path in paths.items()},
        )
        llm_calls = 1
        try:
            verdict = unifier(request)
        except Exception as exc:  # noqa: BLE001
            # Un consolidatore che non risponde non costa il piano: resta quello
            # fuso, con i doppioni visibili, e il rapporto lo dice.
            status, note = "failed", f"{type(exc).__name__}: {exc}"
            logger.warning("unificazione del piano non riuscita: %s", note)
        else:
            status, note = "done", ""
            data, node_alias, unified, discarded = _unify(
                data, verdict, origins=origins, source_paths=paths
            )
            paths = {name: _remap_list(path, node_alias) for name, path in paths.items()}
            chosen = verdict.process_start_id
            if chosen and chosen in candidates:
                agent_start = node_alias.get(chosen, chosen)
            elif chosen:
                discarded.append(
                    DiscardedGroup("start", (chosen,), "inizio proposto fuori dai candidati")
                )

    ordered, start_id, basis, unordered = derive_path_order(
        data,
        source_paths=paths,
        start_id=agent_start,
        start_basis="agent" if agent_start else "none",
    )
    boundaries = _boundaries_for_order(ordered, start_id, paths, partial_boundaries or {})
    if boundaries:
        ordered["boundaries"] = boundaries

    return PlanConsolidation(
        process=ProcessUnderstanding.model_validate(ordered),
        unified=unified,
        discarded=discarded,
        unifier_status=status,
        unifier_note=note,
        llm_calls=llm_calls,
        start_id=start_id,
        start_basis=basis,
        unordered=unordered,
    )
