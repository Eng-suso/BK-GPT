"""Quanto un BPMN prodotto somiglia alla mappa che un consulente avrebbe disegnato.

La rubrica esistente (`rubric.py`) risponde si' o no a domande sul caso Esaote:
ci sono i tre reparti, c'e' la soglia, il percorso urgente e' agganciato. E'
utile e non generalizza: non dice *quanto* un modello e' vicino al riferimento,
non si confronta fra due versioni dell'estrattore e vale per un caso solo.

Qui il confronto e' fra due grafi - il BPMN prodotto e una mappa di riferimento
scritta da un consulente - con metriche che hanno lo stesso significato su
qualunque processo:

| metrica | cosa misura |
| --- | --- |
| attivita' - precision | quanto di cio' che il modello disegna e' nel riferimento |
| attivita' - recall | quanto del riferimento il modello disegna |
| corsie | le attivita' riconosciute stanno nella corsia giusta? |
| gateway - recall | le decisioni del riferimento diventano punti di decisione? |
| flussi - recall | l'ordine del riferimento si ritrova nel grafo prodotto? |
| flussi - precision | l'ordine che il modello disegna e' quello del riferimento? |
| violazioni | elementi che il riferimento dichiara **vietati**: cio' che le fonti non dicono e un modello tende a inventare |
| lacune | domande che il riferimento dichiara aperte: il modello non deve chiuderle disegnando |

Tutto deterministico. Il confronto delle etichette usa radici di parola e
alias scritti nel riferimento, non un modello: un eval giudicato da un LLM misura
l'accordo fra due LLM.

Formato del riferimento: vedi `tests/golden/README.md`.
"""

from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"

ACTIVITY_TAGS = frozenset(
    {
        "task", "userTask", "manualTask", "serviceTask", "sendTask", "receiveTask",
        "businessRuleTask", "scriptTask", "subProcess", "callActivity",
    }
)
GATEWAY_TAGS = frozenset(
    {"exclusiveGateway", "inclusiveGateway", "parallelGateway", "eventBasedGateway", "complexGateway"}
)

# Soglia di corrispondenza fra un'etichetta prodotta e un alias del riferimento:
# quota delle radici dell'alias che si ritrovano nell'etichetta. Gli alias sono
# corti e scelti da chi scrive il riferimento, quindi la soglia puo' essere alta.
LABEL_MATCH_THRESHOLD = 0.6
STEM_CHARS = 5
MIN_TOKEN_CHARS = 3

_STOPWORDS = frozenset(
    """
    il lo la i gli le un uno una di a da in con su per tra fra del della dei delle
    dal dalla al alla allo agli alle nel nella sul sulla e ed o che chi cui non si
    ci se come quando dove piu poi anche gia dell dall nell sull
    """.split()
)
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)


def stems(text: str) -> frozenset[str]:
    """Radici di contenuto di un testo: la stessa parola flessa conta una volta."""
    folded = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    words = _NON_WORD.sub(" ", folded.casefold()).split()
    return frozenset(
        word[:STEM_CHARS]
        for word in words
        if len(word) >= MIN_TOKEN_CHARS and word not in _STOPWORDS
    )


def label_score(label: str, aliases: list[str]) -> float:
    """Quanto un'etichetta prodotta corrisponde al migliore degli alias."""
    produced = stems(label)
    best = 0.0
    for alias in aliases:
        wanted = stems(alias)
        if not wanted:
            continue
        best = max(best, len(wanted & produced) / len(wanted))
    return round(best, 4)


# --- il grafo prodotto ------------------------------------------------------


@dataclass(frozen=True)
class ProducedNode:
    id: str
    tag: str
    name: str
    lane: str = ""

    @property
    def is_activity(self) -> bool:
        return self.tag in ACTIVITY_TAGS

    @property
    def is_gateway(self) -> bool:
        return self.tag in GATEWAY_TAGS


@dataclass
class ProducedGraph:
    nodes: dict[str, ProducedNode]
    successors: dict[str, list[str]]

    @property
    def activities(self) -> list[ProducedNode]:
        return [node for node in self.nodes.values() if node.is_activity]

    @property
    def gateways(self) -> list[ProducedNode]:
        return [node for node in self.nodes.values() if node.is_gateway]

    def next_activities(self, node_id: str) -> set[str]:
        """Le attivita' raggiungibili senza attraversare un'altra attivita'.

        E' la relazione "viene subito dopo" che un consulente legge in un
        diagramma: gateway, eventi intermedi e bordi non sono passaggi di lavoro,
        quindi si attraversano.
        """
        found: set[str] = set()
        seen: set[str] = {node_id}
        frontier = list(self.successors.get(node_id, []))
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            node = self.nodes.get(current)
            if node is None:
                continue
            if node.is_activity:
                found.add(current)
                continue
            frontier.extend(self.successors.get(current, []))
        return found


def parse_bpmn(xml: str) -> ProducedGraph:
    """Il grafo di un BPMN: nodi con la loro corsia, archi di sequenza.

    Si leggono tutti i processi della definizione, cosi' una collaborazione con
    piu' pool resta un grafo solo. I bordi (`boundaryEvent`) diventano archi
    dall'attivita' a cui sono attaccati.
    """
    root = ET.fromstring(xml.strip())
    nodes: dict[str, ProducedNode] = {}
    successors: dict[str, list[str]] = {}
    lane_of: dict[str, str] = {}

    for lane in root.iter(f"{{{BPMN_NS}}}lane"):
        lane_name = str(lane.attrib.get("name") or lane.attrib.get("id") or "")
        for ref in lane.findall(f"{{{BPMN_NS}}}flowNodeRef"):
            if ref.text:
                lane_of[ref.text.strip()] = lane_name

    for process in root.iter(f"{{{BPMN_NS}}}process"):
        for element in process.iter():
            tag = element.tag.split("}")[-1]
            element_id = element.attrib.get("id")
            if not element_id or tag in {"process", "laneSet", "lane", "sequenceFlow"}:
                continue
            if tag in ACTIVITY_TAGS or tag in GATEWAY_TAGS or tag.endswith("Event"):
                nodes[element_id] = ProducedNode(
                    id=element_id,
                    tag=tag,
                    name=str(element.attrib.get("name") or ""),
                    lane=lane_of.get(element_id, ""),
                )
                attached = element.attrib.get("attachedToRef")
                if tag == "boundaryEvent" and attached:
                    successors.setdefault(attached, []).append(element_id)
        for flow in process.iter(f"{{{BPMN_NS}}}sequenceFlow"):
            source = flow.attrib.get("sourceRef")
            target = flow.attrib.get("targetRef")
            if source and target:
                successors.setdefault(source, []).append(target)

    return ProducedGraph(nodes=nodes, successors=successors)


# --- il riferimento ----------------------------------------------------------


@dataclass(frozen=True)
class ReferenceActivity:
    id: str
    aliases: list[str]
    lane: str = ""
    required: bool = True


@dataclass(frozen=True)
class ReferenceCase:
    case_id: str
    status: str
    process_name: str
    sources: list[str]
    lanes: dict[str, list[str]]
    activities: list[ReferenceActivity]
    gateways: dict[str, list[str]]
    edges: list[tuple[str, str]]
    forbidden: list[dict[str, Any]]
    open_gaps: list[dict[str, Any]]
    root: Path
    # Cio' che il compilatore oggi non sa esprimere per questo caso. Non e' una
    # tolleranza: il test del compilatore su questo caso e' atteso fallire finche'
    # la lista non e' vuota, e fallisce anche quando il compilatore migliora e la
    # lista resta scritta - cosi' non diventa una scusa permanente.
    compiler_known_gaps: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, folder: Path) -> "ReferenceCase":
        data = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
        activity_ids = {item["id"] for item in data["activities"]}
        lane_ids = {item["id"] for item in data.get("lanes") or []}
        for item in data["activities"]:
            lane = item.get("lane", "")
            if lane and lane not in lane_ids:
                # Una corsia che il riferimento non dichiara renderebbe l'accuratezza
                # delle corsie un numero calcolato su un refuso.
                raise ValueError(f"{folder.name}: {item['id']} in una corsia non dichiarata {lane}")
        edges = [tuple(edge) for edge in data.get("edges") or []]
        for source, target in edges:
            # Un riferimento che cita un'attivita' che non dichiara e' un
            # riferimento rotto: fallire qui evita metriche calcolate su un refuso.
            if source not in activity_ids or target not in activity_ids:
                raise ValueError(f"{folder.name}: arco su attivita' non dichiarata {source}->{target}")
        return cls(
            case_id=data["case_id"],
            status=data.get("status", "draft"),
            process_name=data["process_name"],
            sources=list(data["sources"]),
            lanes={item["id"]: list(item["aliases"]) for item in data.get("lanes") or []},
            activities=[
                ReferenceActivity(
                    id=item["id"],
                    aliases=list(item["aliases"]),
                    lane=item.get("lane", ""),
                    required=bool(item.get("required", True)),
                )
                for item in data["activities"]
            ],
            gateways={item["id"]: list(item["aliases"]) for item in data.get("gateways") or []},
            edges=edges,
            forbidden=list(data.get("forbidden") or []),
            open_gaps=list(data.get("open_gaps") or []),
            root=folder,
            compiler_known_gaps=list(data.get("compiler_known_gaps") or []),
        )

    def source_texts(self) -> list[dict[str, str]]:
        return [
            {
                "id": name,
                "name": name,
                "content": (self.root / "sources" / name).read_text(encoding="utf-8"),
            }
            for name in self.sources
        ]


def load_golden_cases(root: Path) -> list[ReferenceCase]:
    return [
        ReferenceCase.load(folder)
        for folder in sorted(root.iterdir())
        if folder.is_dir() and (folder / "expected.json").exists()
    ]


# --- il confronto ------------------------------------------------------------


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def _f1(precision: float, recall: float) -> float:
    return round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0


@dataclass
class GraphMetrics:
    case_id: str
    activity_precision: float
    activity_recall: float
    activity_f1: float
    lane_accuracy: float
    gateway_recall: float
    edge_precision: float
    edge_recall: float
    forbidden_hits: list[str] = field(default_factory=list)
    gap_violations: list[str] = field(default_factory=list)
    matches: dict[str, str] = field(default_factory=dict)
    missing_activities: list[str] = field(default_factory=list)
    extra_activities: list[str] = field(default_factory=list)

    @property
    def honest(self) -> bool:
        return not self.forbidden_hits and not self.gap_violations

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "activity_precision": self.activity_precision,
            "activity_recall": self.activity_recall,
            "activity_f1": self.activity_f1,
            "lane_accuracy": self.lane_accuracy,
            "gateway_recall": self.gateway_recall,
            "edge_precision": self.edge_precision,
            "edge_recall": self.edge_recall,
            "honest": self.honest,
            "forbidden_hits": self.forbidden_hits,
            "gap_violations": self.gap_violations,
            "missing_activities": self.missing_activities,
            "extra_activities": self.extra_activities,
        }


def _match_activities(
    produced: list[ProducedNode], reference: list[ReferenceActivity]
) -> dict[str, str]:
    """Corrispondenza uno a uno, la migliore per prima.

    Greedy e deterministica: si ordinano tutte le coppie per punteggio e, a
    parita', per id, poi si assegnano scartando cio' che e' gia' preso. Non e'
    l'assegnamento ottimo, ed e' voluto: un matching ottimo sposterebbe
    un'attivita' su un'altra pur di massimizzare il totale, e la metrica
    smetterebbe di dire "questa attivita' e' quella".
    """
    pairs = sorted(
        (
            (label_score(node.name, [ref.id.replace("_", " "), *ref.aliases]), ref.id, node.id)
            for ref in reference
            for node in produced
        ),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    matched: dict[str, str] = {}
    taken: set[str] = set()
    for score, ref_id, node_id in pairs:
        if score < LABEL_MATCH_THRESHOLD:
            break
        if ref_id in matched or node_id in taken:
            continue
        matched[ref_id] = node_id
        taken.add(node_id)
    return matched


def compare(graph: ProducedGraph, case: ReferenceCase) -> GraphMetrics:
    """Il BPMN prodotto confrontato con la mappa di riferimento del caso."""
    activities = graph.activities
    matches = _match_activities(activities, case.activities)
    required = [item for item in case.activities if item.required]

    activity_precision = _ratio(len(matches), len(activities))
    activity_recall = _ratio(sum(1 for item in required if item.id in matches), len(required))

    lane_checks = [
        (graph.nodes[node_id].lane, case.lanes.get(ref.lane, []))
        for ref in case.activities
        if ref.id in matches and ref.lane
        for node_id in [matches[ref.id]]
    ]
    lane_accuracy = _ratio(
        sum(1 for lane, aliases in lane_checks if label_score(lane, aliases) >= LABEL_MATCH_THRESHOLD),
        len(lane_checks),
    )

    gateway_recall = _ratio(
        sum(
            1
            for aliases in case.gateways.values()
            if any(label_score(node.name, aliases) >= LABEL_MATCH_THRESHOLD for node in graph.gateways)
        ),
        len(case.gateways),
    )

    reverse = {node_id: ref_id for ref_id, node_id in matches.items()}
    reference_edges = set(case.edges)
    checkable = [(a, b) for a, b in reference_edges if a in matches and b in matches]
    edge_recall = _ratio(
        sum(1 for a, b in checkable if matches[b] in graph.next_activities(matches[a])),
        len(checkable),
    )
    produced_edges = [
        (reverse[source], reverse[target])
        for source in reverse
        for target in graph.next_activities(source)
        if target in reverse
    ]
    edge_precision = _ratio(
        sum(1 for edge in produced_edges if edge in reference_edges),
        len(produced_edges),
    )

    labels = [node.name for node in graph.nodes.values() if node.name]
    forbidden_hits = [
        f"{rule.get('why', 'vietato')}: «{label}»"
        for rule in case.forbidden
        for label in labels
        if label_score(label, list(rule["aliases"])) >= LABEL_MATCH_THRESHOLD
    ]
    # Una lacuna aperta chiusa disegnando: un'attivita' che risponde alla domanda
    # che nessuna fonte ha risposto.
    gap_violations = [
        f"{gap.get('why', 'lacuna chiusa senza evidenza')}: «{node.name}»"
        for gap in case.open_gaps
        for node in activities
        if label_score(node.name, list(gap.get("closed_by_aliases") or [])) >= LABEL_MATCH_THRESHOLD
    ]

    return GraphMetrics(
        case_id=case.case_id,
        activity_precision=activity_precision,
        activity_recall=activity_recall,
        activity_f1=_f1(activity_precision, activity_recall),
        lane_accuracy=lane_accuracy,
        gateway_recall=gateway_recall,
        edge_precision=edge_precision,
        edge_recall=edge_recall,
        forbidden_hits=forbidden_hits,
        gap_violations=gap_violations,
        matches=matches,
        missing_activities=[item.id for item in required if item.id not in matches],
        extra_activities=[node.name for node in activities if node.id not in reverse],
    )


# --- regressione -------------------------------------------------------------

REGRESSION_METRICS = (
    "activity_precision",
    "activity_recall",
    "lane_accuracy",
    "gateway_recall",
    "edge_precision",
    "edge_recall",
)


def regressions(
    current: dict[str, Any], baseline: dict[str, Any], *, tolerance: float = 0.05
) -> list[str]:
    """Cio' che e' peggiorato rispetto alla baseline, oltre la tolleranza.

    L'onesta' non ha tolleranza: un caso che era onesto e ora inventa e' una
    regressione anche se tutte le altre metriche sono salite.
    """
    found: list[str] = []
    for key in REGRESSION_METRICS:
        before = float(baseline.get(key, 0.0))
        after = float(current.get(key, 0.0))
        if after < before - tolerance:
            found.append(f"{current['case_id']}: {key} {before:.2f} -> {after:.2f}")
    if baseline.get("honest", True) and not current.get("honest", True):
        found.append(
            f"{current['case_id']}: il modello ha smesso di essere onesto "
            f"({'; '.join([*current.get('forbidden_hits', []), *current.get('gap_violations', [])][:3])})"
        )
    return found


def plan_shape(plan: dict[str, Any]) -> dict[str, Any]:
    """La forma del piano come la legge un consulente: quanti passaggi, in che ordine.

    Il confronto col riferimento misura il disegno; qui si misura il piano da cui
    il disegno nasce, perche' i due difetti del merge per fonte - un percorso che
    comincia dalla fonte letta per prima, e lo stesso passaggio contato due volte -
    stanno nel piano prima che nel grafo.
    """
    from backend.process_understanding import (
        ProcessUnderstanding,
        process_understanding_diagnostics,
    )

    labels = {
        entry.get("id"): entry.get("label")
        for name in ("steps", "events", "decisions")
        for entry in plan.get(name) or []
    }
    path = plan.get("main_success_path") or plan.get("sequence") or []
    diagnostics = process_understanding_diagnostics(ProcessUnderstanding.model_validate(plan))
    return {
        "steps": len(plan.get("steps") or []),
        "main_success_path": [labels.get(item, item) for item in path],
        "start_event": (plan.get("boundaries") or {}).get("start_event"),
        "unified_elements": plan.get("unified_elements") or [],
        "consultant_findings": [item.get("finding") for item in plan.get("consultant_findings") or []],
        "diagnostics_blocking": diagnostics.blocking,
    }
