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


# --- qualita' sintattica (Tabella A.15) ---------------------------------------


def _share(passing: int, total: int) -> float:
    """Quota di elementi che rispettano una regola. Nessun elemento: nessuna violazione."""
    return 1.0 if total == 0 else round(passing / total, 4)


def split_and_join_gateways(model: Model) -> tuple[list[Node], list[Node]]:
    """Ogni gateway e' un join se ha piu' di un arco entrante, altrimenti uno split.

    Il paper non dice dove cade un gateway con piu' entrate e piu' uscite, ne' uno
    con un'entrata e un'uscita: qui ogni gateway e' giudicato una volta sola, e
    in entrambi i casi infrange la regola del suo gruppo (15 o 16).
    """
    joins = [g for g in model.gateways if len(model.incoming(g.id)) > 1]
    splits = [g for g in model.gateways if len(model.incoming(g.id)) <= 1]
    return splits, joins


def _reachable(successors: dict[str, list[str]], start: str) -> set[str]:
    seen: set[str] = set()
    frontier = [start]
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(successors.get(current, []))
    return seen


def _has_matching_join(model: Model, split: Node, joins: list[Node], successors: dict[str, list[str]]) -> bool:
    """Matchgate: un join dello stesso tipo che ogni ramo dello split raggiunge."""
    branches = [_reachable(successors, target) for target in model.outgoing(split.id)]
    if len(branches) < 2:
        return False
    return any(
        join.gateway_kind == split.gateway_kind and all(join.id in branch for branch in branches)
        for join in joins
    )


def _sequence_flow_allowed(model: Model, source: str, target: str) -> bool:
    """Regola 5: un arco di sequenza non esce da una fine, non entra in un inizio
    o in un bordo, e non attraversa il confine di un processo."""
    origin, destination = model.nodes[source], model.nodes[target]
    return (
        origin.tag not in END_TAGS
        and destination.tag not in START_TAGS | BOUNDARY_TAGS
        and origin.process == destination.process
    )


def _message_flow_allowed(model: Model, source: str, target: str) -> bool:
    """Regola 6: un messaggio parte da attivita', fine o evento che lo lancia (o da
    un pool), arriva ad attivita', inizio o evento che lo riceve (o a un pool), e
    collega due pool diversi."""
    pool_of_process = {process: pool for pool, process in model.participants.items() if process}

    def endpoint(element_id: str, sending: bool) -> str | None:
        if element_id in model.participants:
            return element_id
        node = model.nodes.get(element_id)
        if node is None:
            return None
        if sending:
            allowed = node.is_activity or (node.message and node.tag in END_TAGS | {"intermediateThrowEvent"})
        else:
            allowed = node.is_activity or (
                node.message and node.tag in START_TAGS | {"intermediateCatchEvent"} | BOUNDARY_TAGS
            )
        return pool_of_process.get(node.process, node.process) if allowed else None

    origin, destination = endpoint(source, True), endpoint(target, False)
    return origin is not None and destination is not None and origin != destination


def syntactic_metrics(model: Model) -> dict[str, float]:
    """Le 16 regole sintattiche, ognuna in [0, 1].

    Booleane le prime due, quote le altre. La regola 3 (e la 4) nel PDF stampa
    "processi con almeno un inizio" ma si chiama "un inizio per processo": vale
    il nome, cioe' esattamente uno. La regola 10 conta come violazione anche un
    pool senza processo (black box): la formula chiede esattamente un processo.
    """
    starts, ends = model.of(START_TAGS), model.of(END_TAGS)
    intermediates = model.of(INTERMEDIATE_TAGS)
    exceptions = model.of(BOUNDARY_TAGS)
    splits, joins = split_and_join_gateways(model)
    successors = model.successors()
    processes = model.processes or [""]

    def degree(node: Node, inbound: int, outbound: int) -> bool:
        return len(model.incoming(node.id)) == inbound and len(model.outgoing(node.id)) == outbound

    return {
        "start_exists": 1.0 if starts else 0.0,
        "end_exists": 1.0 if ends else 0.0,
        "one_start_per_process": _share(
            sum(1 for p in processes if sum(1 for n in starts if n.process == p) == 1), len(processes)
        ),
        "one_end_per_process": _share(
            sum(1 for p in processes if sum(1 for n in ends if n.process == p) == 1), len(processes)
        ),
        "sequence_flow_rules": _share(
            sum(1 for s, t in model.sequence_flows if _sequence_flow_allowed(model, s, t)),
            len(model.sequence_flows) + model.dangling_flows,
        ),
        "message_flow_rules": _share(
            sum(1 for s, t in model.message_flows if _message_flow_allowed(model, s, t)),
            len(model.message_flows),
        ),
        "start_degree": _share(sum(1 for n in starts if degree(n, 0, 1)), len(starts)),
        "end_degree": _share(sum(1 for n in ends if degree(n, 1, 0)), len(ends)),
        "split_has_join": _share(
            sum(1 for g in splits if _has_matching_join(model, g, joins, successors)), len(splits)
        ),
        "one_process_per_pool": _share(
            sum(1 for process in model.participants.values() if process in model.processes),
            len(model.participants),
        ),
        "tasks_labelled": _share(sum(1 for n in model.activities if n.name), len(model.activities)),
        "task_degree": _share(sum(1 for n in model.activities if degree(n, 1, 1)), len(model.activities)),
        "intermediate_degree": _share(sum(1 for n in intermediates if degree(n, 1, 1)), len(intermediates)),
        "exception_degree": _share(sum(1 for n in exceptions if degree(n, 0, 1)), len(exceptions)),
        "split_degree": _share(
            sum(1 for g in splits if len(model.incoming(g.id)) == 1 and len(model.outgoing(g.id)) > 1),
            len(splits),
        ),
        "join_degree": _share(sum(1 for g in joins if len(model.outgoing(g.id)) == 1), len(joins)),
    }

