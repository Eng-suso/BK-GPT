"""BEF4LLM: la qualita' di un BPMN sulla scala di un benchmark pubblicato.

Lauer, Pfeiffer, Rombach, Mehdiyev, "Assessing the business process modeling
competences of large language models", Information Systems 142 (2026) 102761.
Il framework misura un BPMN generato su quattro dimensioni, ognuna in [0, 1]:

| dimensione | metriche | cosa chiede |
| --- | --- | --- |
| `Q_val` | 1 | l'XML passa lo schema XSD di BPMN 2.0? Fa da cancello: se no, il resto non si calcola |
| `Q_syn` | 16 | il modello rispetta le regole di BPMN (start/end, archi ammessi, gradi dei nodi, split con join) |
| `Q_prag` | 15 | un umano lo legge? Dimensione, densita', interazione fra gateway, partizionabilita', concorrenza |
| `Q_sem` | 7 | dice quello che dice il modello di riferimento? Etichette, struttura, comportamento |

`Q_qual` e' la media di sintassi, pragmatica e semantica; `Q_total` aggiunge la
validita'. Le metriche di una dimensione pesano tutte uguale (media aritmetica),
come nel paper.

Cosa non e' identico al paper, e perche'. Il codice degli autori sta su un
GitLab del DFKI che da qui non si raggiunge, e le tabelle delle formule
(A.15-A.17) nel PDF hanno esponenti e pedici persi. Dove la formula stampata e'
illeggibile vale la definizione della fonte che il paper cita, ed e' scritta
accanto alla metrica. I punteggi sono quindi confrontabili con quelli
pubblicati come ordine di grandezza, non alla terza cifra.

Fuori dal framework, come nel paper: layout, artefatti (annotazioni, gruppi,
data object) e il contenuto dei sottoprocessi, che contano come un'attivita'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from lxml import etree

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
XSD_DIR = Path(__file__).resolve().parent / "bef4llm_xsd"

ACTIVITY_TAGS = frozenset(
    {
        "task", "userTask", "manualTask", "serviceTask", "sendTask", "receiveTask",
        "businessRuleTask", "scriptTask", "callActivity",
        "subProcess", "transaction", "adHocSubProcess",
    }
)
START_TAGS = frozenset({"startEvent"})
END_TAGS = frozenset({"endEvent"})
INTERMEDIATE_TAGS = frozenset({"intermediateCatchEvent", "intermediateThrowEvent"})
BOUNDARY_TAGS = frozenset({"boundaryEvent"})
EVENT_TAGS = START_TAGS | END_TAGS | INTERMEDIATE_TAGS | BOUNDARY_TAGS

# Il paper ragiona su tre famiglie di gateway (AND, XOR, OR). Event-based
# sceglie un ramo solo, quindi e' XOR; complex puo' attivarne piu' d'uno, OR.
GATEWAY_KIND = {
    "exclusiveGateway": "XOR",
    "eventBasedGateway": "XOR",
    "parallelGateway": "AND",
    "inclusiveGateway": "OR",
    "complexGateway": "OR",
}


# --- validita' ----------------------------------------------------------------


@lru_cache(maxsize=1)
def _schema() -> etree.XMLSchema:
    """Lo schema XSD di BPMN 2.0, lo stesso che usa il paper (bpmn-moddle)."""
    return etree.XMLSchema(etree.parse(str(XSD_DIR / "BPMN20.xsd")))


def validity(xml: str) -> tuple[float, list[str]]:
    """`Q_val`: 1.0 se l'XML si legge e passa lo schema, altrimenti 0.0 e perche'."""
    try:
        document = etree.fromstring(xml.strip().encode("utf-8"))
    except etree.XMLSyntaxError as error:
        return 0.0, [f"XML illeggibile: {error}"]
    schema = _schema()
    if schema.validate(document):
        return 1.0, []
    return 0.0, [f"riga {entry.line}: {entry.message}" for entry in schema.error_log]


# --- il grafo -----------------------------------------------------------------


@dataclass(frozen=True)
class Node:
    id: str
    tag: str
    name: str
    process: str
    attached_to: str = ""
    message: bool = False

    @property
    def is_activity(self) -> bool:
        return self.tag in ACTIVITY_TAGS

    @property
    def is_gateway(self) -> bool:
        return self.tag in GATEWAY_KIND

    @property
    def is_event(self) -> bool:
        return self.tag in EVENT_TAGS

    @property
    def gateway_kind(self) -> str:
        return GATEWAY_KIND.get(self.tag, "")


@dataclass
class Model:
    """I flow object di tutti i processi, gli archi di sequenza e di messaggio.

    I nodi di un sottoprocesso non si leggono: il sottoprocesso e' un nodo
    solo, come nel paper. Un evento di bordo non ha archi entranti: il suo
    legame con l'attivita' sta in `attached_to`.
    """

    nodes: dict[str, Node] = field(default_factory=dict)
    sequence_flows: list[tuple[str, str]] = field(default_factory=list)
    message_flows: list[tuple[str, str]] = field(default_factory=list)
    processes: list[str] = field(default_factory=list)
    participants: dict[str, str] = field(default_factory=dict)
    dangling_flows: int = 0

    def incoming(self, node_id: str) -> list[str]:
        return [source for source, target in self.sequence_flows if target == node_id]

    def outgoing(self, node_id: str) -> list[str]:
        return [target for source, target in self.sequence_flows if source == node_id]

    def of(self, *tags: frozenset[str]) -> list[Node]:
        wanted = frozenset().union(*tags)
        return [node for node in self.nodes.values() if node.tag in wanted]

    @property
    def gateways(self) -> list[Node]:
        return [node for node in self.nodes.values() if node.is_gateway]

    @property
    def activities(self) -> list[Node]:
        return [node for node in self.nodes.values() if node.is_activity]

    def successors(self) -> dict[str, list[str]]:
        """Gli archi da percorrere: sequenza, piu' attivita' -> suo evento di bordo."""
        result: dict[str, list[str]] = {node_id: [] for node_id in self.nodes}
        for source, target in self.sequence_flows:
            result[source].append(target)
        for node in self.nodes.values():
            if node.attached_to in self.nodes:
                result[node.attached_to].append(node.id)
        return result


def _local(tag: object) -> str:
    return str(tag).split("}")[-1]


def parse(xml: str) -> Model:
    """Il `Model` di un BPMN 2.0 che ha gia' passato `validity`."""
    root = etree.fromstring(xml.strip().encode("utf-8"))
    model = Model()
    for process in root.iter(f"{{{BPMN_NS}}}process"):
        process_id = str(process.get("id") or "")
        model.processes.append(process_id)
        for element in process:
            tag = _local(element.tag)
            element_id = element.get("id")
            if not element_id or not (tag in ACTIVITY_TAGS or tag in EVENT_TAGS or tag in GATEWAY_KIND):
                continue
            model.nodes[element_id] = Node(
                id=element_id,
                tag=tag,
                name=str(element.get("name") or "").strip(),
                process=process_id,
                attached_to=str(element.get("attachedToRef") or ""),
                message=element.find(f"{{{BPMN_NS}}}messageEventDefinition") is not None,
            )
        for flow in process.findall(f"{{{BPMN_NS}}}sequenceFlow"):
            source, target = flow.get("sourceRef"), flow.get("targetRef")
            if source in model.nodes and target in model.nodes:
                model.sequence_flows.append((str(source), str(target)))
            else:
                model.dangling_flows += 1
    for participant in root.iter(f"{{{BPMN_NS}}}participant"):
        model.participants[str(participant.get("id"))] = str(participant.get("processRef") or "")
    for flow in root.iter(f"{{{BPMN_NS}}}messageFlow"):
        model.message_flows.append((str(flow.get("sourceRef")), str(flow.get("targetRef"))))
    return model

