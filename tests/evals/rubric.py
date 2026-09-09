"""La rubrica con cui si giudica una mappatura AS-IS, senza chiedere a un LLM.

Un eval che fa giudicare il modello da un altro modello misura l'accordo fra
due modelli. Qui il metro e' il BPMN 2.0 e l'evidenza: si controlla cio' che il
piano dichiara contro cio' che le fonti dicono, e cio' che il compilatore
produce contro cio' che una mappa da consulente senior deve avere. Tutte
verifiche deterministiche, quindi l'eval e' un gate e non un'opinione.

Due famiglie di criteri, e la differenza fra le due e' l'unica cosa che conta
davvero:

- **completezza**: quello che le fonti dicono deve arrivare nel modello - i tre
  reparti, il lavoro di ognuno, la decisione sulla soglia, il percorso urgente;
- **onesta'**: quello che le fonti NON dicono non deve comparire - nessun attore
  inventato, nessun passaggio inventato, e la lacuna che nessuno copre deve
  restare dichiarata invece di essere riempita con una plausibilita'.

Un modello che sbaglia per completezza e' incompleto. Un modello che sbaglia
per onesta' e' peggio: e' un AS-IS che il cliente firmerebbe credendo che
descriva la sua azienda.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.bpmn import BPMNSemanticModel, semantic_model_to_bpmn_xml
from backend.bpmn.soundness import analyze_control_flow
from backend.memory.provenance import _loose, normalize  # noqa: PLC2701
from backend.process_understanding import ProcessUnderstanding
from backend.workspace_services.bpmn_canvas_validation import validate_canvas_against_process


# Parole troppo comuni per dimostrare che un'etichetta viene dalle fonti.
_STOPWORDS = frozenset(
    """
    il lo la i gli le un uno una di a da in con su per tra fra del della dei delle
    dal dalla al alla allo agli alle nel nella sul sulla e ed o oppure che chi cui
    non si ci se come quando dove piu meno molto poi anche solo gia ancora
    essere sono era stato viene vengono fare fa fatto dopo prima
    """.split()
)

_MIN_TOKEN = 4


def content_words(text: str) -> set[str]:
    """Le parole di contenuto di un testo, confrontabili fra loro."""
    return {
        word
        for word in _loose(text).split()
        if len(word) >= _MIN_TOKEN and word not in _STOPWORDS
    }


def grounded_in_sources(label: str, vocabulary: set[str], *, ratio: float = 0.5) -> bool:
    """Questa etichetta poggia sulle parole delle fonti?

    Il controllo e' volutamente permissivo (meta' delle parole di contenuto):
    un consulente riformula, e pretendere il verbatim segnalerebbe come
    invenzione ogni sintesi corretta. Serve a prendere l'altra cosa - un
    passaggio che nelle interviste non esiste in nessuna forma.
    """
    words = content_words(label)
    if not words:
        return True
    return len(words & vocabulary) >= len(words) * ratio


@dataclass
class Criterion:
    id: str
    weight: int
    required: bool
    passed: bool
    detail: str = ""


@dataclass
class RubricResult:
    criteria: list[Criterion] = field(default_factory=list)

    @property
    def score(self) -> float:
        total = sum(item.weight for item in self.criteria) or 1
        return sum(item.weight for item in self.criteria if item.passed) / total

    @property
    def failed_required(self) -> list[Criterion]:
        return [item for item in self.criteria if item.required and not item.passed]

    def report(self) -> str:
        lines = [f"Punteggio: {self.score:.2f}"]
        for item in self.criteria:
            mark = "ok " if item.passed else "NO "
            flag = " [obbligatorio]" if item.required else ""
            lines.append(f"{mark}{item.id}{flag}: {item.detail}")
        return "\n".join(lines)


def _actor_labels(process: ProcessUnderstanding) -> list[str]:
    return [actor.label for actor in process.actors] + [
        participant.label for participant in process.participants
    ]


def score_as_is_model(
    *,
    process: ProcessUnderstanding,
    semantic_model: BPMNSemanticModel,
    source_text: str,
    expected_departments: tuple[str, ...],
    unresolved_gap_terms: tuple[str, ...],
) -> RubricResult:
    """Giudica una mappatura AS-IS contro le fonti da cui e' nata.

    Args:
        process: Il ProcessUnderstanding prodotto dall'agente.
        semantic_model: Il BPMNSemanticModel compilato da quel piano.
        source_text: Il testo delle fonti, che e' il metro dell'onesta'.
        expected_departments: I reparti che le fonti nominano e che quindi
            devono comparire, come radici di parola.
        unresolved_gap_terms: Le parole della lacuna che nessuna fonte copre:
            deve restare una domanda, non diventare un passaggio.

    Returns:
        Il risultato con il punteggio e i criteri, uno per uno.
    """
    vocabulary = content_words(source_text)
    xml = semantic_model_to_bpmn_xml(semantic_model)
    node_types = [node.type for node in semantic_model.flowNodes]
    actor_ids_with_work = {
        actor_id for step in process.steps for actor_id in step.actor_ids
    }
    actors_text = " ".join(_actor_labels(process)).casefold()
    validation = validate_canvas_against_process(
        xml=xml,
        process_understanding=process,
        bpmn_semantic_model=semantic_model,
    )
    control_flow = analyze_control_flow(semantic_model)

    missing_departments = [
        department
        for department in expected_departments
        if department.casefold() not in actors_text
    ]
    unowned_steps = [step.label for step in process.steps if not step.actor_ids]
    ungrounded_actors = [
        label
        for label in _actor_labels(process)
        if not grounded_in_sources(label, vocabulary)
    ]
    ungrounded_steps = [
        step.label
        for step in process.steps
        if not grounded_in_sources(step.label, vocabulary)
    ]
    gap_declared = any(
        any(term in normalize(unknown.question) for term in unresolved_gap_terms)
        for unknown in process.unknowns
    )
    gap_invented_as_step = [
        step.label
        for step in process.steps
        if all(term in normalize(step.label) for term in unresolved_gap_terms[:1])
        and "regolarizz" in normalize(step.label)
    ]
    decisions_with_outcomes = [
        decision
        for decision in process.decisions
        if len(decision.outcomes) >= 2 or len(decision.outcome_details) >= 2
    ]
    unlabelled_edges = [edge.id for edge in process.flow_edges if not edge.label.strip()]

    criteria = [
        Criterion(
            id="reparti_completi",
            weight=3,
            required=True,
            passed=not missing_departments,
            detail=(
                "tutti i reparti nominati dalle fonti sono nel modello"
                if not missing_departments
                else f"reparti assenti dal modello: {', '.join(missing_departments)}"
            ),
        ),
        Criterion(
            id="nessun_attore_inventato",
            weight=3,
            required=True,
            passed=not ungrounded_actors,
            detail=(
                "ogni attore poggia sulle parole delle fonti"
                if not ungrounded_actors
                else f"attori che le fonti non nominano: {', '.join(ungrounded_actors)}"
            ),
        ),
        Criterion(
            id="nessun_passaggio_inventato",
            weight=3,
            required=True,
            passed=len(ungrounded_steps) == 0,
            detail=(
                "ogni attivita' poggia sulle parole delle fonti"
                if not ungrounded_steps
                else f"attivita' che le fonti non descrivono: {', '.join(ungrounded_steps)}"
            ),
        ),
        Criterion(
            id="lacuna_dichiarata_non_riempita",
            weight=3,
            required=True,
            passed=gap_declared and not gap_invented_as_step,
            detail=(
                "la lacuna che nessuna fonte copre e' rimasta una domanda"
                if gap_declared and not gap_invented_as_step
                else "la lacuna e' sparita dal piano o e' diventata un passaggio inventato"
            ),
        ),
        Criterion(
            id="flusso_di_controllo_sano",
            weight=3,
            required=True,
            passed=control_flow.is_sound,
            detail=(
                "nessun nodo irraggiungibile o senza uscita"
                if control_flow.is_sound
                else "; ".join(issue.message for issue in control_flow.errors[:3])
            ),
        ),
        Criterion(
            id="canvas_coerente_col_piano",
            weight=2,
            required=True,
            passed=not (validation.get("issues") or []),
            detail=(
                "il disegno copre il piano senza issue bloccanti"
                if not (validation.get("issues") or [])
                else "; ".join((validation.get("issues") or [])[:3])
            ),
        ),
        Criterion(
            id="ogni_attivita_ha_un_titolare",
            weight=2,
            required=False,
            passed=not unowned_steps,
            detail=(
                "ogni attivita' ha l'attore che la esegue"
                if not unowned_steps
                else f"attivita' senza titolare: {', '.join(unowned_steps[:4])}"
            ),
        ),
        Criterion(
            id="una_corsia_per_chi_lavora",
            weight=2,
            required=False,
            passed=len(semantic_model.lanes) >= len(actor_ids_with_work),
            detail=(
                f"{len(semantic_model.lanes)} corsie per "
                f"{len(actor_ids_with_work)} attori che eseguono lavoro"
            ),
        ),
        Criterion(
            id="evento_di_inizio_dalle_fonti",
            weight=2,
            required=False,
            passed=(
                "startEvent" in node_types
                and bool(process.boundaries)
                and grounded_in_sources(
                    f"{process.boundaries.trigger or ''} {process.boundaries.start_event or ''}",
                    vocabulary,
                )
            ),
            detail="l'inizio del processo e' quello che le fonti descrivono",
        ),
        Criterion(
            id="evento_di_fine",
            weight=1,
            required=False,
            passed="endEvent" in node_types,
            detail=f"eventi di fine nel modello: {node_types.count('endEvent')}",
        ),
        Criterion(
            id="decisione_come_gateway",
            weight=2,
            required=False,
            passed=bool(decisions_with_outcomes)
            and any(node_type.endswith("Gateway") for node_type in node_types),
            detail=(
                f"{len(decisions_with_outcomes)} decisioni con esiti nominati, "
                f"{sum(1 for t in node_types if t.endswith('Gateway'))} gateway nel disegno"
            ),
        ),
        Criterion(
            id="percorso_eccezione_agganciato",
            weight=2,
            required=False,
            passed=bool(process.exceptions or process.alternative_paths)
            and (
                "boundaryEvent" in node_types
                or any(path.sequence for path in process.alternative_paths)
            ),
            detail=(
                "il percorso fuori standard e' modellato e agganciato al flusso"
                if process.exceptions or process.alternative_paths
                else "nessun percorso alternativo o d'eccezione, benche' le fonti ne descrivano uno"
            ),
        ),
        Criterion(
            id="frecce_leggibili",
            weight=1,
            required=False,
            passed=not unlabelled_edges,
            detail=(
                "ogni collegamento dichiarato ha una label"
                if not unlabelled_edges
                else f"collegamenti senza label: {', '.join(unlabelled_edges[:4])}"
            ),
        ),
    ]
    return RubricResult(criteria=criteria)
