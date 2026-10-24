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

import heapq
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from lxml import etree

from tests.evals.graph_metrics import stems

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


# --- qualita' pragmatica (Tabelle A.16 e A.18) ---------------------------------

# Quattro soglie per metrica dividono i valori in cinque gruppi (Tabella A.18).
# `desc`: meno e' meglio; `asc`: piu' e' meglio. Le direzioni sono quelle della
# Tabella A.16; il testo del paper cita CNC e token split fra le metriche "piu'
# e' meglio", ma la tabella delle formule le normalizza discendenti e qui vale
# la tabella.
PRAGMATIC_THRESHOLDS: dict[str, tuple[str, tuple[float, float, float, float]]] = {
    "tnn": ("desc", (29.9, 43.7, 58.1, 81.1)),
    "tng": ("desc", (1.42, 3.36, 5.3, 6.49)),
    "tnsf": ("desc", (19.4, 34.8, 50.2, 74.8)),
    "tnmf": ("desc", (1.09, 7.15, 13.2, 22.8)),
    "diameter": ("desc", (7.92, 12.2, 16.5, 23.4)),
    "density": ("desc", (0.1361169, 0.357143, 0.741667, 2.33333)),
    "agd": ("desc", (3.67, 3.88, 4.06, 4.18)),
    "cnc": ("desc", (0.37, 0.9, 1.43, 4.18)),
    "gh": ("desc", (0.62, 0.79, 0.92, 0.94)),
    "cfc": ("desc", (13, 22, 37, 51)),
    "cc": ("asc", (0.007996, 0.030407, 0.061814, 0.112903)),
    "sequentiality": ("desc", (0.25, 0.48, 0.7, 1.07)),
    "separability": ("asc", (0.03, 0.37, 0.71, 1.24)),
    "depth": ("desc", (0.42, 1.72, 3.02, 5.09)),
    "token_split": ("desc", (0.12, 0.21, 0.6, 1.36)),
}

PRAGMATIC_GROUPS = {
    "size": ("tnn", "tng", "tnsf", "tnmf", "diameter"),
    "density": ("density", "agd", "cnc"),
    "connector_interplay": ("gh", "cfc", "cc"),
    "partitionability": ("sequentiality", "separability", "depth"),
    "concurrency": ("token_split",),
}


def normalize(value: float, direction: str, thresholds: tuple[float, float, float, float]) -> float:
    """Equazioni (1) e (2): il gruppo del valore, da 1.0 (facile) a 0.0 (difficile).

    Con TNN = 45 e soglie (29.9, 43.7, 58.1, 81.1) il gruppo e' il terzo: 0.5.
    """
    group = sum(1 for threshold in thresholds if value >= threshold)
    score = 1.0 - 0.25 * group
    return score if direction == "desc" else 1.0 - score


def _acyclic_successors(model: Model) -> dict[str, list[str]]:
    """Il grafo senza gli archi all'indietro di una visita dagli inizi.

    Diametro e profondita' sono definiti sui cammini da un inizio a una fine:
    un ciclo li renderebbe infiniti, e un cammino semplice non lo ripercorre.
    """
    successors = model.successors()
    roots = [n.id for n in model.of(START_TAGS)] or [
        node_id for node_id in model.nodes if not model.incoming(node_id)
    ]
    roots += [node_id for node_id in model.nodes if node_id not in roots]
    state: dict[str, int] = {}
    kept: dict[str, list[str]] = {node_id: [] for node_id in model.nodes}
    for root in roots:
        if root in state:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        state[root] = 1
        while stack:
            node_id, index = stack.pop()
            targets = successors[node_id]
            if index < len(targets):
                stack.append((node_id, index + 1))
                target = targets[index]
                if state.get(target) == 1:
                    continue
                kept[node_id].append(target)
                if target not in state:
                    state[target] = 1
                    stack.append((target, 0))
            else:
                state[node_id] = 2
    return kept


def _topological(order_of: dict[str, list[str]]) -> list[str]:
    indegree = {node_id: 0 for node_id in order_of}
    for targets in order_of.values():
        for target in targets:
            indegree[target] += 1
    ready = sorted(node_id for node_id, count in indegree.items() if count == 0)
    order: list[str] = []
    while ready:
        current = ready.pop()
        order.append(current)
        for target in order_of[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    return order


def _diameter(model: Model) -> int:
    """Mendling: il cammino piu' lungo da un inizio a una fine, contato in nodi."""
    dag = _acyclic_successors(model)
    ends = {n.id for n in model.of(END_TAGS)} or {node_id for node_id, out in dag.items() if not out}
    starts = [n.id for n in model.of(START_TAGS)] or [
        node_id for node_id in model.nodes if not model.incoming(node_id)
    ]
    longest: dict[str, int] = {}
    for node_id in reversed(_topological(dag)):
        tails = [longest[t] for t in dag[node_id] if t in longest]
        if node_id in ends:
            longest[node_id] = max([1, *(1 + tail for tail in tails)])
        elif tails:
            longest[node_id] = 1 + max(tails)
    return max((longest.get(start, 0) for start in starts), default=0)


def _depth(model: Model) -> int:
    """Mendling: la massima annidatura, min(profondita' d'ingresso, d'uscita).

    Lungo un cammino uno split apre un livello per i nodi che seguono, un join
    lo chiude per se stesso; la profondita' d'uscita e' la stessa cosa sul
    grafo rovesciato.
    """
    dag = _acyclic_successors(model)
    splits = {g.id for g in model.gateways if len(model.outgoing(g.id)) > 1}
    joins = {g.id for g in model.gateways if len(model.incoming(g.id)) > 1}
    reverse: dict[str, list[str]] = {node_id: [] for node_id in dag}
    for source, targets in dag.items():
        for target in targets:
            reverse[target].append(source)

    def sweep(forward: dict[str, list[str]], opens: set[str], closes: set[str]) -> dict[str, int]:
        backward: dict[str, list[str]] = {node_id: [] for node_id in forward}
        for source, targets in forward.items():
            for target in targets:
                backward[target].append(source)
        level: dict[str, int] = {}
        for node_id in _topological(forward):
            before = [level[p] + (1 if p in opens else 0) for p in backward[node_id]]
            level[node_id] = max(0, max(before, default=0) - (1 if node_id in closes else 0))
        return level

    inward = sweep(dag, splits, joins)
    outward = sweep(reverse, joins, splits)
    return max((min(inward[n], outward[n]) for n in model.nodes), default=0)


def _cut_vertices(model: Model) -> set[str]:
    """Punti di articolazione del grafo non orientato (Tarjan, iterativo)."""
    neighbours: dict[str, set[str]] = {node_id: set() for node_id in model.nodes}
    for source, targets in model.successors().items():
        for target in targets:
            if source != target:
                neighbours[source].add(target)
                neighbours[target].add(source)
    discovery: dict[str, int] = {}
    low: dict[str, int] = {}
    cuts: set[str] = set()
    clock = 0
    for root in model.nodes:
        if root in discovery:
            continue
        discovery[root] = low[root] = clock
        clock += 1
        children = 0
        stack: list[tuple[str, str | None, list[str]]] = [(root, None, sorted(neighbours[root]))]
        while stack:
            node_id, parent, pending = stack[-1]
            if pending:
                nxt = pending.pop()
                if nxt == parent:
                    continue
                if nxt in discovery:
                    low[node_id] = min(low[node_id], discovery[nxt])
                else:
                    discovery[nxt] = low[nxt] = clock
                    clock += 1
                    if node_id == root:
                        children += 1
                    stack.append((nxt, node_id, sorted(neighbours[nxt])))
                continue
            stack.pop()
            if parent is not None:
                low[parent] = min(low[parent], low[node_id])
                if parent != root and low[node_id] >= discovery[parent]:
                    cuts.add(parent)
        if children > 1:
            cuts.add(root)
    return cuts


def _node_weight(model: Model, node: Node) -> float:
    """Vanderfeesten et al. (2008): il peso di un nodo nella cross-connectivity."""
    if not node.is_gateway:
        return 1.0
    degree = len(model.incoming(node.id)) + len(model.outgoing(node.id))
    if degree == 0 or node.gateway_kind == "AND":
        return 1.0
    if node.gateway_kind == "XOR":
        return 1.0 / degree
    combinations = 2**degree - 1
    return 1.0 / combinations + (combinations - 1) / combinations * (1.0 / degree)


def _cross_connectivity(model: Model) -> float:
    """Vanderfeesten et al. (2008): quanto forte e' il legame medio fra due nodi.

    Il peso di un arco e' il prodotto dei pesi dei suoi nodi, il valore di un
    cammino il prodotto dei suoi archi, quello di una coppia il cammino migliore.
    Con pesi in (0, 1] il cammino migliore e' il piu' corto in -log(peso).
    """
    nodes = list(model.nodes.values())
    if len(nodes) < 2:
        return 0.0
    weight = {node.id: _node_weight(model, node) for node in nodes}
    successors = model.successors()
    total = 0.0
    for origin in nodes:
        best: dict[str, float] = {}
        queue: list[tuple[float, str]] = [(0.0, origin.id)]
        while queue:
            cost, current = heapq.heappop(queue)
            for target in successors[current]:
                arc = weight[current] * weight[target]
                next_cost = cost - math.log(arc)
                if next_cost < best.get(target, math.inf):
                    best[target] = next_cost
                    heapq.heappush(queue, (next_cost, target))
        total += sum(math.exp(-cost) for target, cost in best.items() if target != origin.id)
    return total / (len(nodes) * (len(nodes) - 1))


def pragmatic_values(model: Model) -> dict[str, float]:
    """Le 15 misure grezze, prima delle soglie.

    Dove la Tabella A.16 del PDF e' illeggibile vale la fonte citata: CFC di
    Cardoso (OR = 2^|out| - 1), sequenzialita' di Mendling (archi fra due nodi
    che non sono gateway, sul totale degli archi).
    """
    nodes, flows, gateways = model.nodes, model.sequence_flows, model.gateways
    splits = [g for g in gateways if len(model.outgoing(g.id)) > 1]
    kinds = [g.gateway_kind for g in gateways]
    heterogeneity = 0.0
    if kinds:
        for kind in ("AND", "XOR", "OR"):
            share = kinds.count(kind) / len(kinds)
            if share:
                heterogeneity -= share * math.log(share, 3)
    cfc = sum(
        1 if g.gateway_kind == "AND"
        else len(model.outgoing(g.id)) if g.gateway_kind == "XOR"
        else 2 ** len(model.outgoing(g.id)) - 1
        for g in splits
    )
    size = len(nodes)
    return {
        "tnn": size,
        "tng": len(gateways),
        "tnsf": len(flows),
        "tnmf": len(model.message_flows),
        "diameter": _diameter(model),
        "density": len(flows) / (size * (size - 1)) if size > 1 else 0.0,
        "agd": (
            sum(len(model.incoming(g.id)) + len(model.outgoing(g.id)) for g in gateways) / len(gateways)
            if gateways else 0.0
        ),
        "cnc": len(flows) / size if size else 0.0,
        "gh": heterogeneity,
        "cfc": cfc,
        "cc": _cross_connectivity(model),
        "sequentiality": (
            sum(1 for s, t in flows if not nodes[s].is_gateway and not nodes[t].is_gateway) / len(flows)
            if flows else 0.0
        ),
        "separability": len(_cut_vertices(model)) / (size - 2) if size > 2 else 0.0,
        "depth": _depth(model),
        "token_split": sum(
            len(model.outgoing(g.id)) - 1 for g in splits if g.gateway_kind in {"AND", "OR"}
        ),
    }


def pragmatic_metrics(model: Model) -> dict[str, float]:
    """Le 15 metriche pragmatiche, ognuna gia' portata in [0, 1] dalle soglie."""
    values = pragmatic_values(model)
    return {
        name: normalize(values[name], direction, thresholds)
        for name, (direction, thresholds) in PRAGMATIC_THRESHOLDS.items()
    }


# --- qualita' semantica (Tabella A.17) ------------------------------------------

# Dijkman et al. (2011): pesi della parola identica e del sinonimo nella
# somiglianza semantica delle etichette. Un dizionario di sinonimi italiani non
# c'e': il termine dei sinonimi vale zero e la misura si riduce al Dice sulle
# radici, che e' il caso peggiore per il modello valutato, mai il migliore.
WORD_WEIGHT = 1.0
SYNONYM_WEIGHT = 0.75
# Sotto questa somiglianza due nodi non sono "lo stesso nodo" per la distanza di
# edit e per nodi/archi comuni (Dijkman usa una soglia di corrispondenza).
MATCH_CUTOFF = 0.5


def _levenshtein(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, char_left in enumerate(left, 1):
        current = [i]
        for j, char_right in enumerate(right, 1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_left != char_right))
            )
        previous = current
    return previous[-1]


def syntactic_label_similarity(left: str, right: str) -> float:
    """1 - distanza di Levenshtein / lunghezza dell'etichetta piu' lunga."""
    left, right = left.casefold().strip(), right.casefold().strip()
    longest = max(len(left), len(right))
    return 1.0 if longest == 0 else 1.0 - _levenshtein(left, right) / longest


def semantic_label_similarity(left: str, right: str) -> float:
    """Dijkman: parole in comune sulle radici, senza dizionario di sinonimi."""
    words_left, words_right = stems(left), stems(right)
    if not words_left and not words_right:
        return 1.0 if left.strip().casefold() == right.strip().casefold() else 0.0
    if not words_left or not words_right:
        return 0.0
    overlap = len(words_left & words_right)
    return 2 * WORD_WEIGHT * overlap / (len(words_left) + len(words_right))


def optimal_assignment(scores: list[list[float]]) -> list[tuple[int, int]]:
    """Accoppiamento bipartito di somma massima (algoritmo ungherese, O(n^3)).

    Ritorna solo le coppie con punteggio positivo: un nodo accoppiato a zero
    resta di fatto senza corrispondenza.
    """
    rows = len(scores)
    cols = len(scores[0]) if rows else 0
    if rows == 0 or cols == 0:
        return []
    size = max(rows, cols)
    top = max(max(row) for row in scores)
    cost = [
        [top - (scores[i][j] if i < rows and j < cols else 0.0) for j in range(size)]
        for i in range(size)
    ]
    inf = float("inf")
    u, v = [0.0] * (size + 1), [0.0] * (size + 1)
    match, way = [0] * (size + 1), [0] * (size + 1)
    for i in range(1, size + 1):
        match[0], column = i, 0
        minimum, used = [inf] * (size + 1), [False] * (size + 1)
        while True:
            used[column] = True
            row, delta, nxt = match[column], inf, 0
            for j in range(1, size + 1):
                if not used[j]:
                    current = cost[row - 1][j - 1] - u[row] - v[j]
                    if current < minimum[j]:
                        minimum[j], way[j] = current, column
                    if minimum[j] < delta:
                        delta, nxt = minimum[j], j
            for j in range(size + 1):
                if used[j]:
                    u[match[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            column = nxt
            if match[column] == 0:
                break
        while column:
            previous = way[column]
            match[column] = match[previous]
            column = previous
    pairs = []
    for j in range(1, size + 1):
        i = match[j] - 1
        if i < rows and j - 1 < cols and scores[i][j - 1] > 0:
            pairs.append((i, j - 1))
    return pairs


def _category(node: Node) -> str:
    return "gateway" if node.is_gateway else "event" if node.is_event else "activity"


def _labelled(model: Model) -> list[Node]:
    """I nodi confrontati per etichetta: tutti tranne i gateway (`G` nel paper)."""
    return [node for node in model.nodes.values() if not node.is_gateway]


def _matched_score(
    candidate: list[Node], reference: list[Node], similarity
) -> tuple[float, list[tuple[Node, Node, float]]]:
    """2 * somma delle somiglianze accoppiate / (nodi del candidato + del riferimento)."""
    if not candidate and not reference:
        return 1.0, []
    scores = [
        [similarity(c, r) if _category(c) == _category(r) else 0.0 for r in reference] for c in candidate
    ]
    pairs = [(candidate[i], reference[j], scores[i][j]) for i, j in optimal_assignment(scores)]
    return 2 * sum(score for _, _, score in pairs) / (len(candidate) + len(reference)), pairs


def _work_neighbours(model: Model, node_id: str, forward: bool) -> set[str]:
    """I nodi etichettati subito prima (o dopo), attraversando i gateway."""
    step = model.outgoing if forward else model.incoming
    found: set[str] = set()
    seen = {node_id}
    frontier = list(step(node_id))
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        if model.nodes[current].is_gateway:
            frontier.extend(step(current))
        else:
            found.add(current)
    return found


def _context_similarity(
    candidate: Model, reference: Model, mapping: dict[str, str], left: Node, right: Node
) -> float:
    """Dijkman: quanti vicini (prima e dopo) dei due nodi si corrispondono."""
    total = 0.0
    for forward in (False, True):
        mine = _work_neighbours(candidate, left.id, forward)
        theirs = _work_neighbours(reference, right.id, forward)
        if mine and theirs:
            shared = sum(1 for node_id in mine if mapping.get(node_id) in theirs)
            total += shared / (2 * (len(mine) * len(theirs)) ** 0.5)
        elif not mine and not theirs:
            # Entrambi senza vicini da quel lato (un inizio, una fine): Dijkman
            # lascia la frazione indefinita, qui conta come corrispondenza piena.
            total += 0.5
    return total


def _node_mapping(candidate: Model, reference: Model) -> dict[str, str]:
    """La corrispondenza fra nodi per struttura e comportamento: per etichetta,
    nella stessa categoria, sopra `MATCH_CUTOFF`. Gateway compresi."""
    left, right = list(candidate.nodes.values()), list(reference.nodes.values())
    _, pairs = _matched_score(
        left, right, lambda c, r: max(semantic_label_similarity(c.name, r.name), 1e-6)
    )
    return {c.id: r.id for c, r, score in pairs if score >= MATCH_CUTOFF}


def _relation_overlap(left: set[tuple[str, str]], right: set[tuple[str, str]]) -> float:
    union = left | right
    return 1.0 if not union else len(left & right) / len(union)


def _behaviour(model: Model, name_of: dict[str, str]) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Footprint causale (chi precede chi, anche a distanza) e grafo delle
    dipendenze (chi viene subito dopo chi) sui nodi etichettati.

    E' la lettura operativa dei due insiemi della Tabella A.17 (CF e DG), che il
    paper rimanda a [55, 57] senza formula propria: relazioni d'ordine fra nodi,
    con `name_of` che da' lo stesso nome ai nodi accoppiati dei due modelli.
    """
    successors = model.successors()
    direct: set[tuple[str, str]] = set()
    causal: set[tuple[str, str]] = set()
    for node in _labelled(model):
        for nxt in _work_neighbours(model, node.id, True):
            direct.add((name_of[node.id], name_of[nxt]))
        for later in _reachable(successors, node.id) - {node.id}:
            if not model.nodes[later].is_gateway:
                causal.add((name_of[node.id], name_of[later]))
    return causal, direct


def semantic_metrics(candidate: Model, reference: Model) -> dict[str, float]:
    """Le 7 metriche semantiche del candidato contro il modello di riferimento."""
    left, right = _labelled(candidate), _labelled(reference)
    syntactic, _ = _matched_score(left, right, lambda c, r: syntactic_label_similarity(c.name, r.name))
    semantic, label_pairs = _matched_score(
        left, right, lambda c, r: semantic_label_similarity(c.name, r.name)
    )
    label_mapping = {c.id: r.id for c, r, _ in label_pairs}
    context, _ = _matched_score(
        left, right, lambda c, r: _context_similarity(candidate, reference, label_mapping, c, r)
    )

    mapping = _node_mapping(candidate, reference)
    nodes_total = len(candidate.nodes) + len(reference.nodes)
    edges_total = len(candidate.sequence_flows) + len(reference.sequence_flows)
    candidate_edges = {(mapping.get(s, f"~{s}"), mapping.get(t, f"~{t}")) for s, t in candidate.sequence_flows}
    reference_edges = set(reference.sequence_flows)
    unmatched_nodes = nodes_total - 2 * len(mapping)
    unmatched_edges = len(candidate_edges ^ reference_edges)
    substitution = sum(
        1 - semantic_label_similarity(candidate.nodes[c].name, reference.nodes[r].name)
        for c, r in mapping.items()
    )
    snv = unmatched_nodes / nodes_total if nodes_total else 0.0
    sev = unmatched_edges / edges_total if edges_total else 0.0
    sbv = 2 * substitution / (nodes_total - unmatched_nodes) if nodes_total - unmatched_nodes else 0.0
    common = (
        1 - (unmatched_nodes + unmatched_edges) / (nodes_total + edges_total)
        if nodes_total + edges_total else 1.0
    )

    candidate_names = {node_id: f"#{mapping[node_id]}" if node_id in mapping else f"c:{node_id}" for node_id in candidate.nodes}
    matched = set(mapping.values())
    reference_names = {node_id: f"#{node_id}" if node_id in matched else f"r:{node_id}" for node_id in reference.nodes}
    candidate_causal, candidate_direct = _behaviour(candidate, candidate_names)
    reference_causal, reference_direct = _behaviour(reference, reference_names)
    return {
        "syntactic_label_similarity": round(syntactic, 4),
        "semantic_label_similarity": round(semantic, 4),
        "context_similarity": round(context, 4),
        "graph_edit_similarity": round(1 - (snv + sev + sbv) / 3, 4),
        "common_nodes_and_edges": round(common, 4),
        "causal_footprint_overlap": round(_relation_overlap(candidate_causal, reference_causal), 4),
        "dependency_graph_overlap": round(_relation_overlap(candidate_direct, reference_direct), 4),
    }

