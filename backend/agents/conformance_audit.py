"""Il disegno, il piano e le fonti devono dire la stessa cosa. Qui lo si verifica.

Caso Esaote, 2026-09-17: tre interviste agli atti, un piano V1 preparato dal
titolo del processo prima che le interviste arrivassero, e un comando «Genera
BPMN» che per sei volte ha disegnato start -> end rispondendo «ho disegnato la
bozza e l'ho riletta dal canvas salvato». Ogni controllo che esisteva era
vero: il canvas coincideva con il piano, il piano era valido, la scrittura si
rileggeva. Nessuno confrontava il piano con le interviste, e nessuno si chiedeva
se il piano fosse quello delle interviste di adesso.

Questo modulo e' il revisore che mancava, e lavora su due piani.

**Il runtime verifica cio' che si puo' contare** (nessun modello):

| layer | domanda |
| --- | --- |
| `plan_currency` | il piano e' costruito sul set di fonti agli atti adesso? |
| `canvas_plan` | il canvas salvato contiene esattamente i nodi, i nomi e i flussi che il piano compila? |
| `review_plan` | il documento di piano che il consulente legge e' quello del piano strutturato? |
| `plan_sources` | ogni elemento del piano ha un appiglio in una fonte, o e' stato confermato da chi conosce il processo? |

**Un agente giudica cio' che non si puo' contare**, fonte per fonte:

| layer | domanda |
| --- | --- |
| `source_coverage` | la fonte racconta un'attivita', una decisione, un ruolo, un'eccezione che il piano non ha? |
| `source_contradiction` | la fonte dice il contrario di un elemento del piano (un altro attore, un altro ordine, un'altra condizione)? |

Il giudizio e' dell'agente, la prova no: ogni rilievo deve portare la citazione
letterale della fonte, e il runtime la cerca nel testo. Un rilievo con una
citazione che la fonte non contiene si scarta e si conta
(`discarded_findings`): un revisore che inventa le prove non e' un revisore.

`conformant` significa una cosa sola: nessun rilievo deterministico, nessun
rilievo verificato dell'agente, e l'agente ha letto tutte le fonti con un testo.
Se l'agente non ha potuto leggere, il verdetto e' `incomplete` - mai
`conformant` per assenza di chi controlla.
"""

from __future__ import annotations

import hashlib
import json
import logging
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.agents.process_snapshot import ProcessKnowledgeSnapshot
from backend.memory.provenance import FoldedText

logger = logging.getLogger(__name__)

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"

AuditLayer = Literal[
    "plan_currency",
    "canvas_plan",
    "review_plan",
    "plan_sources",
    "source_coverage",
    "source_contradiction",
    # Non un difetto del piano: due voci raccontano lo stesso passaggio in modo
    # diverso. Il piano ha seguito una delle due, e nessuna riscrittura puo'
    # accontentarle entrambe: serve una decisione di chi conosce il processo.
    "source_divergence",
]
FindingSeverity = Literal["blocking", "gap"]
Verdict = Literal[
    "conformant",
    # Il disegno segue le fonti, ma le fonti non dicono tutte la stessa cosa.
    "conformant_with_divergences",
    "not_conformant",
    "incomplete",
]

# I rilievi che una nuova estrazione dalle fonti puo' chiudere. Una divergenza
# fra due voci non e' fra questi: riestrarre la rifarebbe identica.
REPAIRABLE_LAYERS = frozenset({"source_coverage", "source_contradiction"})
LlmAuditStatus = Literal["done", "partial", "skipped", "failed"]

# I nodi che fanno il processo. Il DI, la documentazione e gli attributi di
# estensione non sono contenuto: il layout li riscrive e la marcatura della
# provenance li aggiunge, e un confronto che li contasse fallirebbe su ogni
# bozza corretta.
FLOW_NODE_TYPES = frozenset(
    {
        "startEvent",
        "endEvent",
        "intermediateCatchEvent",
        "intermediateThrowEvent",
        "boundaryEvent",
        "task",
        "userTask",
        "serviceTask",
        "sendTask",
        "receiveTask",
        "manualTask",
        "businessRuleTask",
        "scriptTask",
        "callActivity",
        "subProcess",
        "exclusiveGateway",
        "parallelGateway",
        "inclusiveGateway",
        "eventBasedGateway",
        "complexGateway",
        "lane",
        "participant",
    }
)

# Quante fonti l'agente legge insieme. Sono chiamate di rete indipendenti.
MAX_PARALLEL_AUDITS = 4
# Quanto testo di una fonte legge l'agente: lo stesso limite dell'estrazione,
# perche' una verifica su meno testo di quello estratto dichiarerebbe mancante
# cio' che non ha letto.
AUDIT_SOURCE_CHAR_LIMIT = 120_000
# Come si nomina un elemento del disegno senza etichetta: mai con il suo id.
UNNAMED = "un elemento senza nome"

# Quanti rilievi per layer finiscono nelle righe per il consulente.
CONSULTANT_LINES_PER_LAYER = 6


class ConformanceFinding(BaseModel):
    """Un punto in cui disegno, piano e fonti non dicono la stessa cosa."""

    layer: AuditLayer
    severity: FindingSeverity
    code: str
    message: str
    element_ref: str = ""
    source_id: str = ""
    source_name: str = ""
    # Le parole della fonte, verificate nel testo. Vuota per i layer
    # deterministici che non citano una fonte.
    quote: str = ""


class ConformanceReport(BaseModel):
    """L'esito della verifica, con cio' su cui e' stata fatta."""

    verdict: Verdict
    process_id: str
    snapshot_id: str = ""
    snapshot_label: str = ""
    plan_version: int = 0
    # L'impronta del canvas verificato: un canvas salvato dopo la verifica ne ha
    # un'altra, e il rapporto non vale piu' per lui.
    canvas_signature: str = ""
    findings: list[ConformanceFinding] = Field(default_factory=list)
    llm_audit: LlmAuditStatus = "skipped"
    llm_audit_note: str = ""
    llm_calls: int = 0
    sources_audited: int = 0
    sources_with_text: int = 0
    discarded_findings: int = 0
    audited_at: str = ""

    @property
    def blocking(self) -> list[ConformanceFinding]:
        return [item for item in self.findings if item.severity == "blocking"]

    @property
    def divergences(self) -> list[ConformanceFinding]:
        """I punti in cui sono le fonti a non essere d'accordo fra loro."""
        return [item for item in self.findings if item.layer == "source_divergence"]

    @property
    def needs_plan_repair(self) -> bool:
        """Ci sono rilievi dell'agente che una nuova estrazione puo' chiudere."""
        return any(item.layer in REPAIRABLE_LAYERS for item in self.findings)

    def consultant_lines(self) -> list[str]:
        """I rilievi come li legge il consulente, raggruppati e contati."""
        lines: list[str] = []
        by_layer: dict[str, list[ConformanceFinding]] = {}
        for item in self.findings:
            by_layer.setdefault(item.layer, []).append(item)
        for items in by_layer.values():
            for item in items[:CONSULTANT_LINES_PER_LAYER]:
                lines.append(item.message)
            if len(items) > CONSULTANT_LINES_PER_LAYER:
                lines.append(f"... e altri {len(items) - CONSULTANT_LINES_PER_LAYER} punti dello stesso tipo.")
        if self.verdict == "conformant_with_divergences":
            lines.append(
                "Il disegno segue le fonti: i punti qui sopra sono disaccordi fra le voci, "
                "e si chiudono con una tua conferma."
            )
        if self.verdict == "incomplete":
            lines.append(
                "Il confronto con le fonti non e' completo: "
                + (self.llm_audit_note or "alcune fonti non sono state lette.")
            )
        return lines


# --- il contratto dell'agente --------------------------------------------


DiagramChange = Literal[
    "new_activity",
    "new_decision",
    "new_alternative_path",
    "new_exception_path",
    "new_role",
    "new_start_or_end",
]
ElementChange = Literal[
    "different_performer",
    "different_order",
    "different_condition",
    "step_does_not_happen",
]


class AuditedFact(BaseModel):
    """Un fatto che la fonte racconta e che il disegno dovrebbe mostrare e non mostra."""

    kind: Literal["activity", "decision", "actor", "exception", "event", "rule", "handoff"]
    diagram_change: DiagramChange = Field(
        description="Cosa andrebbe aggiunto al diagramma BPMN per rappresentarlo."
    )
    statement: str = Field(description="Il fatto, in una frase, in italiano.")
    quote: str = Field(
        description="Le parole esatte della fonte che lo dicono, copiate senza modificarle."
    )


class AuditedContradiction(BaseModel):
    """Un elemento del piano che la fonte smentisce."""

    element_ref: str = Field(description="Il riferimento dell'elemento del piano, es. steps:crea_ordine.")
    element_change: ElementChange = Field(
        description="Cosa cambierebbe di quell'elemento nel diagramma."
    )
    quote: str = Field(description="Le parole esatte della fonte che lo smentiscono.")
    explanation: str = Field(description="Cosa dice la fonte di diverso, in una frase.")


class SourceAuditVerdict(BaseModel):
    """Cio' che il revisore ha trovato in una fonte. Liste vuote: la fonte e' rappresentata."""

    missing_facts: list[AuditedFact] = Field(default_factory=list)
    contradicted_elements: list[AuditedContradiction] = Field(default_factory=list)


@dataclass(frozen=True)
class SourceAuditRequest:
    """Una fonte intera e il piano da confrontarci."""

    process_name: str
    source_id: str
    source_name: str
    source_text: str
    plan_elements: list[dict[str, Any]] = field(default_factory=list)


SourceAuditor = Callable[[SourceAuditRequest], SourceAuditVerdict]


AUDITOR_PROMPT = """
Sei il revisore di conformita' di DeliR. Confronti UNA fonte (un'intervista o un
documento) con il piano di un processo AS-IS, elemento per elemento.

Il metro e' il diagramma BPMN: riporti solo cio' che, se la fonte ha ragione,
cambierebbe il disegno. Riporta due cose:

1. missing_facts: fatti che la fonte afferma su come il processo funziona OGGI e
   che il diagramma dovrebbe mostrare e non mostra. In `diagram_change` dichiari
   cosa andrebbe aggiunto: un'attivita', una decisione, un percorso alternativo,
   un percorso d'eccezione, un ruolo (corsia), un evento di inizio o fine.
2. contradicted_elements: elementi del piano che la fonte smentisce. In
   `element_change` dichiari cosa cambierebbe: chi lo esegue, in che ordine, a
   quale condizione, oppure che non avviene.

Non sono rilievi, perche' non cambiano il diagramma: frequenze e abitudini
("di solito la mattina"), durate e tempi di attesa, campi di un modulo, stati di
un registro, strumenti usati, canali di comunicazione quando il passaggio e' gia'
disegnato, opinioni, lamentele, proposte, cio' che la voce dice di non sapere, la
descrizione della giornata di lavoro della persona intervistata.

Regole:
- Ogni rilievo porta in `quote` le parole esatte della fonte, copiate senza
  cambiarle. Un rilievo senza citazione letterale verra' scartato.
- Un fatto gia' rappresentato con parole diverse NON e' mancante.
- Non riportare opinioni, lamentele, proposte di miglioramento, cose che la voce
  dice di non sapere, dettagli di sistema irrilevanti per il flusso.
- Non riportare fatti che il piano non potrebbe contenere perche' la fonte li
  attribuisce a un altro processo.
- Se la fonte e' rappresentata fedelmente, restituisci liste vuote. Liste vuote
  sono una risposta corretta, non un fallimento.
""".strip()


def _render_plan_elements(elements: list[dict[str, Any]]) -> str:
    return json.dumps(elements, ensure_ascii=False, indent=1)


def llm_source_auditor() -> SourceAuditor | None:
    """Il revisore basato sul modello, se il modello e' configurato.

    Returns:
        Il revisore, o ``None`` quando manca la chiave: chi chiama deve poter
        dire "verifica non eseguita" invece di scambiarla per "tutto conforme".
    """
    from backend.settings import settings

    if not settings.openai_api_key:
        return None

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    from backend.llm_config import chat_openai_kwargs
    from backend.llm_streaming import stream_to_final

    runnable = ChatOpenAI(**chat_openai_kwargs()).with_structured_output(SourceAuditVerdict)

    def _audit(request: SourceAuditRequest) -> SourceAuditVerdict:
        raw = stream_to_final(
            runnable,
            [
                SystemMessage(content=AUDITOR_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        {
                            "processo": request.process_name,
                            "fonte": request.source_name,
                            "testo_fonte": request.source_text,
                            "elementi_del_piano": request.plan_elements,
                        },
                        ensure_ascii=False,
                    )
                ),
            ],
        )
        return raw if isinstance(raw, SourceAuditVerdict) else SourceAuditVerdict.model_validate(raw)

    return _audit


# --- layer deterministici ------------------------------------------------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def flow_signature(xml: str) -> dict[str, Any]:
    """Cosa il BPMN dice del processo, in forma confrontabile.

    Nodi e corsie per id con tipo e nome, flussi per id con sorgente e
    destinazione. Nient'altro: il DI e gli attributi di estensione cambiano senza
    che il processo cambi.
    """
    root = ET.fromstring((xml or "").strip())
    nodes: dict[str, tuple[str, str]] = {}
    flows: dict[str, tuple[str, str]] = {}
    for element in root.iter():
        if not element.tag.startswith(f"{{{BPMN_NS}}}"):
            continue
        kind = _local(element.tag)
        element_id = element.attrib.get("id")
        if not element_id:
            continue
        if kind in FLOW_NODE_TYPES:
            nodes[element_id] = (kind, " ".join(str(element.attrib.get("name") or "").split()))
        elif kind == "sequenceFlow":
            flows[element_id] = (
                str(element.attrib.get("sourceRef") or ""),
                str(element.attrib.get("targetRef") or ""),
            )
    return {"nodes": nodes, "flows": flows}


def signature_digest(xml: str | None) -> str:
    if not xml or not xml.strip():
        return ""
    try:
        signature = flow_signature(xml)
    except ET.ParseError:
        return hashlib.sha256(xml.encode("utf-8")).hexdigest()[:16]
    material = json.dumps(
        {
            "nodes": sorted((key, *value) for key, value in signature["nodes"].items()),
            "flows": sorted((key, *value) for key, value in signature["flows"].items()),
        },
        ensure_ascii=False,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def canvas_plan_findings(canvas_xml: str | None, expected_xml: str | None) -> list[ConformanceFinding]:
    """Il canvas salvato contro il BPMN che il piano compila."""
    if not expected_xml:
        return [
            ConformanceFinding(
                layer="canvas_plan",
                severity="blocking",
                code="plan_not_compilable",
                message="Il piano non si traduce in un disegno: va rivisto prima di confrontarlo con il canvas.",
            )
        ]
    if not canvas_xml or not canvas_xml.strip():
        return [
            ConformanceFinding(
                layer="canvas_plan",
                severity="blocking",
                code="canvas_empty",
                message="Il disegno salvato e' vuoto mentre il piano descrive un processo.",
            )
        ]
    try:
        actual = flow_signature(canvas_xml)
    except ET.ParseError as exc:
        return [
            ConformanceFinding(
                layer="canvas_plan",
                severity="blocking",
                code="canvas_unreadable",
                message="Il disegno salvato non si riesce a leggere: va rigenerato dal piano.",
            )
        ]
    expected = flow_signature(expected_xml)

    findings: list[ConformanceFinding] = []
    for node_id, (kind, name) in expected["nodes"].items():
        found = actual["nodes"].get(node_id)
        label = name or UNNAMED
        if found is None:
            findings.append(
                ConformanceFinding(
                    layer="canvas_plan",
                    severity="blocking",
                    code="canvas_missing_element",
                    element_ref=node_id,
                    message=f"Nel disegno manca «{label}», che il piano contiene.",
                )
            )
        elif found != (kind, name):
            findings.append(
                ConformanceFinding(
                    layer="canvas_plan",
                    severity="blocking",
                    code="canvas_element_differs",
                    element_ref=node_id,
                    message=(
                        f"Nel disegno «{found[1] or UNNAMED}» non coincide con il piano, "
                        f"che dice «{label}»."
                    ),
                )
            )
    for node_id, (_kind, name) in actual["nodes"].items():
        if node_id not in expected["nodes"]:
            findings.append(
                ConformanceFinding(
                    layer="canvas_plan",
                    severity="blocking",
                    code="canvas_extra_element",
                    element_ref=node_id,
                    message=f"Nel disegno c'e' «{name or UNNAMED}», che il piano non contiene.",
                )
            )
    names = {key: value[1] or UNNAMED for key, value in {**expected["nodes"], **actual["nodes"]}.items()}
    for flow_id, ends in expected["flows"].items():
        if actual["flows"].get(flow_id) != ends:
            findings.append(
                ConformanceFinding(
                    layer="canvas_plan",
                    severity="blocking",
                    code="canvas_flow_differs",
                    element_ref=flow_id,
                    message=(
                        f"Nel disegno manca o e' diverso il collegamento da «{names.get(ends[0], UNNAMED)}» "
                        f"a «{names.get(ends[1], UNNAMED)}»."
                    ),
                )
            )
    for flow_id, ends in actual["flows"].items():
        if flow_id not in expected["flows"]:
            findings.append(
                ConformanceFinding(
                    layer="canvas_plan",
                    severity="blocking",
                    code="canvas_extra_flow",
                    element_ref=flow_id,
                    message=(
                        f"Nel disegno c'e' un collegamento da «{names.get(ends[0], UNNAMED)}» a "
                        f"«{names.get(ends[1], UNNAMED)}» che il piano non prevede."
                    ),
                )
            )
    return findings


def plan_currency_findings(snapshot: ProcessKnowledgeSnapshot) -> list[ConformanceFinding]:
    if not snapshot.evidence_count or snapshot.plan_is_current:
        return []
    return [
        ConformanceFinding(
            layer="plan_currency",
            severity="blocking",
            code="plan_stale",
            message=(
                "Il piano non tiene conto di tutte le fonti raccolte: e' stato preparato "
                "prima che alcune arrivassero."
            ),
        )
    ]


def review_plan_findings(
    snapshot: ProcessKnowledgeSnapshot, review_brief: str | None
) -> list[ConformanceFinding]:
    """Il documento di piano che il consulente legge viene dal piano strutturato?

    Il documento si puo' modificare a mano; il disegno pero' nasce dal piano
    strutturato. Se i due divergono, il consulente approva un testo e il canvas
    ne disegna un altro.
    """
    if not snapshot.process_understanding or review_brief is None:
        return []
    from backend.process_understanding import ProcessUnderstanding, render_process_review

    try:
        expected = render_process_review(
            ProcessUnderstanding.model_validate(snapshot.process_understanding)
        )
    except ValueError:
        return []
    if " ".join(expected.split()) == " ".join(str(review_brief).split()):
        return []
    return [
        ConformanceFinding(
            layer="review_plan",
            severity="blocking",
            code="review_document_diverges",
            message=(
                "Il testo del piano e' stato modificato a mano e non corrisponde piu' a cio' "
                "che il disegno rappresenta."
            ),
        )
    ]


def plan_source_findings(snapshot: ProcessKnowledgeSnapshot) -> list[ConformanceFinding]:
    report = snapshot.provenance
    if report is None:
        return []
    findings: list[ConformanceFinding] = []
    for item in report.elements:
        if item.consultant_decision == "rejected":
            findings.append(
                ConformanceFinding(
                    layer="plan_sources",
                    severity="blocking",
                    code="rejected_element_in_plan",
                    element_ref=item.source_ref,
                    message=f"«{item.label}» e' stato rifiutato dal consulente ma e' ancora nel piano.",
                )
            )
        elif item.awaiting_confirmation:
            findings.append(
                ConformanceFinding(
                    layer="plan_sources",
                    severity="gap",
                    code="element_without_source",
                    element_ref=item.source_ref,
                    message=f"«{item.label}» non risulta in nessuna fonte e nessuno l'ha confermato.",
                )
            )
    for name in report.unused_sources:
        findings.append(
            ConformanceFinding(
                layer="plan_sources",
                severity="gap",
                code="source_unused",
                source_name=name,
                message=f"Dal piano non risulta niente di cio' che dice «{name}».",
            )
        )
    return findings


# --- l'agente, con le prove verificate -----------------------------------


def plan_elements_for_audit(snapshot: ProcessKnowledgeSnapshot) -> list[dict[str, Any]]:
    """Il piano come lo legge il revisore: elementi con riferimento e citazione."""
    from backend.process_understanding import ProcessUnderstanding

    if not snapshot.process_understanding:
        return []
    plan = ProcessUnderstanding.model_validate(snapshot.process_understanding)
    quotes = {
        item.source_ref: item.quote for item in (snapshot.provenance.elements if snapshot.provenance else [])
    }
    actors = {actor.id: actor.label for actor in plan.actors}
    elements: list[dict[str, Any]] = []

    def add(ref: str, kind: str, label: str, **extra: Any) -> None:
        entry = {"ref": ref, "tipo": kind, "etichetta": label}
        entry.update({key: value for key, value in extra.items() if value})
        if quotes.get(ref):
            entry["citazione_fonte"] = quotes[ref]
        elements.append(entry)

    for actor in plan.actors:
        add(f"actors:{actor.id}", "attore", actor.label)
    for participant in plan.participants:
        add(f"participants:{participant.id}", "partecipante", participant.label)
    for event in plan.events:
        add(f"events:{event.id}", "evento", event.label)
    for step in plan.steps:
        add(
            f"steps:{step.id}",
            "attivita",
            step.label,
            descrizione=step.description,
            chi=", ".join(actors.get(ref, ref) for ref in step.actor_ids),
        )
    for decision in plan.decisions:
        add(
            f"decisions:{decision.id}",
            "decisione",
            decision.label,
            domanda=decision.question,
            esiti=[item.label for item in decision.outcome_details] or decision.outcomes,
        )
    for exception in plan.exceptions:
        add(
            f"exceptions:{exception.id}",
            "eccezione",
            exception.label,
            innesco=exception.trigger,
            gestione=exception.handling,
        )
    for rule in plan.structured_business_rules:
        add(f"structured_business_rules:{rule.id}", "regola", rule.consequence, condizione=rule.condition)
    order = plan.main_success_path or plan.sequence
    if order:
        # Le etichette, non gli id: questo testo torna al consulente dentro un
        # rilievo sull'ordine dei passaggi.
        names = {step.id: step.label for step in plan.steps}
        names.update({event.id: event.label for event in plan.events})
        names.update({decision.id: decision.label for decision in plan.decisions})
        elements.append(
            {
                "ref": "sequence",
                "tipo": "ordine_percorso_principale",
                "etichetta": "L'ordine dei passaggi principali: "
                + " → ".join(names.get(item, UNNAMED) for item in order),
            }
        )
    return elements


@dataclass
class _SourceOutcome:
    findings: list[ConformanceFinding]
    discarded: int
    failed: str = ""


def _verified_source_findings(
    request: SourceAuditRequest,
    verdict: SourceAuditVerdict,
    known_refs: set[str],
    element_sources: dict[str, str] | None = None,
) -> _SourceOutcome:
    labels = {
        str(item.get("ref")): str(item.get("etichetta") or "")
        for item in request.plan_elements
    }
    # Da quale fonte viene l'elemento che questa fonte smentisce. Se viene da
    # un'altra voce, il disaccordo e' fra le due voci, non fra il piano e le
    # fonti: il piano ha seguito una delle due, ed e' esattamente cio' che deve
    # arrivare a chi conosce il processo come domanda.
    origins = element_sources or {}
    folded = FoldedText(request.source_text)
    findings: list[ConformanceFinding] = []
    discarded = 0
    seen_spans: set[tuple[int, int, str]] = set()

    for fact in verdict.missing_facts:
        span = folded.locate(fact.quote)
        if span is None:
            discarded += 1
            continue
        key = (span[0], span[1], "fact")
        if key in seen_spans:
            continue
        seen_spans.add(key)
        quote = folded.text[span[0] : span[1]]
        findings.append(
            ConformanceFinding(
                layer="source_coverage",
                severity="gap",
                code=f"missing_{fact.kind}",
                source_id=request.source_id,
                source_name=request.source_name,
                quote=quote,
                message=(
                    f"«{request.source_name}» dice «{quote}», e il disegno non lo rappresenta "
                    f"({fact.statement})."
                ),
            )
        )

    for contradiction in verdict.contradicted_elements:
        span = folded.locate(contradiction.quote)
        if span is None or contradiction.element_ref not in known_refs:
            discarded += 1
            continue
        quote = folded.text[span[0] : span[1]]
        # Il percorso principale come etichetta e' l'elenco di tutti i passaggi:
        # dentro un rilievo diventa un muro di testo. Si nomina per quello che e'.
        label = (
            "L'ordine dei passaggi"
            if contradiction.element_ref == "sequence"
            else labels.get(contradiction.element_ref) or UNNAMED
        )
        origin = origins.get(contradiction.element_ref) or ""
        if origin and origin != request.source_name:
            findings.append(
                ConformanceFinding(
                    layer="source_divergence",
                    severity="gap",
                    code="sources_disagree",
                    element_ref=contradiction.element_ref,
                    source_id=request.source_id,
                    source_name=request.source_name,
                    quote=quote,
                    message=(
                        f"«{label}»: «{origin}» e «{request.source_name}» lo raccontano in modo "
                        f"diverso. «{request.source_name}» dice «{quote}» "
                        f"({contradiction.explanation}). Il disegno segue «{origin}»: "
                        "serve una tua conferma su come funziona davvero."
                    ),
                )
            )
            continue
        findings.append(
            ConformanceFinding(
                layer="source_contradiction",
                severity="blocking",
                code="element_contradicted",
                element_ref=contradiction.element_ref,
                source_id=request.source_id,
                source_name=request.source_name,
                quote=quote,
                message=(
                    f"«{label}»: «{request.source_name}» "
                    f"dice diversamente - «{quote}» ({contradiction.explanation})."
                ),
            )
        )
    return _SourceOutcome(findings=findings, discarded=discarded)


def _audit_sources(
    snapshot: ProcessKnowledgeSnapshot,
    sources: list[dict],
    auditor: SourceAuditor,
) -> tuple[list[ConformanceFinding], int, int, list[str]]:
    from concurrent.futures import ThreadPoolExecutor

    elements = plan_elements_for_audit(snapshot)
    known_refs = {str(item["ref"]) for item in elements}
    requests = [
        SourceAuditRequest(
            process_name=snapshot.process_name or snapshot.process_id,
            source_id=str(source.get("id") or ""),
            source_name=str(source.get("name") or source.get("id") or "fonte"),
            source_text=str(source.get("content") or "")[:AUDIT_SOURCE_CHAR_LIMIT],
            plan_elements=elements,
        )
        for source in sources
    ]

    element_sources = {
        item.source_ref: item.source_name
        for item in (snapshot.provenance.elements if snapshot.provenance else [])
        if item.status != "unverified" and item.source_name
    }

    def _run(request: SourceAuditRequest) -> _SourceOutcome:
        try:
            verdict = auditor(request)
        except Exception as exc:  # noqa: BLE001 - una fonte non letta non porta via le altre
            logger.warning("verifica di conformita' non riuscita su %s", request.source_name, exc_info=True)
            return _SourceOutcome(findings=[], discarded=0, failed=f"{request.source_name}: {type(exc).__name__}: {exc}")
        return _verified_source_findings(request, verdict, known_refs, element_sources)

    workers = max(1, min(MAX_PARALLEL_AUDITS, len(requests)))
    if workers > 1:
        from backend.agents.process_synthesis import warm_provider_imports

        warm_provider_imports()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="conformance-audit") as pool:
        outcomes = list(pool.map(_run, requests))

    findings = [item for outcome in outcomes for item in outcome.findings]
    discarded = sum(outcome.discarded for outcome in outcomes)
    failures = [outcome.failed for outcome in outcomes if outcome.failed]
    audited = len(requests) - len(failures)
    return findings, discarded, audited, failures


# --- la verifica ---------------------------------------------------------


_AUDITOR_FROM_SETTINGS = object()


def verdict_for(findings: list[ConformanceFinding], llm_audit: LlmAuditStatus) -> Verdict:
    """Il verdetto, dalle sole cose che si possono contare.

    Tre regole, e nessuna scorciatoia:

    - un rilievo che riguarda il disegno o il piano lo rende non conforme;
    - se restano solo disaccordi fra le voci, il disegno segue le fonti e lo si
      dice - ma con i punti da chiarire dichiarati, perche' il consulente deve
      deciderli;
    - senza un revisore che abbia letto tutte le fonti non si dichiara conforme
      niente: `incomplete` e' la risposta onesta quando il controllo non c'e'
      stato.
    """
    if any(item.layer != "source_divergence" for item in findings):
        return "not_conformant"
    if llm_audit != "done":
        return "incomplete"
    return "conformant_with_divergences" if findings else "conformant"


def evaluate_conformance(
    snapshot: ProcessKnowledgeSnapshot,
    *,
    sources: list[dict],
    canvas_xml: str | None,
    review_brief: str | None,
    auditor: SourceAuditor | None,
) -> ConformanceReport:
    """Verifica disegno, piano e fonti di uno snapshot.

    Args:
        snapshot: Lo stato del processo che si dichiara disegnato.
        sources: Le fonti con il loro testo **integrale** (il registro, non gli
            estratti del confine).
        canvas_xml: Il canvas salvato.
        review_brief: Il documento di piano come il consulente lo legge.
        auditor: Il revisore delle fonti; ``None`` quando non e' disponibile.

    Returns:
        Il rapporto. Sola lettura: la persistenza e' di chi chiama.
    """
    from backend.bpmn import BPMNSemanticModel, semantic_model_to_bpmn_xml

    findings: list[ConformanceFinding] = []
    findings += plan_currency_findings(snapshot)

    expected_xml = None
    if snapshot.bpmn_semantic_model:
        try:
            expected_xml = semantic_model_to_bpmn_xml(
                BPMNSemanticModel.model_validate(snapshot.bpmn_semantic_model)
            )
        except Exception:  # noqa: BLE001 - un piano che non compila e' un rilievo, non un crash
            logger.warning("piano non compilabile in verifica per %s", snapshot.process_id, exc_info=True)
    findings += canvas_plan_findings(canvas_xml, expected_xml)
    findings += review_plan_findings(snapshot, review_brief)
    findings += plan_source_findings(snapshot)

    readable = [source for source in sources if str(source.get("content") or "").strip()]
    llm_audit: LlmAuditStatus = "skipped"
    note = ""
    audited = 0
    discarded = 0
    if not readable:
        # Niente testo da leggere: non c'e' nulla da verificare, e dirlo "fatto"
        # e' vero solo se non c'era evidenza con un testo.
        llm_audit = "done"
        note = "nessuna fonte con un testo da verificare."
    elif not snapshot.process_understanding:
        note = "non c'e' ancora un piano da confrontare con le fonti."
    elif auditor is None:
        note = "il confronto con le fonti non e' disponibile in questo momento."
    else:
        source_findings, discarded, audited, failures = _audit_sources(snapshot, readable, auditor)
        findings += source_findings
        if not failures:
            llm_audit = "done"
        elif audited:
            llm_audit = "partial"
            note = "alcune fonti non sono state confrontate: " + ", ".join(
                failure.split(":", 1)[0] for failure in failures
            ) + ". Riprova la verifica."
        else:
            llm_audit = "failed"
            note = "nessuna fonte e' stata confrontata. Riprova la verifica tra qualche minuto."
            logger.warning("verifica fallita su tutte le fonti: %s", "; ".join(failures))

    verdict = verdict_for(findings, llm_audit)

    return ConformanceReport(
        verdict=verdict,
        process_id=snapshot.process_id,
        snapshot_id=snapshot.snapshot_id,
        snapshot_label=snapshot.label,
        plan_version=snapshot.version,
        canvas_signature=signature_digest(canvas_xml),
        findings=findings,
        llm_audit=llm_audit,
        llm_audit_note=note,
        llm_calls=audited if llm_audit in {"done", "partial"} and readable else 0,
        sources_audited=audited,
        sources_with_text=len(readable),
        discarded_findings=discarded,
        audited_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def conformance_is_current(snapshot: ProcessKnowledgeSnapshot, stored: dict | None, canvas_xml: str | None) -> bool:
    """Il rapporto registrato descrive esattamente questo stato?

    Due cose lo identificano: la versione di conoscenza del processo e
    l'impronta del disegno salvato. Se coincidono, rifare il confronto
    spenderebbe una chiamata per fonte per riscrivere le stesse righe - e con il
    confronto acceso su tutti i progetti, quelle chiamate sono il costo che
    decide se la verifica puo' restare sempre attiva.
    """
    if not stored:
        return False
    return (
        stored.get("snapshot_id") == snapshot.snapshot_id
        and stored.get("canvas_signature") == signature_digest(canvas_xml)
    )


def audit_process_conformance(
    process_id: str,
    *,
    auditor: SourceAuditor | None | object = _AUDITOR_FROM_SETTINGS,
    persist: bool = True,
    force: bool = False,
) -> ConformanceReport | None:
    """Verifica lo stato persistito di un processo e registra l'esito.

    Args:
        process_id: Il processo, non affidabile.
        auditor: Il revisore delle fonti. Omesso: quello del modello configurato.
            ``None`` esplicito: nessun revisore, il verdetto sara' al piu'
            `incomplete`.
        persist: Registrare il rapporto sulla review del processo.
        force: Rifare il confronto anche se quello registrato descrive gia'
            questo stato. Serve quando lo si chiede esplicitamente.

    Returns:
        Il rapporto, o ``None`` se il processo non esiste.

    Side effects:
        Chiama il revisore una volta per fonte con testo; scrive il rapporto
        sulla review quando `persist`.
    """
    from backend import workspace_database
    from backend.agents.process_snapshot import build_process_snapshot
    from backend.graphs.process.nodes import load_evidence_ledger

    snapshot = build_process_snapshot(process_id)
    if snapshot is None:
        return None
    resolved = llm_source_auditor() if auditor is _AUDITOR_FROM_SETTINGS else auditor
    ledger = load_evidence_ledger(snapshot.project_id, process_id)
    model = workspace_database.get_bpmn_model(snapshot.bpmn_model_id) if snapshot.bpmn_model_id else None
    review = (
        workspace_database.get_bpmn_review(snapshot.bpmn_model_id, include_approved=True)
        if snapshot.bpmn_model_id
        else None
    )

    stored = ((review or {}).get("conformance") or {}).get("report")
    if not force and conformance_is_current(snapshot, stored, (model or {}).get("xml")):
        logger.info(
            "confronto gia' attuale per il processo %s: nessuna nuova lettura delle fonti",
            process_id,
        )
        existing = ConformanceReport.model_validate(stored)
        if persist:
            try:
                workspace_database.record_conformance_report(snapshot.bpmn_model_id, stored)
            except Exception:  # noqa: BLE001 - lo stato della coda non e' il rapporto
                logger.warning("stato del confronto non aggiornato per %s", process_id, exc_info=True)
        return existing

    report = evaluate_conformance(
        snapshot,
        sources=list(ledger.get("sources") or []),
        canvas_xml=(model or {}).get("xml"),
        review_brief=(review or {}).get("bpmn_brief") if review else None,
        auditor=resolved,  # type: ignore[arg-type]
    )
    if persist and review is not None:
        try:
            workspace_database.record_conformance_report(
                snapshot.bpmn_model_id, report.model_dump(mode="json")
            )
        except Exception:  # noqa: BLE001 - un rapporto non salvato resta un rapporto
            logger.warning("rapporto di conformita' non registrato per %s", process_id, exc_info=True)
    logger.info(
        "conformita' %s per il processo %s (%s): %s rilievi, revisore %s",
        report.verdict,
        process_id,
        report.snapshot_label,
        len(report.findings),
        report.llm_audit,
    )
    return report


def reviewer_notes_by_source(report: ConformanceReport) -> dict[str, list[str]]:
    """I rilievi verificati dell'agente, come note per la nuova estrazione di ogni fonte."""
    notes: dict[str, list[str]] = {}
    for item in report.findings:
        if item.layer not in {"source_coverage", "source_contradiction"} or not item.source_id:
            continue
        if item.layer == "source_coverage":
            line = f"Non rappresentato nel piano precedente: «{item.quote}»."
        else:
            line = f"Il piano precedente contraddice la fonte su {item.element_ref}: «{item.quote}»."
        notes.setdefault(item.source_id, []).append(line)
    return notes
