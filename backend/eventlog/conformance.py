"""Conformance delle esecuzioni: il log reale contro il comportamento del BPMN.

Perche' esiste. ``bpmn_match`` dice quali attivita' del log hanno un elemento nel
modello; ``agents/conformance_audit`` dice se il modello e' coerente con le fonti.
Nessuno dei due risponde alla domanda del consulente davanti al process owner:
*i casi reali seguono il processo disegnato? quanti no, e dove escono di strada?*

Il metodo e' il token-based replay (Rozinat e van der Aalst, 2008). Il BPMN
diventa una rete di Petri:

- ogni sequence flow e' un posto;
- ogni attivita' e' una transizione con etichetta (l'``element_id``); piu' flussi
  in ingresso sono un merge esclusivo implicito, piu' flussi in uscita uno split
  parallelo implicito, come vuole la semantica BPMN;
- gateway ed eventi sono transizioni silenti: esclusivo ed event-based una per
  ramo, parallelo una sola, inclusivo una per sottoinsieme non vuoto di rami;
- un boundary event e' una transizione silente che prende il posto
  dell'attivita' a cui e' attaccato (interrompente) o la affianca (no).

Ogni variante del log si riproduce sulla rete. Quando l'attivita' successiva non
e' abilitata si cerca la sequenza piu' corta di transizioni silenti che la
abilita (BFS sulle marcature, con un tetto). Se non esiste, l'attivita' scatta
lo stesso e i token che mancavano si contano come *mancanti*: l'attivita' e'
stata eseguita senza che il modello lo consentisse. A fine traccia i token che
restano fuori dalla fine sono *rimanenti*: il modello aspettava ancora qualcosa
che non e' successo (un'approvazione saltata, un ramo parallelo non chiuso).

    fitness = 1/2 (1 - mancanti/consumati) + 1/2 (1 - rimanenti/prodotti)

Limiti dichiarati, da non nascondere a chi legge il risultato:

- e' controllo del flusso, non dei dati: «ordini sopra 30.000 EUR passano dal
  CFO» si verifica solo se il modello ha un ramo per il CFO e il log mostra il
  caso uscire dall'altro ramo senza la condizione; la condizione sul valore non
  e' valutata;
- il join inclusivo e' approssimato (si preferisce il sottoinsieme piu' grande
  disponibile): un modello con inclusivi annidati puo' avere fitness leggermente
  pessimista;
- un sottoprocesso conta come attivita' atomica;
- un caso ancora aperto ha token rimanenti per costruzione: chi analizza un log
  estratto a meta' periodo filtra prima i casi completi.

Il risultato non e' un allineamento ottimo (A*): e' la stima classica, veloce e
spiegabile. L'allineamento resta il passo successivo se servira' la sequenza
minima di correzioni per ogni caso.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from itertools import combinations
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from backend.eventlog.model import EventLog

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
        "transaction",
        "adHocSubProcess",
    }
)
XOR_GATEWAYS = frozenset({"exclusiveGateway", "eventBasedGateway", "complexGateway"})
SILENT_EVENTS = frozenset(
    {"intermediateCatchEvent", "intermediateThrowEvent", "implicitThrowEvent"}
)

SOURCE = "source"
SINK = "sink"

#: Oltre questo numero di rami un gateway inclusivo non si espande in sottoinsiemi
#: (2^n transizioni): si tratta come esclusivo e lo si segnala nel risultato.
MAX_INCLUSIVE_BRANCHES = 6
#: Tetto della ricerca di transizioni silenti, per traccia e per passo.
MAX_SEARCH_STATES = 4_000
MAX_SEARCH_DEPTH = 24
#: Le varianti piu' frequenti che si riproducono; le altre si contano come escluse.
DEFAULT_MAX_VARIANTS = 2_000


@dataclass(frozen=True, slots=True)
class ConformanceWarning:
    """Un avviso con un codice stabile: il testo lo scrive chi lo mostra, nella sua lingua.

    Codici: ``multiple_processes`` (``count``), ``boundary_without_host``,
    ``inclusive_as_exclusive``, ``silent_node`` (``element``, ``kind``),
    ``mapped_to_non_activity`` (``activities``), ``variants_truncated``
    (``kept``, ``dropped``).
    """

    code: str
    params: dict[str, str | int] = field(default_factory=dict)


class ConformanceModelError(ValueError):
    """Il BPMN non si puo' trasformare in una rete da riprodurre."""


@dataclass(frozen=True, slots=True)
class Transition:
    id: str
    #: L'elemento BPMN dell'attivita'; ``None`` per una transizione silente.
    element_id: str | None
    consume: tuple[str, ...]
    produce: tuple[str, ...]


@dataclass(slots=True)
class PetriNet:
    transitions: list[Transition]
    initial: Counter[str]
    #: Il nome leggibile di ogni nodo BPMN, per il report.
    names: dict[str, str]
    #: Per ogni posto, l'elemento BPMN che aspetta il token.
    waiting_element: dict[str, str]
    warnings: list[ConformanceWarning] = field(default_factory=list)
    by_element: dict[str, list[Transition]] = field(default_factory=dict)
    silent_by_place: dict[str, list[Transition]] = field(default_factory=dict)
    #: Per ogni posto, le attivita' raggiungibili passando solo da transizioni
    #: silenti: dice quale ramo di uno split serve al resto della traccia.
    reachable_activities: dict[str, frozenset[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for transition in self.transitions:
            if transition.element_id is not None:
                self.by_element.setdefault(transition.element_id, []).append(transition)
                continue
            for place in set(transition.consume):
                self.silent_by_place.setdefault(place, []).append(transition)
        # A parita' di profondita' la BFS prova prima chi consuma di piu': un join
        # inclusivo con due rami arrivati scatta su entrambi, non su uno solo.
        for candidates in self.silent_by_place.values():
            candidates.sort(key=lambda item: -len(item.consume))
        consumers: dict[str, list[Transition]] = {}
        for transition in self.transitions:
            for place in set(transition.consume):
                consumers.setdefault(place, []).append(transition)
        for place in {p for t in self.transitions for p in (*t.consume, *t.produce)}:
            found: set[str] = set()
            seen = {place}
            stack = [place]
            while stack:
                for transition in consumers.get(stack.pop(), ()):
                    if transition.element_id is not None:
                        found.add(transition.element_id)
                        continue
                    for produced in transition.produce:
                        if produced not in seen:
                            seen.add(produced)
                            stack.append(produced)
            self.reachable_activities[place] = frozenset(found)

    def ranked(self, transitions: list[Transition], future: frozenset[str]) -> list[Transition]:
        """Prima i join piu' larghi, poi gli split che aprono solo rami utili.

        Un ramo e' utile se porta a un'attivita' che il resto della traccia
        esegue. Senza questa preferenza uno split inclusivo aprirebbe sempre
        tutti i rami, e quelli mai percorsi resterebbero come token rimanenti.
        """

        def key(transition: Transition) -> tuple[int, int, int]:
            useful = sum(1 for p in transition.produce if self.reachable_activities.get(p, frozenset()) & future)
            return (-len(transition.consume), -useful, len(transition.produce) - useful)

        return sorted(transitions, key=key)

    @property
    def activities(self) -> list[str]:
        return sorted(self.by_element)


@dataclass(frozen=True, slots=True)
class ElementDeviation:
    element_id: str
    name: str
    #: Casi in cui l'attivita' e' stata eseguita senza essere abilitata.
    executed_out_of_order: int
    #: Casi finiti con il modello ancora in attesa di questo elemento.
    left_waiting: int
    #: Casi distinti con almeno una delle due deviazioni su questo elemento.
    cases_affected: int


@dataclass(frozen=True, slots=True)
class VariantConformance:
    activities: tuple[str, ...]
    cases: int
    fitness: float
    produced: int
    consumed: int
    missing: int
    remaining: int
    #: Elementi eseguiti senza essere abilitati, nell'ordine della traccia.
    out_of_order: tuple[str, ...]
    #: Elementi che il modello aspettava ancora a fine caso.
    waiting: tuple[str, ...]
    #: Attivita' del log senza elemento nel modello: saltate nel replay.
    unmodeled: tuple[str, ...]

    @property
    def fits(self) -> bool:
        return self.missing == 0 and self.remaining == 0 and not self.unmodeled


@dataclass(frozen=True, slots=True)
class ConformanceResult:
    fitness: float
    cases: int
    fitting_cases: int
    variants: tuple[VariantConformance, ...]
    deviations: tuple[ElementDeviation, ...]
    #: Attivita' del log senza elemento nel modello, con il numero di casi.
    unmodeled_activities: dict[str, int]
    #: Attivita' del modello che nessun caso replicato ha eseguito.
    unobserved_elements: tuple[str, ...]
    excluded_variants: int
    excluded_cases: int
    warnings: tuple[ConformanceWarning, ...]

    @property
    def fitting_share(self) -> float:
        return self.fitting_cases / self.cases if self.cases else 0.0


# ---------------------------------------------------------------------------
# BPMN -> rete di Petri
# ---------------------------------------------------------------------------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


@dataclass(slots=True)
class _ProcessGraph:
    nodes: dict[str, Element]
    incoming: dict[str, list[str]]
    outgoing: dict[str, list[str]]
    flow_target: dict[str, str]


def _processes(root: Element) -> list[_ProcessGraph]:
    graphs: list[_ProcessGraph] = []
    for process in root.iter():
        if _local(process.tag) != "process":
            continue
        nodes: dict[str, Element] = {}
        flows: list[tuple[str, str, str]] = []
        for child in process:
            tag = _local(child.tag)
            node_id = child.attrib.get("id")
            if not node_id:
                continue
            if tag == "sequenceFlow":
                source = child.attrib.get("sourceRef") or ""
                target = child.attrib.get("targetRef") or ""
                if source and target:
                    flows.append((node_id, source, target))
            elif tag in ACTIVITY_TAGS or tag.endswith("Gateway") or tag.endswith("Event"):
                nodes[node_id] = child
        graph = _ProcessGraph(nodes, {}, {}, {})
        for flow_id, source, target in flows:
            if source in nodes and target in nodes:
                graph.outgoing.setdefault(source, []).append(flow_id)
                graph.incoming.setdefault(target, []).append(flow_id)
                graph.flow_target[flow_id] = target
        if nodes:
            graphs.append(graph)
    return graphs


def _subsets(items: list[str]) -> list[tuple[str, ...]]:
    return [
        subset
        for size in range(len(items), 0, -1)
        for subset in combinations(items, size)
    ]


def build_petri_net(bpmn_xml: str, *, relevant_elements: Iterable[str] = ()) -> PetriNet:
    """La rete di Petri del BPMN.

    Con piu' processi (una collaborazione) si riproduce solo quello che contiene
    piu' elementi di ``relevant_elements`` - le attivita' abbinate al log - o,
    senza abbinamenti, quello con piu' attivita'. Un caso del log vive in un
    processo solo.

    Raises:
        ConformanceModelError: XML non leggibile o nessun processo con nodi.
    """
    try:
        root = ElementTree.fromstring(bpmn_xml.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise ConformanceModelError(f"BPMN non leggibile: {exc}") from exc
    graphs = _processes(root)
    if not graphs:
        raise ConformanceModelError("Il BPMN non contiene un processo con nodi.")

    relevant = set(relevant_elements)

    def score(graph: _ProcessGraph) -> tuple[int, int]:
        activities = [n for n, el in graph.nodes.items() if _local(el.tag) in ACTIVITY_TAGS]
        return (len(relevant.intersection(activities)), len(activities))

    graph = max(graphs, key=score)
    warnings: list[ConformanceWarning] = []
    if len(graphs) > 1:
        warnings.append(ConformanceWarning("multiple_processes", {"count": len(graphs)}))

    transitions: list[Transition] = []
    names: dict[str, str] = {}
    waiting: dict[str, str] = {}

    def flow_place(flow_id: str) -> str:
        place = f"flow:{flow_id}"
        waiting[place] = graph.flow_target[flow_id]
        return place

    def silent(tid: str, consume: Iterable[str], produce: Iterable[str]) -> None:
        transitions.append(Transition(tid, None, tuple(consume), tuple(produce)))

    def merged_input(node_id: str, kind: str) -> str:
        """Il posto da cui il nodo consuma: i flussi in ingresso si fondono (XOR)."""
        incoming = graph.incoming.get(node_id, [])
        if not incoming:
            return SOURCE
        if len(incoming) == 1:
            return flow_place(incoming[0])
        place = f"{kind}:{node_id}"
        waiting[place] = node_id
        for flow_id in incoming:
            silent(f"merge:{node_id}:{flow_id}", [flow_place(flow_id)], [place])
        return place

    def outputs(node_id: str) -> list[str]:
        out = [flow_place(f) for f in graph.outgoing.get(node_id, [])]
        return out or [SINK]

    input_place: dict[str, str] = {}
    for node_id, element in graph.nodes.items():
        tag = _local(element.tag)
        names[node_id] = (element.attrib.get("name") or "").strip() or node_id
        if tag in ACTIVITY_TAGS:
            place = merged_input(node_id, "in")
            input_place[node_id] = place
            transitions.append(Transition(f"act:{node_id}", node_id, (place,), tuple(outputs(node_id))))

    for node_id, element in graph.nodes.items():
        tag = _local(element.tag)
        if tag in ACTIVITY_TAGS:
            continue
        incoming = graph.incoming.get(node_id, [])
        out = outputs(node_id)
        if tag == "boundaryEvent":
            attached = element.attrib.get("attachedToRef") or ""
            if attached not in input_place:
                warnings.append(ConformanceWarning("boundary_without_host", {"element": names[node_id]}))
                continue
            host = input_place[attached]
            interrupting = (element.attrib.get("cancelActivity") or "true").lower() != "false"
            produce = out if interrupting else [host, *out]
            silent(f"boundary:{node_id}", [host], produce)
        elif tag == "parallelGateway":
            consume = [flow_place(f) for f in incoming] or [SOURCE]
            silent(f"and:{node_id}", consume, out)
        elif tag == "inclusiveGateway":
            ins = [flow_place(f) for f in incoming] or [SOURCE]
            if len(ins) > MAX_INCLUSIVE_BRANCHES or len(out) > MAX_INCLUSIVE_BRANCHES:
                warnings.append(
                    ConformanceWarning(
                        "inclusive_as_exclusive", {"element": names[node_id], "branches": MAX_INCLUSIVE_BRANCHES}
                    )
                )
                hub = merged_input(node_id, "or")
                for index, place in enumerate(out):
                    silent(f"or:{node_id}:{index}", [hub], [place])
                continue
            hub = f"or:{node_id}"
            waiting[hub] = node_id
            for index, subset in enumerate(_subsets(ins)):
                silent(f"or-join:{node_id}:{index}", subset, [hub])
            for index, subset in enumerate(_subsets(out)):
                silent(f"or-split:{node_id}:{index}", [hub], subset)
        else:
            # Gateway esclusivi/event-based/complessi, eventi di inizio, fine e
            # intermedi: consumano un token da un ingresso qualunque.
            hub = merged_input(node_id, "xor")
            if tag in XOR_GATEWAYS and len(out) > 1:
                for index, place in enumerate(out):
                    silent(f"xor:{node_id}:{index}", [hub], [place])
            else:
                if tag not in XOR_GATEWAYS and tag not in SILENT_EVENTS and tag not in {
                    "startEvent",
                    "endEvent",
                }:
                    warnings.append(ConformanceWarning("silent_node", {"element": names[node_id], "kind": tag}))
                silent(f"pass:{node_id}", [hub], out)

    if not any(t.element_id for t in transitions):
        raise ConformanceModelError("Il processo non contiene attivita' da confrontare con il log.")
    return PetriNet(transitions, Counter({SOURCE: 1}), names, waiting, warnings)


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

Marking = Counter[str]


def _enabled(transition: Transition, marking: Marking) -> bool:
    need = Counter(transition.consume)
    return all(marking[place] >= count for place, count in need.items())


def _fire(transition: Transition, marking: Marking) -> None:
    for place in transition.consume:
        marking[place] -= 1
        if not marking[place]:
            del marking[place]
    for place in transition.produce:
        marking[place] += 1


def _key(marking: Marking) -> tuple[tuple[str, int], ...]:
    return tuple(sorted((p, c) for p, c in marking.items() if c))


def _silent_path(
    net: PetriNet,
    marking: Marking,
    goal: Callable[[Marking], bool],
    future: frozenset[str] = frozenset(),
) -> list[Transition] | None:
    """La sequenza piu' corta di transizioni silenti che porta a ``goal``."""
    if goal(marking):
        return []
    start = Counter(marking)
    seen = {_key(start)}
    queue: deque[tuple[Marking, list[Transition]]] = deque([(start, [])])
    while queue and len(seen) < MAX_SEARCH_STATES:
        current, path = queue.popleft()
        if len(path) >= MAX_SEARCH_DEPTH:
            continue
        candidates = {
            transition.id: transition
            for place in current
            for transition in net.silent_by_place.get(place, ())
            if _enabled(transition, current)
        }
        for transition in net.ranked(list(candidates.values()), future):
                following = Counter(current)
                _fire(transition, following)
                key = _key(following)
                if key in seen:
                    continue
                seen.add(key)
                step = [*path, transition]
                if goal(following):
                    return step
                queue.append((following, step))
    return None


@dataclass(slots=True)
class _Tally:
    produced: int = 0
    consumed: int = 0
    missing: int = 0

    def fire(self, transition: Transition, marking: Marking) -> None:
        self.consumed += len(transition.consume)
        self.produced += len(transition.produce)
        _fire(transition, marking)


def _enables_any(candidates: list[Transition]) -> Callable[[Marking], bool]:
    def goal(marking: Marking) -> bool:
        return any(_enabled(transition, marking) for transition in candidates)

    return goal


def replay_trace(net: PetriNet, elements: list[str]) -> tuple[_Tally, list[str], Marking]:
    """Riproduce una sequenza di ``element_id``. Restituisce conteggi, elementi
    eseguiti fuori ordine e la marcatura finale (prima del consumo della fine)."""
    marking: Marking = Counter(net.initial)
    tally = _Tally(produced=sum(net.initial.values()))
    out_of_order: list[str] = []

    for index, element in enumerate(elements):
        candidates = net.by_element[element]
        chosen = next((t for t in candidates if _enabled(t, marking)), None)
        if chosen is None:
            path = _silent_path(
                net, marking, _enables_any(candidates), frozenset(elements[index:])
            )
            if path is not None:
                for transition in path:
                    tally.fire(transition, marking)
                chosen = next(t for t in candidates if _enabled(t, marking))
        if chosen is None:
            chosen = candidates[0]
            for place, count in Counter(chosen.consume).items():
                lacking = count - marking[place]
                if lacking > 0:
                    tally.missing += lacking
                    marking[place] += lacking
            out_of_order.append(element)
        tally.fire(chosen, marking)

    def only_sink(m: Marking) -> bool:
        return m[SINK] > 0 and all(p == SINK for p, c in m.items() if c)

    path = _silent_path(net, marking, only_sink)
    if path is None:
        path = _silent_path(net, marking, lambda m: m[SINK] > 0) or []
    for transition in path:
        tally.fire(transition, marking)
    return tally, out_of_order, marking


def _fitness(produced: int, consumed: int, missing: int, remaining: int) -> float:
    if not produced or not consumed:
        return 0.0
    value = 0.5 * (1 - missing / consumed) + 0.5 * (1 - remaining / produced)
    return max(0.0, min(1.0, value))


def check_conformance(
    log: EventLog,
    bpmn_xml: str,
    mapping: Mapping[str, str | None],
    *,
    max_variants: int = DEFAULT_MAX_VARIANTS,
) -> ConformanceResult:
    """Confronta i casi del log con il comportamento consentito dal BPMN.

    Args:
        log: L'event log canonico.
        bpmn_xml: Il modello.
        mapping: Attivita' del log -> ``element_id`` del BPMN, quella confermata
            dal consulente (``bpmn_match``). Un'attivita' assente o a ``None`` e'
            fuori modello: si conta e si salta nel replay.
        max_variants: Le varianti piu' frequenti da riprodurre.

    Raises:
        ConformanceModelError: Se il BPMN non si puo' riprodurre.
    """
    net = build_petri_net(bpmn_xml, relevant_elements=(v for v in mapping.values() if v))
    known = set(net.by_element)

    variants: Counter[tuple[str, ...]] = Counter(
        tuple(event.activity for event in events) for events in log.cases().values()
    )
    ordered = variants.most_common()
    kept, dropped = ordered[:max_variants], ordered[max_variants:]

    results: list[VariantConformance] = []
    unmodeled_cases: Counter[str] = Counter()
    out_of_order_cases: Counter[str] = Counter()
    waiting_cases: Counter[str] = Counter()
    affected_cases: Counter[str] = Counter()
    observed: set[str] = set()
    totals = [0, 0, 0, 0]
    fitting = 0
    warnings = list(net.warnings)
    off_process = sorted(activity for activity, element in mapping.items() if element and element not in known)
    if off_process:
        warnings.append(ConformanceWarning("mapped_to_non_activity", {"activities": ", ".join(off_process)}))

    for activities, cases in kept:
        elements: list[str] = []
        unmodeled: list[str] = []
        for activity in activities:
            element = mapping.get(activity)
            if element and element in known:
                elements.append(element)
            elif activity not in unmodeled:
                unmodeled.append(activity)
        observed.update(elements)
        tally, out_of_order, final = replay_trace(net, elements)
        consumed = tally.consumed + max(final[SINK], 1)
        missing = tally.missing + (0 if final[SINK] else 1)
        remaining_places = [p for p, c in final.items() if c and p != SINK for _ in range(c)]
        remaining = len(remaining_places)
        waiting_elements = tuple(dict.fromkeys(net.waiting_element.get(p, p) for p in remaining_places))

        variant = VariantConformance(
            activities=activities,
            cases=cases,
            fitness=_fitness(tally.produced, consumed, missing, remaining),
            produced=tally.produced,
            consumed=consumed,
            missing=missing,
            remaining=remaining,
            out_of_order=tuple(out_of_order),
            waiting=waiting_elements,
            unmodeled=tuple(unmodeled),
        )
        results.append(variant)
        for name in unmodeled:
            unmodeled_cases[name] += cases
        for element in set(out_of_order):
            out_of_order_cases[element] += cases
        for element in waiting_elements:
            waiting_cases[element] += cases
        for element in set(out_of_order) | set(waiting_elements):
            affected_cases[element] += cases
        if variant.fits:
            fitting += cases
        for index, value in enumerate((tally.produced, consumed, missing, remaining)):
            totals[index] += value * cases

    deviations = tuple(
        sorted(
            (
                ElementDeviation(
                    element_id=element,
                    name=net.names.get(element, element),
                    executed_out_of_order=out_of_order_cases[element],
                    left_waiting=waiting_cases[element],
                    cases_affected=affected_cases[element],
                )
                for element in affected_cases
            ),
            key=lambda d: (-d.cases_affected, d.name),
        )
    )
    replayed_cases = sum(cases for _, cases in kept)
    if dropped:
        warnings.append(ConformanceWarning("variants_truncated", {"kept": len(kept), "dropped": len(dropped)}))
    return ConformanceResult(
        fitness=_fitness(*totals),
        cases=replayed_cases,
        fitting_cases=fitting,
        variants=tuple(results),
        deviations=deviations,
        unmodeled_activities=dict(unmodeled_cases.most_common()),
        unobserved_elements=tuple(sorted(known - observed)),
        excluded_variants=len(dropped),
        excluded_cases=sum(cases for _, cases in dropped),
        warnings=tuple(warnings),
    )
