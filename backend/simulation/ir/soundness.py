"""VAL-01: un modello di simulazione che puo' sempre finire.

``bpmn_check`` verifica che IR e BPMN parlino degli stessi elementi; qui si
verifica che il processo, con le probabilita' dell'IR, porti ogni caso alla fine.
Si rifiuta un modello che il motore eseguirebbe senza mai chiudere i casi:

- **blocco (deadlock):** il caso ha ancora lavoro aperto ma nessun passo puo'
  partire, per esempio un'unione parallela che aspetta un ramo che una scelta
  ha escluso;
- **ciclo senza uscita (livelock):** il caso continua a muoversi ma da li' la
  fine non e' piu' raggiungibile, per esempio una decisione che torna indietro
  con probabilita' 1 e lascia l'uscita a 0 (lo scenario SIMOD di
  AcademicCredentials in G3);
- **lavoro che si moltiplica:** percorsi paralleli che non si ricongiungono e
  ripartono, finche' il caso non ha piu' un numero finito di stati.

Il metodo e' il gioco dei gettoni del BPMN: uno stato e' quanti gettoni stanno
su ogni flusso; da uno stato si passa al successivo facendo scattare un elemento
abilitato, e una decisione si apre in un ramo per ogni uscita possibile (con la
sua probabilita'). Ogni flusso ha un solo elemento di arrivo, quindi due elementi
non si contendono mai lo stesso gettone: l'ordine in cui scattano non cambia gli
stati che si raggiungono (il sistema e' persistente). Basta allora un ordine
fisso, il primo elemento abilitato, e lo spazio degli stati e' una catena di
Markov in cui l'unica scelta e' quella delle decisioni.

Su questa catena:

- la fine (nessun gettone) deve essere raggiungibile da ogni stato raggiungibile;
  in una catena finita questo vuol dire che ogni caso finisce con probabilita' 1
  e che ogni ciclo ha un'uscita con probabilita' maggiore di zero;
- il numero atteso di esecuzioni di ogni attivita' per caso e' allora finito e
  si calcola risolvendo la catena (componente per componente, dalla prima).

I rami con probabilita' 0 si esplorano lo stesso, marcati come impossibili: cosi'
un ciclo senza uscita dice quale decisione lo chiude e verso dove avrebbe dovuto
uscire. Una decisione per regola (attributi del caso) o a tempo (escalation)
puo' prendere ogni ramo: la verifica la tratta cosi' e non calcola le attese.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from itertools import combinations
from typing import Literal

from defusedxml import ElementTree

from backend.simulation.ir.model import Gateway, SimulationModel

ProblemKind = Literal["no_start", "deadlock", "livelock", "unbounded"]

ACTIVITY_TAGS = frozenset(
    {
        "task",
        "userTask",
        "serviceTask",
        "scriptTask",
        "businessRuleTask",
        "manualTask",
        "sendTask",
        "receiveTask",
        "callActivity",
        "subProcess",
    }
)
_PASS_TAGS = ACTIVITY_TAGS | {"intermediateCatchEvent", "intermediateThrowEvent"}
_CHOICE_TAGS = frozenset({"exclusiveGateway", "eventBasedGateway"})
_INCLUSIVE_TAGS = frozenset({"inclusiveGateway", "complexGateway"})

# Oltre questi limiti la verifica si ferma e lo dice: un flusso con piu' gettoni
# e' lavoro che si moltiplica; troppi stati non si verificano in un import.
MAX_TOKENS_PER_FLOW = 8
MAX_STATES = 50_000
# Rami di un'unica decisione inclusiva oltre i quali non si elencano le combinazioni.
_MAX_INCLUSIVE_BRANCHES = 10

Marking = tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SoundnessProblem:
    """Cosa non torna, detto al consulente, e gli elementi coinvolti."""

    kind: ProblemKind
    message: str  # cosa non torna, in linguaggio di business
    action: str  # cosa fare
    element_ids: tuple[str, ...] = ()
    detail: str = ""  # per specialisti: id e regola violata


@dataclass(frozen=True, slots=True)
class SoundnessReport:
    problems: tuple[SoundnessProblem, ...]
    states: int
    # Esecuzioni attese per caso di ogni attivita'; ``None`` se una decisione non
    # ha probabilita' (regole, escalation, inclusive) o se il modello non finisce.
    expected_executions: dict[str, float] | None = None
    # La verifica si e' fermata prima della fine (troppi stati): nulla e' provato.
    complete: bool = True

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass(slots=True)
class _Graph:
    tags: dict[str, str] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    flow_ends: dict[str, tuple[str, str]] = field(default_factory=dict)
    incoming: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    outgoing: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    terminate: set[str] = field(default_factory=set)
    # attivita' -> eventi di bordo, con True se interrompono l'attivita'
    boundary: dict[str, list[tuple[str, bool]]] = field(default_factory=lambda: defaultdict(list))


@dataclass(frozen=True, slots=True)
class _Step:
    """Uno scatto dallo stato corrente: l'elemento, lo stato dopo, la probabilita'."""

    node: str
    target: Marking
    probability: float | None  # None: possibile, probabilita' sconosciuta
    possible: bool
    via: str | None = None  # il ramo di una decisione


def check_soundness(model: SimulationModel, bpmn_xml: str) -> SoundnessReport:
    """La verifica di VAL-01 del modello ``model`` sul BPMN che il motore eseguira'."""
    graph = _read(bpmn_xml)
    return _Checker(graph, {gateway.element_id: gateway for gateway in model.gateways}).run()


# --------------------------------------------------------------------------- #
# BPMN
# --------------------------------------------------------------------------- #


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read(bpmn_xml: str) -> _Graph:
    root = ElementTree.fromstring(bpmn_xml.encode("utf-8"))
    graph = _Graph()
    for element in root.iter():
        tag = _local(element.tag)
        element_id = element.attrib.get("id")
        if not element_id:
            continue
        if tag == "sequenceFlow":
            source, target = element.attrib.get("sourceRef"), element.attrib.get("targetRef")
            if source and target:
                graph.flow_ends[element_id] = (source, target)
                graph.outgoing[source].append(element_id)
                graph.incoming[target].append(element_id)
            continue
        graph.tags[element_id] = tag
        graph.names[element_id] = (element.attrib.get("name") or "").strip()
        children = {_local(child.tag) for child in element}
        if tag == "endEvent" and "terminateEventDefinition" in children:
            graph.terminate.add(element_id)
        if tag == "boundaryEvent" and element.attrib.get("attachedToRef"):
            interrupting = element.attrib.get("cancelActivity", "true").lower() != "false"
            graph.boundary[element.attrib["attachedToRef"]].append((element_id, interrupting))
    return graph


# --------------------------------------------------------------------------- #
# Spazio degli stati
# --------------------------------------------------------------------------- #


class _Checker:
    def __init__(self, graph: _Graph, gateways: dict[str, Gateway]) -> None:
        self.graph = graph
        self.gateways = gateways
        self.flows = sorted(graph.flow_ends)
        self.index = {flow: i for i, flow in enumerate(self.flows)}
        # Ordine fisso degli elementi: il primo abilitato scatta.
        self.nodes = sorted(node for node in graph.tags if graph.incoming.get(node))
        self.known_probabilities = True
        self._upstream: dict[str, set[int]] = {}

    # ---- regole di scatto ------------------------------------------------- #

    def _put(self, marking: list[int], flows: Iterable[str]) -> None:
        for flow in flows:
            marking[self.index[flow]] += 1

    def _inputs(self, node: str) -> list[int]:
        return [self.index[flow] for flow in self.graph.incoming[node]]

    def _enabled(self, node: str, marking: Marking) -> int | None:
        """L'indice del flusso da cui ``node`` prende il gettone, -1 se li prende tutti."""
        inputs = self._inputs(node)
        tag = self.graph.tags[node]
        if tag == "parallelGateway":
            return -1 if all(marking[i] for i in inputs) else None
        if tag in _INCLUSIVE_TAGS and len(inputs) > 1:
            if not any(marking[i] for i in inputs):
                return None
            return -1 if self._or_join_ready(node, marking) else None
        return next((i for i in inputs if marking[i]), None)

    def _or_join_ready(self, node: str, marking: Marking) -> bool:
        """Unione inclusiva: nessun gettone altrove puo' ancora arrivare a un ingresso vuoto."""
        inputs = set(self._inputs(node))
        empty = {i for i in inputs if not marking[i]}
        for i, tokens in enumerate(marking):
            if tokens and i not in inputs and self._reaches(i, node) & empty:
                return False
        return True

    def _reaches(self, flow: int, join: str) -> set[int]:
        """Gli ingressi di ``join`` che un gettone su ``flow`` puo' raggiungere senza attraversarlo."""
        key = f"{flow}->{join}"
        if key not in self._upstream:
            seen: set[int] = set()
            todo = [flow]
            while todo:
                current = todo.pop()
                if current in seen:
                    continue
                seen.add(current)
                target = self.graph.flow_ends[self.flows[current]][1]
                if target != join:
                    todo.extend(self.index[f] for f in self._outputs(target))
            self._upstream[key] = seen & set(self._inputs(join))
        return self._upstream[key]

    def _outputs(self, node: str) -> list[str]:
        flows = list(self.graph.outgoing.get(node, ()))
        for boundary, _ in self.graph.boundary.get(node, ()):
            flows += self.graph.outgoing.get(boundary, [])
        return flows

    def _steps(self, marking: Marking) -> list[_Step]:
        for node in self.nodes:
            taken = self._enabled(node, marking)
            if taken is None:
                continue
            after = list(marking)
            for i in (self._inputs(node) if taken == -1 else [taken]):
                if after[i]:
                    after[i] -= 1
            return list(self._fire(node, after))
        return []

    def _fire(self, node: str, after: list[int]) -> Iterator[_Step]:
        tag = self.graph.tags[node]
        outgoing = self.graph.outgoing.get(node, [])
        if tag == "endEvent":
            yield _Step(node, tuple(0 for _ in after) if node in self.graph.terminate else tuple(after), 1.0, True)
            return
        if tag in _CHOICE_TAGS and len(outgoing) > 1:
            yield from self._choice(node, after, outgoing)
            return
        if tag in _INCLUSIVE_TAGS and len(outgoing) > 1:
            yield from self._inclusive(node, after, outgoing)
            return
        boundaries = self.graph.boundary.get(node, [])
        normal = list(after)
        self._put(normal, outgoing)
        if not boundaries:
            yield _Step(node, tuple(normal), 1.0, True)
            return
        # Un evento di bordo e' un'altra fine possibile dell'attivita': senza
        # probabilita' nell'IR, ogni esito e' possibile.
        self.known_probabilities = False
        yield _Step(node, tuple(normal), None, True)
        for boundary, interrupting in boundaries:
            alternative = list(after if interrupting else normal)
            self._put(alternative, self.graph.outgoing.get(boundary, []))
            yield _Step(node, tuple(alternative), None, True, via=boundary)

    def _choice(self, node: str, after: list[int], outgoing: list[str]) -> Iterator[_Step]:
        weights = self._weights(node, outgoing)
        for flow in outgoing:
            target = list(after)
            self._put(target, [flow])
            weight = weights.get(flow)
            yield _Step(node, tuple(target), weight, _may_take(weight), via=flow)

    def _inclusive(self, node: str, after: list[int], outgoing: list[str]) -> Iterator[_Step]:
        # Prosimos non documenta come combina i rami di un'inclusiva: ogni
        # combinazione non vuota dei rami possibili e' possibile.
        self.known_probabilities = False
        weights = self._weights(node, outgoing)
        possible = [flow for flow in outgoing if _may_take(weights.get(flow))]
        if len(possible) > _MAX_INCLUSIVE_BRANCHES:
            possible = possible[:_MAX_INCLUSIVE_BRANCHES]
        for size in range(1, len(possible) + 1):
            for chosen in combinations(possible, size):
                target = list(after)
                self._put(target, chosen)
                yield _Step(node, tuple(target), None, True, via=",".join(chosen))
        for flow in outgoing:
            if flow not in possible:
                target = list(after)
                self._put(target, [flow])
                yield _Step(node, tuple(target), 0.0, False, via=flow)

    def _weights(self, node: str, outgoing: list[str]) -> dict[str, float | None]:
        gateway = self.gateways.get(node)
        if gateway is None or gateway.escalation is not None or any(b.condition for b in gateway.branches):
            # Senza probabilita' (porta senza rami nell'IR, regole, escalation): ogni ramo e' possibile.
            self.known_probabilities = False
            return {flow: None for flow in outgoing}
        declared = {branch.flow_id: branch.probability for branch in gateway.branches}
        total = sum(declared.get(flow, 0.0) for flow in outgoing)
        return {flow: (declared.get(flow, 0.0) / total if total else 0.0) for flow in outgoing}

    # ---- esplorazione e analisi ------------------------------------------ #

    def run(self) -> SoundnessReport:
        starts = sorted(node for node, tag in self.graph.tags.items() if tag == "startEvent")
        if not starts:
            return SoundnessReport(
                problems=(
                    SoundnessProblem(
                        "no_start",
                        "Il disegno del processo non ha un inizio: la simulazione non saprebbe da dove far partire i casi.",
                        "Aggiungi l'inizio del processo nel disegno e importa di nuovo lo scenario.",
                        detail="nessuno startEvent nel BPMN",
                    ),
                ),
                states=0,
            )
        initial: list[Marking] = []
        for start in starts:
            seed = [0] * len(self.flows)
            self._put(seed, self.graph.outgoing.get(start, []))
            initial.append(tuple(seed))

        steps: dict[Marking, list[_Step]] = {}
        reachable: set[Marking] = set()  # per rami possibili, dagli stati iniziali
        queue: deque[tuple[Marking, bool]] = deque((m, True) for m in initial)
        overflow: set[Marking] = set()
        while queue:
            marking, possible = queue.popleft()
            if possible:
                if marking in reachable:
                    continue
                reachable.add(marking)
            elif marking in steps:
                continue
            if max(marking, default=0) > MAX_TOKENS_PER_FLOW:
                overflow.add(marking)
                steps[marking] = []
                continue
            if len(steps) >= MAX_STATES:
                return SoundnessReport(problems=(), states=len(steps), complete=False)
            if marking not in steps:
                steps[marking] = self._steps(marking)
            for step in steps[marking]:
                queue.append((step.target, possible and step.possible))

        problems: list[SoundnessProblem] = []
        exploded = sorted(overflow & reachable)
        if exploded:
            problems.append(self._unbounded(exploded[0]))
        finishing = self._finishing(steps, {m for m in steps if not any(m)})
        stuck = [m for m in sorted(reachable) if m not in finishing and m not in overflow]
        deadlocks = [m for m in stuck if not steps[m]]
        if deadlocks:
            problems.append(self._deadlock(deadlocks))
        # Chi finisce comunque in un blocco o nel lavoro che si moltiplica e' gia' detto sopra.
        doomed = self._finishing(steps, set(deadlocks) | overflow)
        trapped = {m for m in stuck if steps[m] and m not in doomed}
        if trapped:
            problems.append(self._livelock(trapped, steps, finishing))
        expected = None
        if not problems and self.known_probabilities and len(initial) == 1:
            expected = self._expected(initial[0], steps, reachable)
        return SoundnessReport(problems=tuple(problems), states=len(steps), expected_executions=expected)

    def _finishing(self, steps: dict[Marking, list[_Step]], goals: set[Marking]) -> set[Marking]:
        """Gli stati da cui uno dei ``goals`` si raggiunge per rami possibili."""
        back: dict[Marking, list[Marking]] = defaultdict(list)
        for source, out in steps.items():
            for step in out:
                if step.possible:
                    back[step.target].append(source)
        done = set(goals)
        todo = list(done)
        while todo:
            for source in back[todo.pop()]:
                if source not in done:
                    done.add(source)
                    todo.append(source)
        return done

    def _expected(
        self, start: Marking, steps: dict[Marking, list[_Step]], reachable: set[Marking]
    ) -> dict[str, float]:
        """Esecuzioni attese per caso: visite attese a ogni stato (catena assorbente)."""
        visits = _expected_visits(
            start,
            {m: [(s.target, s.probability or 0.0) for s in steps[m] if s.possible] for m in reachable},
        )
        executions: dict[str, float] = defaultdict(float)
        for marking, times in visits.items():
            out = steps[marking]
            if out and self.graph.tags[out[0].node] in ACTIVITY_TAGS:
                executions[out[0].node] += times
        return dict(sorted(executions.items()))

    # ---- messaggi --------------------------------------------------------- #

    def _label(self, node: str) -> str:
        """Come il consulente riconosce un elemento: il nome, o l'attivita' che lo precede."""
        name = self.graph.names.get(node)
        tag = self.graph.tags.get(node, "")
        if name:
            return f"«{name}»"
        before = self._activity_before(node)
        if tag in _CHOICE_TAGS | _INCLUSIVE_TAGS:
            return f"la decisione dopo «{before}»" if before else "una decisione senza nome"
        if tag == "parallelGateway":
            return f"il punto di unione dopo «{before}»" if before else "un punto di unione senza nome"
        return f"«{before}»" if before else "un passo senza nome"

    def _activity_before(self, node: str) -> str | None:
        seen, todo = {node}, deque([node])
        while todo:
            current = todo.popleft()
            for flow in sorted(self.graph.incoming.get(current, [])):
                source = self.graph.flow_ends[flow][0]
                if self.graph.tags.get(source) in ACTIVITY_TAGS and self.graph.names.get(source):
                    return self.graph.names[source]
                if source not in seen:
                    seen.add(source)
                    todo.append(source)
        return None

    def _activity_after(self, flow: str) -> str | None:
        seen, todo = {flow}, deque([flow])
        while todo:
            target = self.graph.flow_ends[todo.popleft()][1]
            if self.graph.tags.get(target) in ACTIVITY_TAGS and self.graph.names.get(target):
                return self.graph.names[target]
            for nxt in sorted(self.graph.outgoing.get(target, [])):
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        return None

    def _waiting(self, marking: Marking) -> list[str]:
        return sorted({self.graph.flow_ends[self.flows[i]][1] for i, tokens in enumerate(marking) if tokens})

    def _deadlock(self, deadlocks: list[Marking]) -> SoundnessProblem:
        nodes = sorted({node for marking in deadlocks for node in self._waiting(marking)})
        joins = [node for node in nodes if self.graph.tags.get(node) in {"parallelGateway", *_INCLUSIVE_TAGS}]
        unknown = [node for node in nodes if node not in self.graph.tags]
        if joins:
            where = ", ".join(self._label(node) for node in joins)
            message = (
                f"Alcuni casi si bloccano a {where}: lì il processo aspetta che arrivino tutti i percorsi, "
                "ma una scelta precedente ne ha preso solo uno. Quei casi non finirebbero mai."
            )
            action = (
                "Se i percorsi sono alternativi, il punto di unione deve aspettarne uno solo: correggi il "
                "disegno del processo e importa di nuovo lo scenario."
            )
        else:
            message = (
                "Alcuni casi si fermano a metà: il percorso porta a un passo che la simulazione non sa eseguire, "
                "e quei casi non finirebbero mai."
            )
            action = "Collega il percorso a un'attività o alla fine del processo e importa di nuovo lo scenario."
        stuck = joins or unknown or nodes
        return SoundnessProblem(
            "deadlock", message, action, tuple(stuck), f"deadlock: gettoni fermi davanti a {', '.join(stuck)}"
        )

    def _livelock(
        self, trapped: set[Marking], steps: dict[Marking, list[_Step]], finishing: set[Marking]
    ) -> SoundnessProblem:
        # Le decisioni del tratto chiuso con un ramo a probabilita' 0 che porterebbe fuori.
        exits: dict[str, set[str]] = defaultdict(set)
        for marking in trapped:
            for step in steps[marking]:
                if not step.possible and step.via and step.target in finishing:
                    exits[step.node].add(step.via)
        loop = sorted({step.node for m in trapped for step in steps[m] if self.graph.tags.get(step.node) in ACTIVITY_TAGS})
        names = [self.graph.names[node] for node in loop if self.graph.names.get(node)]
        activities = ", ".join(f"«{name}»" for name in names[:3]) + (" e altre" if len(names) > 3 else "")
        if exits:
            gateway = sorted(exits)[0]
            before = self._activity_before(gateway)
            towards = self._activity_after(sorted(exits[gateway])[0])
            named = self.graph.names.get(gateway)
            if named:
                where = again = f"alla decisione «{named}»"
            else:
                where = f"dopo «{before}»" if before else self._label(gateway)
                again = "dopo quell'attività" if before in names[:3] else where
            exit_text = f" verso «{towards}»" if towards else ""
            message = (
                f"I casi che arrivano a {activities or where} non escono più da quel tratto: {again} il "
                f"processo li rimanda indietro ogni volta, perché la strada per proseguire{exit_text} ha "
                "probabilità 0. La simulazione ripeterebbe quel tratto all'infinito e i risultati non avrebbero senso."
            )
            action = (
                "Dai a quella strada una probabilità maggiore di zero (per esempio la quota di casi che nei dati "
                "va avanti dopo quell'attività) oppure rifai la scoperta del modello dal log, poi importa di nuovo "
                "lo scenario."
            )
            detail = "livelock: " + "; ".join(
                f"gateway {g}, rami a probabilità 0 che porterebbero alla fine: {', '.join(sorted(flows))}"
                for g, flows in sorted(exits.items())
            )
            return SoundnessProblem("livelock", message, action, tuple(sorted(exits)), detail)
        message = (
            f"I casi che arrivano a {activities or 'un tratto del processo'} non riescono più ad arrivare alla "
            "fine: il percorso gira in tondo senza un'uscita."
        )
        action = "Aggiungi o riapri un'uscita da quel tratto nel disegno del processo e importa di nuovo lo scenario."
        return SoundnessProblem(
            "livelock", message, action, tuple(loop), f"livelock: tratto chiuso su {', '.join(loop)}"
        )

    def _unbounded(self, marking: Marking) -> SoundnessProblem:
        flows = [self.flows[i] for i, tokens in enumerate(marking) if tokens > MAX_TOKENS_PER_FLOW]
        node = self.graph.flow_ends[flows[0]][1]
        message = (
            f"Il lavoro di un caso si moltiplica senza fine prima di {self._label(node)}: un tratto del processo "
            "apre percorsi in parallelo che non si ricongiungono e poi ripartono, così il caso non finisce."
        )
        action = "Ricongiungi i percorsi paralleli prima di tornare indietro e importa di nuovo lo scenario."
        return SoundnessProblem(
            "unbounded", message, action, tuple(flows), f"più di {MAX_TOKENS_PER_FLOW} gettoni su {', '.join(flows)}"
        )


def _may_take(weight: float | None) -> bool:
    """Un ramo si puo' prendere se la sua probabilita' e' sconosciuta o positiva."""
    return weight is None or weight > 0


# --------------------------------------------------------------------------- #
# Catena assorbente
# --------------------------------------------------------------------------- #


def _expected_visits(
    start: Marking, transitions: dict[Marking, list[tuple[Marking, float]]]
) -> dict[Marking, float]:
    """Visite attese a ogni stato partendo da ``start``.

    v = e_start + v·Q. Si risolve una componente fortemente connessa alla volta,
    in ordine topologico: dentro una componente (un ciclo) con l'eliminazione di
    Gauss, perche' la catena e' assorbente e (I - Q) e' invertibile.
    """
    components = _components(transitions)
    inflow: dict[Marking, float] = defaultdict(float)
    inflow[start] = 1.0
    visits: dict[Marking, float] = {}
    for component in components:
        members = sorted(component)
        position = {m: i for i, m in enumerate(members)}
        size = len(members)
        # (I - Q_cc)^T v = b
        matrix = [[0.0] * size for _ in range(size)]
        for i in range(size):
            matrix[i][i] = 1.0
        for source in members:
            for target, probability in transitions.get(source, []):
                if target in position:
                    matrix[position[target]][position[source]] -= probability
        solution = _solve(matrix, [inflow[m] for m in members])
        for member, value in zip(members, solution, strict=True):
            visits[member] = value
            for target, probability in transitions.get(member, []):
                if target not in position:
                    inflow[target] += value * probability
    return visits


def _components(graph: dict[Marking, list[tuple[Marking, float]]]) -> list[set[Marking]]:
    """Componenti fortemente connesse in ordine topologico (Tarjan, iterativo)."""
    index: dict[Marking, int] = {}
    low: dict[Marking, int] = {}
    on_stack: set[Marking] = set()
    stack: list[Marking] = []
    result: list[set[Marking]] = []
    counter = 0
    for root in sorted(graph):
        if root in index:
            continue
        work = [(root, iter([t for t, _ in graph.get(root, [])]))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in graph:
                    continue
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter([t for t, _ in graph.get(child, [])])))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component: set[Marking] = set()
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.add(member)
                    if member == node:
                        break
                result.append(component)
    # Tarjan restituisce le componenti in ordine topologico inverso.
    return result[::-1]


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Eliminazione di Gauss con pivot parziale (sistemi piccoli: un ciclo alla volta)."""
    size = len(rhs)
    rows = [row[:] + [value] for row, value in zip(matrix, rhs, strict=True)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda r: abs(rows[r][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        head = rows[column][column]
        for r in range(column + 1, size):
            factor = rows[r][column] / head
            if factor:
                for c in range(column, size + 1):
                    rows[r][c] -= factor * rows[column][c]
    solution = [0.0] * size
    for r in range(size - 1, -1, -1):
        total = rows[r][size] - sum(rows[r][c] * solution[c] for c in range(r + 1, size))
        solution[r] = total / rows[r][r]
    return solution
