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
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from itertools import combinations, product
from typing import Literal

from defusedxml import ElementTree

from backend.simulation.flow_graph import ACTIVITY_TAGS
from backend.simulation.ir.model import Gateway, SimulationModel

ProblemKind = Literal["no_start", "deadlock", "livelock", "unbounded"]

_CHOICE_TAGS = frozenset({"exclusiveGateway", "eventBasedGateway"})
_INCLUSIVE_TAGS = frozenset({"inclusiveGateway", "complexGateway"})

# Oltre questi limiti la verifica si ferma e lo dice: un flusso con piu' gettoni
# e' lavoro che si moltiplica; troppi stati non si verificano in un import.
MAX_TOKENS_PER_FLOW = 8
MAX_STATES = 50_000
# Rami di un'unica decisione inclusiva, ed esiti combinati di un passo, oltre i
# quali non si elencano le combinazioni: la verifica si ferma e lo dice.
_MAX_INCLUSIVE_BRANCHES = 10
_MAX_COMBINATIONS = 4096

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
class _Outcome:
    """Un esito possibile di un elemento che scatta: i flussi su cui mette un gettone."""

    add: tuple[str, ...]
    probability: float | None  # None: possibile, probabilita' sconosciuta
    via: str | None = None  # il ramo di una decisione
    terminate: bool = False

    @property
    def possible(self) -> bool:
        return _may_take(self.probability)


@dataclass(frozen=True, slots=True)
class _Step:
    """Un passo: gli elementi scattati insieme, lo stato dopo, la probabilita'."""

    fired: tuple[str, ...]
    target: Marking
    probability: float | None
    # Le decisioni che in questo passo prendono un ramo a probabilita' 0, con il ramo.
    zero: tuple[tuple[str, str], ...] = ()

    @property
    def possible(self) -> bool:
        return not self.zero


class UnsoundProcessError(Exception):
    """Con le sue probabilita' qualche caso del modello non finirebbe: non si simula.

    Non e' un ``ValueError``: le route che trasformano i ``ValueError`` in un 400
    generico la lasciano passare al gestore comune (``backend/api/errors.py``), che
    risponde con il codice stabile ``process_cannot_finish`` su import e run.
    """

    def __init__(self, problems: tuple[SoundnessProblem, ...]) -> None:
        self.problems = problems
        # Un paragrafo per cosa non torna, uno per cosa fare: la UI li tiene separati.
        super().__init__(
            "\n\n".join(f"{p.message}\nCosa fare: {p.action[:1].lower()}{p.action[1:]}" for p in problems)
        )

    @property
    def detail(self) -> str:
        """Per specialisti: la regola violata e gli id del BPMN."""
        return "; ".join(p.detail for p in self.problems)


def require_sound(model: SimulationModel, bpmn_xml: str) -> SoundnessReport:
    """Il rapporto di ``check_soundness``; solleva ``UnsoundProcessError`` se qualche caso non finirebbe."""
    report = check_soundness(model, bpmn_xml)
    if report.problems:
        raise UnsoundProcessError(report.problems)
    return report


class _TooLarge(Exception):
    """Lo spazio degli stati supera i limiti di un import: la verifica si ferma."""


def check_soundness(model: SimulationModel, bpmn_xml: str, *, expected: bool = False) -> SoundnessReport:
    """La verifica di VAL-01 del modello ``model`` sul BPMN che il motore eseguira'.

    Con ``expected`` calcola anche le esecuzioni attese di ogni attivita' per caso.
    """
    graph = _read(bpmn_xml)
    return _Checker(graph, {gateway.element_id: gateway for gateway in model.gateways}).run(expected=expected)


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
        # A ogni passo scattano tutti gli elementi abilitati (passo massimo).
        self.nodes = sorted(node for node in graph.tags if graph.incoming.get(node))
        self.known_probabilities = True
        self.inputs = {node: tuple(self.index[f] for f in graph.incoming[node]) for node in self.nodes}
        self._upstream: dict[tuple[int, str], set[int]] = {}
        self._outcome_cache: dict[str, list[_Outcome]] = {}

    # ---- regole di scatto ------------------------------------------------- #

    def _put(self, marking: list[int], flows: Iterable[str]) -> None:
        for flow in flows:
            marking[self.index[flow]] += 1

    def _enabled(self, node: str, marking: Marking) -> int | None:
        """L'indice del flusso da cui ``node`` prende il gettone, -1 se li prende tutti."""
        inputs = self.inputs[node]
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
        inputs = set(self.inputs[node])
        empty = {i for i in inputs if not marking[i]}
        for i, tokens in enumerate(marking):
            if tokens and i not in inputs and self._reaches(i, node) & empty:
                return False
        return True

    def _reaches(self, flow: int, join: str) -> set[int]:
        """Gli ingressi di ``join`` che un gettone su ``flow`` puo' raggiungere senza attraversarlo."""
        key = (flow, join)
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
            self._upstream[key] = seen & set(self.inputs[join])
        return self._upstream[key]

    def _outputs(self, node: str) -> list[str]:
        flows = list(self.graph.outgoing.get(node, ()))
        for boundary, _ in self.graph.boundary.get(node, ()):
            flows += self.graph.outgoing.get(boundary, [])
        return flows

    def _steps(self, marking: Marking) -> list[_Step]:
        """Il passo massimo da ``marking``: un passo per ogni combinazione di esiti."""
        after = list(marking)
        fired: list[str] = []
        options: list[list[_Outcome]] = []
        size = 1
        for node in self.nodes:
            taken = self._enabled(node, marking)
            if taken is None:
                continue
            for i in self.inputs[node] if taken == -1 else [taken]:
                after[i] -= 1
            outcomes = self._outcomes(node)
            fired.append(node)
            options.append(outcomes)
            size *= len(outcomes)
            if size > _MAX_COMBINATIONS:
                raise _TooLarge
        if not fired:
            return []
        steps = []
        for combo in product(*options):
            target = list(after)
            probability: float | None = 1.0
            for outcome in combo:
                self._put(target, outcome.add)
                probability = None if probability is None or outcome.probability is None else probability * outcome.probability
            if any(outcome.terminate for outcome in combo):
                target = [0] * len(target)
            zero = tuple((node, o.via or "") for node, o in zip(fired, combo, strict=True) if not o.possible)
            steps.append(_Step(tuple(fired), tuple(target), probability, zero))
        return steps

    def _outcomes(self, node: str) -> list[_Outcome]:
        """Gli esiti di ``node``: non dipendono dallo stato, si calcolano una volta."""
        if node not in self._outcome_cache:
            self._outcome_cache[node] = self._compute_outcomes(node)
        return self._outcome_cache[node]

    def _compute_outcomes(self, node: str) -> list[_Outcome]:
        tag = self.graph.tags[node]
        outgoing = self.graph.outgoing.get(node, [])
        if tag == "endEvent":
            return [_Outcome((), 1.0, terminate=node in self.graph.terminate)]
        if tag in _CHOICE_TAGS and len(outgoing) > 1:
            weights = self._weights(node, outgoing)
            return [
                _Outcome((flow,), weights[flow], via=flow) for flow in outgoing
            ]
        if tag in _INCLUSIVE_TAGS and len(outgoing) > 1:
            return self._inclusive(node, outgoing)
        boundaries = self.graph.boundary.get(node, [])
        if not boundaries:
            return [_Outcome(tuple(outgoing), 1.0)]
        # Un evento di bordo e' un'altra fine possibile dell'attivita': senza
        # probabilita' nell'IR, ogni esito e' possibile.
        self.known_probabilities = False
        outcomes = [_Outcome(tuple(outgoing), None)]
        for boundary, interrupting in boundaries:
            extra = tuple(self.graph.outgoing.get(boundary, []))
            outcomes.append(_Outcome(extra if interrupting else (*outgoing, *extra), None, via=boundary))
        return outcomes

    def _inclusive(self, node: str, outgoing: list[str]) -> list[_Outcome]:
        # Prosimos non documenta come combina i rami di un'inclusiva: ogni
        # combinazione non vuota dei rami possibili e' possibile.
        self.known_probabilities = False
        weights = self._weights(node, outgoing)
        possible = [flow for flow in outgoing if _may_take(weights[flow])]
        if len(possible) > _MAX_INCLUSIVE_BRANCHES:
            raise _TooLarge
        outcomes = [
            _Outcome(chosen, None, via=",".join(chosen))
            for size in range(1, len(possible) + 1)
            for chosen in combinations(possible, size)
        ]
        outcomes += [_Outcome((flow,), 0.0, via=flow) for flow in outgoing if flow not in possible]
        return outcomes

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

    def run(self, *, expected: bool = False) -> SoundnessReport:
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
        complete = True
        try:
            while queue:
                marking, possible = queue.popleft()
                if marking in (reachable if possible else steps):
                    continue
                if marking not in steps:
                    if len(steps) >= MAX_STATES:
                        raise _TooLarge
                    if max(marking, default=0) > MAX_TOKENS_PER_FLOW:
                        overflow.add(marking)
                        steps[marking] = []
                    else:
                        steps[marking] = self._steps(marking)
                if possible:
                    reachable.add(marking)
                for step in steps[marking]:
                    follow = possible and step.possible
                    if step.target not in (reachable if follow else steps):
                        queue.append((step.target, follow))
        except _TooLarge:
            complete = False

        problems: list[SoundnessProblem] = []
        if overflow & reachable:
            problems.append(self._unbounded(min(overflow & reachable)))
        # Uno stato con lavoro aperto e nessun passo e' un blocco anche se la
        # verifica si e' fermata prima della fine.
        deadlocks = sorted(m for m in reachable if any(m) and not steps[m] and m not in overflow)
        if deadlocks:
            problems.append(self._deadlock(deadlocks))
        if not complete:
            return SoundnessReport(problems=tuple(problems), states=len(steps), complete=False)
        back = _backward(steps)
        finishing = _reaching(back, {m for m in steps if not any(m)})
        # Chi finisce comunque in un blocco o nel lavoro che si moltiplica e' gia' detto sopra.
        doomed = _reaching(back, set(deadlocks) | overflow)
        trapped = {m for m in reachable if m not in finishing and m not in doomed}
        if trapped:
            problems.append(self._livelock(trapped, steps, finishing))
        executions = None
        if expected and not problems and self.known_probabilities and len(initial) == 1:
            executions = self._expected(initial[0], steps, reachable)
        return SoundnessReport(problems=tuple(problems), states=len(steps), expected_executions=executions)

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
            # Ogni passo da uno stato fa scattare gli stessi elementi: cambia solo il ramo preso.
            for node in steps[marking][0].fired if steps[marking] else ():
                if self.graph.tags[node] in ACTIVITY_TAGS:
                    executions[node] += times
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
        """La prima attivita' con un nome risalendo i flussi da ``node``."""
        return self._nearest_activity(node, lambda n: self.graph.incoming.get(n, []), 0)

    def _activity_after(self, flow: str) -> str | None:
        """La prima attivita' con un nome seguendo ``flow``."""
        target = self.graph.flow_ends[flow][1]
        if self.graph.tags.get(target) in ACTIVITY_TAGS and self.graph.names.get(target):
            return self.graph.names[target]
        return self._nearest_activity(target, lambda n: self.graph.outgoing.get(n, []), 1)

    def _nearest_activity(self, start: str, flows: Callable[[str], list[str]], end: int) -> str | None:
        """Ricerca in ampiezza della prima attivita' con un nome; ``end`` 0 risale, 1 scende."""
        seen, todo = {start}, deque([start])
        while todo:
            for flow in sorted(flows(todo.popleft())):
                node = self.graph.flow_ends[flow][end]
                if self.graph.tags.get(node) in ACTIVITY_TAGS and self.graph.names.get(node):
                    return self.graph.names[node]
                if node not in seen:
                    seen.add(node)
                    todo.append(node)
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
                if step.target in finishing:
                    for gateway, branch in step.zero:
                        exits[gateway].add(branch)
        loop = sorted(
            {node for m in trapped for step in steps[m] for node in step.fired if self.graph.tags.get(node) in ACTIVITY_TAGS}
        )
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
                "Dai a quella strada una probabilità maggiore di zero (per esempio la quota di casi che nella realtà "
                "va avanti dopo quell'attività) oppure ricalcola il modello dai dati storici del processo, poi "
                "importa di nuovo lo scenario."
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


def _backward(steps: dict[Marking, list[_Step]]) -> dict[Marking, list[Marking]]:
    """Per ogni stato, gli stati da cui ci si arriva con un passo possibile."""
    back: dict[Marking, list[Marking]] = defaultdict(list)
    for source, out in steps.items():
        for step in out:
            if step.possible:
                back[step.target].append(source)
    return back


def _reaching(back: dict[Marking, list[Marking]], goals: set[Marking]) -> set[Marking]:
    """Gli stati da cui uno dei ``goals`` si raggiunge per passi possibili."""
    done = set(goals)
    todo = list(done)
    while todo:
        for source in back.get(todo.pop(), ()):
            if source not in done:
                done.add(source)
                todo.append(source)
    return done


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
        matrix = [[float(i == j) for j in range(size)] for i in range(size)]
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
