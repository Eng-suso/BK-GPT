"""Il Modeling Plan come artefatto: si modifica, si versiona, si rilegge.

Il piano del processo esisteva gia' - vive dentro la review BPMN - ma esisteva
come *fotografia*, non come artefatto. Due conseguenze, e sono quelle che il
consulente vedeva:

1. **si poteva solo riscrivere.** L'unico write agentico era
   `prepare_bpmn_review`, che sostituisce l'intero `process_understanding`. Una
   richiesta incrementale - "mettilo nel piano" - non aveva un'operazione a cui
   mappare: l'unica cosa vicina era rifare tutto, e rifare tutto passa dal
   disegno. Da li' la richiesta di una modalita' di costruzione per un'operazione
   che il disegno non lo tocca nemmeno;
2. **ogni scrittura era distruttiva.** Aggiungere un percorso urgente a un piano
   che gia' conosceva tre lane significava rispedire anche le tre lane, e cio'
   che il modello non ripeteva spariva. Una lacuna reale e una dimenticanza del
   turno finivano indistinguibili.

Qui il piano diventa un artefatto con due operazioni distinte e una sola regola
di scrittura:

    amend    - il piano corrente piu' cio' che arriva. Non cancella.
    replace  - il piano viene rifatto da capo. Esplicito, mai implicito.

    write -> persistence -> read-after-write -> success

Il merge e' deterministico e non chiede niente all'LLM: le liste si uniscono per
identita' stabile, e dove due versioni della stessa voce si incontrano vince cio'
che la nuova dichiara *davvero* - un campo vuoto non e' una cancellazione, e'
silenzio.

Il piano non e' il disegno. Modificarlo non tocca il BPMN, e questo modulo non
sa nemmeno serializzarlo: applicare il piano al canvas e' un'altra operazione,
di un altro proprietario.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from backend.agents.process_snapshot import (
    PLAN_IGNORES_EVIDENCE_REMEDY,
    ProcessKnowledgeSnapshot,
    build_process_snapshot,
    plan_ignores_evidence,
)
from backend.process_understanding import (
    ProcessUnderstanding,
    unknown_question_id,
)
from backend.workspace_services.write_verification import (
    PersistenceVerificationError,
    verify_review_persisted,
)

logger = logging.getLogger(__name__)

PlanStrategy = Literal["amend", "replace"]
PlanAction = Literal[
    "amended",
    "replaced",
    "created",
    "unchanged",
    "process_not_found",
    "rejected_empty_plan",
    "write_failed",
]

# Quante passate di correzione il loop di review del piano concede prima di
# dire al consulente che non ci arriva. Budget del runtime, non del modello:
# CODE_QUALITY.md tiene limiti e deadline da questa parte del confine.
PLAN_REVIEW_MAX_ATTEMPTS = 2


# --- identita' delle voci del piano ---------------------------------------


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _by_id(entry: dict) -> str:
    """L'identita' di una voce: l'id se c'e', altrimenti l'etichetta.

    Un modello che rigenera il piano puo' cambiare gli id senza cambiare il
    processo. Cadere sull'etichetta evita che la stessa attivita' entri due
    volte solo perche' e' stata rinumerata.
    """
    return _normalized(entry.get("id")) or _normalized(entry.get("label"))


def _by_label(entry: dict) -> str:
    return _normalized(entry.get("label")) or _normalized(entry.get("id"))


def _by_question(entry: dict) -> str:
    return unknown_question_id(str(entry.get("question") or ""))


def _by_edge(entry: dict) -> str:
    return "->".join(
        (
            _normalized(entry.get("source_id")),
            _normalized(entry.get("target_id")),
            _normalized(entry.get("condition")),
        )
    )


def _by_actor(entry: dict) -> str:
    return _normalized(entry.get("actor_id"))


def _by_step(entry: dict) -> str:
    return _normalized(entry.get("step"))


def _by_hint(entry: dict) -> str:
    return f"{_normalized(entry.get('element'))}|{_normalized(entry.get('hint'))}"


# Come si riconosce "la stessa voce" in ogni lista del piano. Una lista che non
# compare qui e' una lista di stringhe e si unisce per testo normalizzato.
_LIST_KEYS: dict[str, Callable[[dict], str]] = {
    "actors": _by_id,
    "events": _by_id,
    "steps": _by_id,
    "decisions": _by_id,
    "handoffs": _by_id,
    "data_objects": _by_id,
    "participants": _by_id,
    "document_requirements": _by_id,
    "exceptions": _by_id,
    "controls": _by_id,
    "structured_business_rules": _by_id,
    "alternative_paths": _by_id,
    "out_of_scope_alternatives": _by_id,
    "loops": _by_id,
    "consultant_findings": _by_id,
    "flow_edges": _by_edge,
    "unknowns": _by_question,
    "actor_relationships": _by_actor,
    "input_outputs": _by_step,
    "bpmn_modeling_hints": _by_hint,
    "unified_elements": _by_id,
}

_TOPOLOGY_LIST_KEYS: dict[str, Callable[[dict], str]] = {
    "pools": _by_id,
    "lanes": _by_id,
    "message_flows": _by_id,
}

# Percorsi ordinati: qui l'unione non ha senso, l'ordine *e'* l'informazione.
# Chi ne dichiara uno nuovo sta riordinando, e riordinare e' una modifica
# legittima; chi non lo dichiara non sta cancellando quello di prima.
_ORDERED_SEQUENCES = frozenset({"sequence", "main_success_path"})

# Ricalcolati a valle da `build_bpmn_review_draft` su tutto il piano fuso: farli
# sopravvivere al merge significherebbe portarsi dietro il giudizio dato su meta'
# del piano.
_RECOMPUTED_FIELDS = frozenset({"quality_report"})


def _is_empty(value: Any) -> bool:
    """Il campo dice qualcosa, o e' silenzio?

    La distinzione e' l'intera regola del merge: un campo assente in cio' che
    arriva non e' una cancellazione. Se lo fosse, ogni amend parziale
    cancellerebbe il piano intorno a se'.
    """
    if value is None:
        return True
    if isinstance(value, (str, list, dict, tuple, set)):
        return len(value) == 0
    return False


def _merge_scalar(base: Any, incoming: Any) -> Any:
    return base if _is_empty(incoming) else incoming


def _merge_entry(base: dict, incoming: dict) -> dict:
    """Due versioni della stessa voce: cio' che la nuova dichiara vince.

    Campo per campo, non voce per voce. Una `source_evidence` gia' registrata
    sopravvive a un aggiornamento che non la ripete, ed e' cio' che tiene la
    provenance attaccata al piano attraverso le revisioni.
    """
    merged = dict(base)
    for key, value in incoming.items():
        if _is_empty(value):
            continue
        if isinstance(value, list) and isinstance(base.get(key), list):
            merged[key] = _merge_string_list(base[key], value)
        else:
            merged[key] = value
    return merged


def _merge_string_list(base: list, incoming: list) -> list:
    """Unione che conserva l'ordine: prima cio' che c'era, poi cio' che e' nuovo."""
    seen = {_normalized(item) for item in base if isinstance(item, (str, int, float))}
    merged = list(base)
    for item in incoming:
        if isinstance(item, (str, int, float)):
            if _normalized(item) not in seen:
                seen.add(_normalized(item))
                merged.append(item)
        elif item not in merged:
            merged.append(item)
    return merged


def _merge_keyed_list(
    base: list, incoming: list, key: Callable[[dict], str]
) -> tuple[list, int, int]:
    """Unisce due liste di voci del piano per identita' stabile.

    Returns:
        La lista fusa, quante voci sono nuove e quante sono state aggiornate.
    """
    merged: list[dict] = []
    index: dict[str, int] = {}
    for entry in base:
        if not isinstance(entry, dict):
            continue
        index.setdefault(key(entry) or f"__anon__{len(merged)}", len(merged))
        merged.append(dict(entry))

    added = updated = 0
    for entry in incoming:
        if not isinstance(entry, dict):
            continue
        entry_key = key(entry) or f"__new__{len(merged)}"
        position = index.get(entry_key)
        if position is None:
            index[entry_key] = len(merged)
            merged.append(dict(entry))
            added += 1
        else:
            previous = merged[position]
            fused = _merge_entry(previous, entry)
            if fused != previous:
                merged[position] = fused
                updated += 1
    return merged, added, updated


def _merge_topology(base: Any, incoming: Any) -> Any:
    if not isinstance(incoming, dict):
        return base
    if not isinstance(base, dict):
        return incoming
    merged = dict(base)
    for key, value in incoming.items():
        if _is_empty(value):
            continue
        if key in _TOPOLOGY_LIST_KEYS and isinstance(value, list):
            merged[key], _, _ = _merge_keyed_list(
                base.get(key) or [], value, _TOPOLOGY_LIST_KEYS[key]
            )
        elif isinstance(value, list) and isinstance(base.get(key), list):
            merged[key] = _merge_string_list(base[key], value)
        else:
            merged[key] = value
    return merged


@dataclass(frozen=True)
class PlanDiff:
    """Cosa e' cambiato nel piano, per campo. Serve a raccontarlo e a verificarlo."""

    added: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.updated)

    @property
    def added_total(self) -> int:
        return sum(self.added.values())

    @property
    def updated_total(self) -> int:
        return sum(self.updated.values())

    def as_dict(self) -> dict[str, Any]:
        return {
            "added": dict(self.added),
            "updated": dict(self.updated),
            "added_total": self.added_total,
            "updated_total": self.updated_total,
        }

    def as_sentence(self) -> str:
        if self.is_empty:
            return "nessuna voce nuova rispetto al piano corrente"
        parts = [
            f"{count} {name} aggiunt{'a' if count == 1 else 'e'}"
            for name, count in sorted(self.added.items())
            if count
        ]
        parts += [
            f"{count} {name} aggiornat{'a' if count == 1 else 'e'}"
            for name, count in sorted(self.updated.items())
            if count
        ]
        return ", ".join(parts)


OrderedSequencePolicy = Literal["replace", "append"]


def _resolve_unified_ids(base_data: dict, incoming_data: dict) -> dict:
    """Riporta sull'elemento sopravvissuto gli id che il piano ha gia' unificato.

    Un emendamento puo' ancora nominare un passaggio con l'id che aveva prima
    dell'unificazione - lo ha letto in una versione precedente, o in un rilievo
    del revisore. Senza questa risoluzione il doppione rientrerebbe nel piano
    dalla porta dell'emendamento, e l'unificazione durerebbe una versione.
    """
    unified = base_data.get("unified_elements") or []
    if not unified:
        return incoming_data
    from backend.agents.plan_consolidation import rewrite_references

    node_alias: dict[str, str] = {}
    actor_alias: dict[str, str] = {}
    for item in unified:
        if not isinstance(item, dict):
            continue
        alias = actor_alias if item.get("kind") == "actor" else node_alias
        for absorbed in item.get("absorbed_ids") or []:
            alias[str(absorbed)] = str(item.get("id"))
    resolved = rewrite_references(incoming_data, node_alias, actor_alias)
    for name, alias in (("actors", actor_alias), ("events", node_alias), ("steps", node_alias), ("decisions", node_alias)):
        for entry in resolved.get(name) or []:
            if isinstance(entry, dict) and entry.get("id") in alias:
                entry["id"] = alias[entry["id"]]
    return resolved


def merge_process_understanding(
    base: ProcessUnderstanding | dict | None,
    incoming: ProcessUnderstanding | dict,
    *,
    ordered_sequences: OrderedSequencePolicy = "replace",
) -> tuple[ProcessUnderstanding, PlanDiff]:
    """Il piano corrente piu' cio' che arriva, senza perdere cio' che c'era.

    Deterministico e senza LLM. Le liste di voci si uniscono per identita'
    stabile e le voci omonime si fondono campo per campo; le liste di stringhe
    si uniscono per testo; i percorsi ordinati (`sequence`, `main_success_path`)
    non si uniscono - chi ne dichiara uno lo sta riordinando, chi tace lo lascia
    com'era.

    Args:
        base: Il piano gia' persistito, o `None` se non ce n'e' uno.
        incoming: Il piano proposto, anche parziale.
        ordered_sequences: Cosa fare di `sequence` e `main_success_path`.
            `replace` e' la regola dell'emendamento: chi dichiara un percorso lo
            sta riordinando, e chi tace lo lascia com'era. `append` serve quando
            i due piani sono due **letture parziali dello stesso processo** - una
            estrazione per intervista - e nessuna delle due descrive il percorso
            intero: li' sostituire significherebbe tenere solo il pezzo di chi ha
            parlato per ultimo.

    Returns:
        Il piano fuso e il diff di cio' che e' cambiato.
    """
    incoming_data = (
        incoming.model_dump(mode="json")
        if isinstance(incoming, ProcessUnderstanding)
        else dict(incoming)
    )
    if base is None:
        model = ProcessUnderstanding.model_validate(incoming_data)
        counts = {
            name: len(incoming_data.get(name) or [])
            for name in _LIST_KEYS
            if incoming_data.get(name)
        }
        return model, PlanDiff(added=counts)

    base_data = (
        base.model_dump(mode="json")
        if isinstance(base, ProcessUnderstanding)
        else dict(base)
    )
    incoming_data = _resolve_unified_ids(base_data, incoming_data)

    merged = dict(base_data)
    added: dict[str, int] = {}
    updated: dict[str, int] = {}

    for key, value in incoming_data.items():
        if key in _RECOMPUTED_FIELDS:
            continue
        if key == "bpmn_topology":
            merged[key] = _merge_topology(base_data.get(key), value)
            continue
        if key in _ORDERED_SEQUENCES:
            merged[key] = (
                _merge_string_list(base_data.get(key) or [], value or [])
                if ordered_sequences == "append" and isinstance(value, list)
                else _merge_scalar(base_data.get(key), value)
            )
            continue
        if key in _LIST_KEYS and isinstance(value, list):
            fused, new_entries, changed = _merge_keyed_list(
                base_data.get(key) or [], value, _LIST_KEYS[key]
            )
            merged[key] = fused
            if new_entries:
                added[key] = new_entries
            if changed:
                updated[key] = changed
            continue
        if isinstance(value, list) and isinstance(base_data.get(key), list):
            fused_strings = _merge_string_list(base_data[key], value)
            if len(fused_strings) > len(base_data[key]):
                added[key] = len(fused_strings) - len(base_data[key])
            merged[key] = fused_strings
            continue
        merged[key] = _merge_scalar(base_data.get(key), value)

    merged["quality_report"] = None
    return ProcessUnderstanding.model_validate(merged), PlanDiff(added=added, updated=updated)


# --- scrittura del piano ---------------------------------------------------


@dataclass(frozen=True)
class PlanWrite:
    """L'esito di una scrittura sul piano, come il database la conferma.

    `action` dice cosa e' successo davvero. `version` e' la versione riletta, non
    quella che si sperava di scrivere: e' il dato che rende "salvato" verificabile
    invece che dichiarato.
    """

    action: PlanAction
    version: int = 0
    previous_version: int = 0
    diff: PlanDiff = field(default_factory=PlanDiff)
    snapshot: ProcessKnowledgeSnapshot | None = None
    review: dict | None = None
    reason: str = ""
    blockers: list[str] = field(default_factory=list)

    @property
    def persisted(self) -> bool:
        """La scrittura e' arrivata al database e la rilettura lo conferma."""
        return self.action in {"amended", "replaced", "created"} and self.version > self.previous_version

    def as_log_entry(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "version": self.version,
            "previous_version": self.previous_version,
            "persisted": self.persisted,
            "diff": self.diff.as_dict(),
            "reason": self.reason,
            "snapshot_id": self.snapshot.snapshot_id if self.snapshot else None,
            "snapshot_label": self.snapshot.label if self.snapshot else None,
        }


def write_process_plan(
    process_id: str,
    incoming: ProcessUnderstanding | dict,
    *,
    strategy: PlanStrategy = "amend",
    change_summary: str = "",
) -> PlanWrite:
    """Scrive il Modeling Plan e non dichiara riuscito cio' che non rilegge.

    Non tocca il BPMN. Il piano e' un artefatto suo: si modifica, sale di
    versione, e resta leggibile alla riapertura senza che nessun disegno cambi.

    Args:
        process_id: Il processo, non affidabile.
        incoming: Il piano proposto, anche parziale quando `strategy="amend"`.
        strategy: `amend` unisce al piano corrente, `replace` lo rifa' da capo.
        change_summary: Cosa e' cambiato, registrato con la versione.

    Returns:
        L'esito, con la versione riletta e il diff.

    Side effects:
        Scrive una nuova versione della review e la rilegge per verificarla.
        Un fallimento lascia intatta la versione precedente.
    """
    from backend import workspace_database
    from backend.graphs.process.nodes import evidence_count, load_evidence_ledger

    process = workspace_database.get_process(process_id)
    if process is None:
        return PlanWrite(
            action="process_not_found",
            reason=f"Processo non trovato: {process_id}",
            blockers=[f"Processo non trovato: {process_id}"],
        )

    bpmn_model_id = str(process.get("bpmn_model_id") or "")
    ledger = load_evidence_ledger(process.get("project_id"), process_id)
    recorded_evidence = evidence_count(ledger)

    previous = workspace_database.get_bpmn_review(bpmn_model_id, include_approved=True)
    previous_version = int((previous or {}).get("version") or 0)
    base = (previous or {}).get("process_understanding") if strategy == "amend" else None

    merged, diff = merge_process_understanding(base, incoming)

    # La regola del confine vale anche qui, e vale prima della scrittura: un
    # piano senza attori, partecipanti ne' attivita' su un processo che ha fonti
    # agli atti non e' prudenza, e' evidenza che non e' arrivata fino al piano.
    ignored = plan_ignores_evidence(merged, recorded_evidence)
    if ignored:
        return PlanWrite(
            action="rejected_empty_plan",
            previous_version=previous_version,
            snapshot=build_process_snapshot(process_id),
            reason=f"{ignored} {PLAN_IGNORES_EVIDENCE_REMEDY}",
            blockers=[ignored],
        )

    # Un amend che non aggiunge niente non e' una scrittura: farlo salire di
    # versione renderebbe "il piano e' cambiato" un'affermazione falsa, e il
    # Canvas usa proprio quel numero per accorgersi che il piano e' cambiato
    # sotto i piedi del disegno in corso.
    if strategy == "amend" and previous is not None and diff.is_empty:
        return PlanWrite(
            action="unchanged",
            version=previous_version,
            previous_version=previous_version,
            diff=diff,
            snapshot=build_process_snapshot(process_id),
            review=previous,
            reason="Il piano contiene gia' tutto cio' che e' arrivato in questa richiesta.",
        )

    summary = change_summary.strip() or (
        "Piano aggiornato" if strategy == "amend" else "Piano ricostruito"
    )
    # Le note su cui il piano nasce sono le fonti, non il riassunto della
    # modifica. Non e' cosmetica: il filtro di ancoraggio giudica le domande del
    # piano contro questo testo, e un piano preparato su una riga di riassunto si
    # vedeva scartare le proprie lacune come "non ancorate all'evidenza" - la
    # conoscenza spariva nel passaggio che doveva salvarla.
    from backend.agents.process_synthesis import evidence_corpus

    source_narrative = evidence_corpus(ledger) if recorded_evidence else summary

    try:
        if previous is None:
            workspace_database.prepare_bpmn_review(
                bpmn_model_id=bpmn_model_id,
                process_description=source_narrative,
                process_understanding=merged.model_dump(mode="json"),
                evidence_source_set_id=str(ledger.get("source_set_id") or ""),
            )
        else:
            workspace_database.revise_bpmn_review(
                bpmn_model_id=bpmn_model_id,
                process_understanding=merged.model_dump(mode="json"),
                change_summary=summary,
            )
        review = verify_review_persisted(
            bpmn_model_id,
            expect_plan_content=True,
            minimum_version=previous_version + 1,
        )
    except (PersistenceVerificationError, ValueError) as exc:
        logger.warning(
            "piano non persistito per il processo %s: %s", process_id, exc, exc_info=True
        )
        return PlanWrite(
            action="write_failed",
            previous_version=previous_version,
            snapshot=build_process_snapshot(process_id),
            reason=str(exc),
            blockers=[str(exc)],
        )

    action: PlanAction = (
        "created" if previous is None else ("amended" if strategy == "amend" else "replaced")
    )
    return PlanWrite(
        action=action,
        version=int(review.get("version") or 0),
        previous_version=previous_version,
        diff=diff,
        snapshot=build_process_snapshot(process_id),
        review=review,
        reason=summary,
    )


# --- il piano si fa rivedere ----------------------------------------------


def _declared_node_ids(plan: dict) -> set[str]:
    """Tutto cio' che nel piano puo' stare a un capo di un arco.

    Non solo le attivita': un percorso di eccezione e' un evento di bordo, e un
    esito di decisione e' un ramo. Contare le sole attivita' faceva risultare
    "non definito" il percorso urgente che il piano definiva eccome, e un difetto
    inventato in un loop di correzione e' un loop che non puo' finire.
    """
    ids: set[str] = set()
    for name in ("steps", "events", "decisions", "exceptions", "alternative_paths"):
        for entry in plan.get(name) or []:
            if isinstance(entry, dict) and entry.get("id"):
                ids.add(_normalized(entry["id"]))
    for decision in plan.get("decisions") or []:
        if not isinstance(decision, dict):
            continue
        for outcome in decision.get("outcome_details") or []:
            if isinstance(outcome, dict) and outcome.get("id"):
                ids.add(_normalized(outcome["id"]))
    return ids


def _referenced_step_ids(plan: dict) -> set[str]:
    referenced: set[str] = set()
    for name in ("sequence", "main_success_path"):
        referenced.update(_normalized(item) for item in plan.get(name) or [])
    for path in plan.get("alternative_paths") or []:
        if isinstance(path, dict):
            referenced.update(_normalized(item) for item in path.get("sequence") or [])
    for edge in plan.get("flow_edges") or []:
        if isinstance(edge, dict):
            referenced.add(_normalized(edge.get("source_id")))
            referenced.add(_normalized(edge.get("target_id")))
    return {item for item in referenced if item}


@dataclass(frozen=True)
class PlanReview:
    """Il giudizio deterministico sul piano persistito.

    `issues` sono i difetti che una passata di modellazione puo' correggere, e
    sono cio' che fa girare il loop. `warnings` sono cose da dire, non da
    riparare: farle guidare il loop lo farebbe girare su punti che nessuna
    passata puo' chiudere, e un loop che non puo' finire e' peggio del difetto.
    """

    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    draft_allowed: bool = False
    validation_complete: bool = False
    signature: str = ""

    @property
    def is_clean(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {
            "issues": list(self.issues),
            "warnings": list(self.warnings),
            "draft_allowed": self.draft_allowed,
            "validation_complete": self.validation_complete,
            "signature": self.signature,
        }


def review_process_plan(snapshot: ProcessKnowledgeSnapshot | None) -> PlanReview:
    """Il piano regge rispetto a cio' che il processo sa?

    Non e' una valutazione di stile: e' l'elenco delle cose che rendono un piano
    non utilizzabile come base di un disegno. Un piano collassato a inizio e fine
    mentre tre interviste descrivono sei passaggi non e' un piano prudente, e
    dichiararlo completato e' il modo in cui il difetto passava.

    Le due soglie restano due e viaggiano qui come flag, non come prosa:
    `draft_allowed` autorizza una bozza con le lacune dentro, `validation_complete`
    dichiara l'AS-IS validato. Un piano puo' - e nel caso normale deve - essere
    il primo senza essere il secondo.

    Sola lettura.
    """
    if snapshot is None:
        return PlanReview(issues=["Processo non trovato: non c'e' un piano da rivedere."])

    draft = snapshot.draft_readiness or {}
    validation = snapshot.validation_readiness or {}
    draft_allowed = draft.get("status") in {"modelable", "synthesizable"} and not (
        draft.get("blockers") or []
    )
    validation_complete = validation.get("status") == "ready_for_approval"

    if not snapshot.has_semantic_model:
        if snapshot.evidence_count:
            return PlanReview(
                issues=[
                    f"Il processo ha {snapshot.evidence_count} elementi di evidenza agli "
                    "atti e nessun piano strutturato: il piano va costruito su quelli."
                ],
                draft_allowed=draft_allowed,
                validation_complete=False,
                signature="no_plan_with_evidence",
            )
        return PlanReview(
            warnings=["Nessuna evidenza registrata: prima le fonti, poi il piano."],
            draft_allowed=False,
            validation_complete=False,
            signature="no_plan_no_evidence",
        )

    plan = snapshot.process_understanding or {}
    issues: list[str] = []
    warnings: list[str] = []

    steps = [entry for entry in plan.get("steps") or [] if isinstance(entry, dict)]
    actors = plan.get("actors") or []
    participants = plan.get("participants") or []

    if not steps:
        issues.append(
            "Il piano non contiene nessuna attivita': un processo descritto dalle "
            "fonti non puo' ridursi a un inizio e una fine."
        )
    if not (actors or participants):
        issues.append(
            "Il piano non dichiara nessun attore ne' partecipante: senza di loro "
            "non ci sono corsie da disegnare, e il lavoro resta senza proprietario."
        )

    declared = _declared_node_ids(plan)
    referenced = _referenced_step_ids(plan)
    dangling = sorted(referenced - declared)
    if dangling:
        issues.append(
            "Il flusso del piano cita passaggi che il piano non definisce: "
            + ", ".join(dangling[:6])
        )

    if steps and not referenced:
        issues.append(
            "Il piano elenca attivita' ma non dice in che ordine avvengono: "
            "senza percorso principale ne' collegamenti non c'e' un flusso da disegnare."
        )

    orphans = [
        str(entry.get("label") or entry.get("id"))
        for entry in steps
        if referenced and _normalized(entry.get("id")) not in referenced
    ]
    if orphans:
        issues.append(
            "Attivita' presenti nel piano ma agganciate a nessun percorso: "
            + ", ".join(orphans[:6])
        )

    unowned = [
        str(entry.get("label") or entry.get("id"))
        for entry in steps
        if not (entry.get("actor_ids") or [])
    ]
    if unowned:
        issues.append(
            "Attivita' senza responsabile dichiarato: " + ", ".join(unowned[:6])
        )

    # Il piano deve reggere l'evidenza, non solo essere coerente con se stesso.
    # Questo resta un avviso e non un difetto: una voce puo' comparire nel piano
    # come ruolo invece che come nome, e trasformarlo in un difetto farebbe
    # girare il loop su una cosa che nessuna passata puo' chiudere.
    plan_text = _normalized(
        " ".join(
            str(entry.get("label") or "")
            for entry in [*actors, *participants]
            if isinstance(entry, dict)
        )
    )
    unrepresented = [
        voice
        for source in snapshot.sources
        for voice in source.participants
        if _normalized(voice) and _normalized(voice) not in plan_text
    ]
    if unrepresented:
        warnings.append(
            "Voci sentite nelle fonti che il piano non nomina fra attori o "
            "partecipanti: " + ", ".join(sorted(set(unrepresented))[:6])
        )

    if not snapshot.plan_is_current and snapshot.evidence_count:
        warnings.append(
            "Il piano non risulta costruito sul set di fonti corrente: potrebbe "
            "descrivere il processo prima dell'ultima intervista."
        )

    for blocker in draft.get("blockers") or []:
        if blocker not in issues:
            issues.append(str(blocker))

    return PlanReview(
        issues=issues,
        warnings=warnings,
        draft_allowed=draft_allowed and not issues,
        validation_complete=validation_complete,
        signature="|".join(sorted(issues)),
    )


def plan_readiness(snapshot: ProcessKnowledgeSnapshot | None) -> dict[str, Any]:
    """Le due soglie come dati, non come prosa.

    Chi legge deve poter distinguere "si puo' disegnare una bozza" da "l'AS-IS e'
    validato" senza interpretare una frase: erano la stessa soglia, e la seconda
    vinceva sempre.
    """
    review = review_process_plan(snapshot)
    return {
        "draft_allowed": review.draft_allowed,
        "validation_complete": review.validation_complete,
        "draft_readiness": (snapshot.draft_readiness if snapshot else None),
        "validation_readiness": (snapshot.validation_readiness if snapshot else None),
        "plan_issues": review.issues,
        "plan_warnings": review.warnings,
    }
