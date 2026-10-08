"""Che cosa diventa ogni elemento del BPMN quando lo simula Prosimos (SIM-05).

Il normalizer (``bpmn_normalizer``) riduce il BPMN del consulente al
vocabolario del motore: abbassa i tipi di attivita', appiattisce i
sottoprocessi, toglie eventi di bordo ed eventi intermedi, unisce inizi e fini.
Lo fa in silenzio. Qui lo si dichiara, elemento per elemento.

Il report nasce da un confronto, non da una seconda copia delle regole: si
normalizza il BPMN e si guarda che cosa e' sparito, che cosa ha cambiato tipo e
quale flusso e' stato ricollegato. Le regole del normalizer servono solo a dire
*perche'* e con quale impatto sui KPI. Cosi' una regola nuova nel normalizer
non puo' produrre un'approssimazione non dichiarata: finisce comunque nel
report, e ``undeclared`` la conta.
"""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree

from defusedxml.ElementTree import fromstring as _safe_fromstring

from backend.schemas.simulation import (
    BpmnCompatibilityResponse,
    BpmnElementCompatibility,
    CompatibilityStatus,
    KpiImpact,
)
from backend.simulation.bpmn_normalizer import (
    _ACTIVITY_TAGS,
    _GATEWAY_REWRITE,
    _NOISE_TAGS,
    _PASSTHROUGH_EVENT_TAGS,
    _SUBPROCESS_TAGS,
    BPMN_MODEL_NS,
    normalize_bpmn_for_prosimos,
)

_LOOP_TAGS = frozenset({"standardLoopCharacteristics", "multiInstanceLoopCharacteristics"})
_SUPPORTED_GATEWAYS = frozenset(
    {"exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway"}
)
# Eventi che fanno aspettare il caso: toglierli accorcia il cycle time.
_WAITING_DEFINITIONS = frozenset(
    {"messageEventDefinition", "signalEventDefinition", "conditionalEventDefinition"}
)
_STATUS_ORDER: tuple[CompatibilityStatus, ...] = ("preserved", "approximated", "flattened", "removed")


@dataclass(frozen=True)
class _After:
    """Il BPMN normalizzato, ridotto a cio' che serve per il confronto."""

    tags: dict[str, str]
    flows: dict[str, tuple[str, str]]


def bpmn_compatibility_report(bpmn_xml: str) -> BpmnCompatibilityResponse:
    """Il report di compatibilita' di ``bpmn_xml`` con il motore."""
    try:
        root = _safe_fromstring(bpmn_xml.encode("utf-8"))
    except ElementTree.ParseError as exc:
        raise ValueError("XML BPMN non valido.") from exc

    after = _read_after(normalize_bpmn_for_prosimos(bpmn_xml))
    elements: list[BpmnElementCompatibility] = []
    for process in root.iter(_q("process")):
        elements.extend(_ProcessReport(process, after).entries())

    counts = {status: 0 for status in _STATUS_ORDER}
    for entry in elements:
        counts[entry.status] += 1
    return BpmnCompatibilityResponse(
        elements=elements,
        counts=counts,
        kpi_affecting=sum(1 for e in elements if e.status != "preserved" and e.impact != "none"),
        undeclared=_undeclared(root, after, elements),
    )


class _ProcessReport:
    def __init__(self, process: ElementTree.Element, after: _After) -> None:
        self.process = process
        self.after = after
        self.exception_nodes = _exception_branch(process)
        starts = [e.get("id", "") for e in process if _local(e.tag) == "startEvent"]
        ends = [e.get("id", "") for e in process if _local(e.tag) == "endEvent"]
        self.start_survivor = starts[0] if starts else None
        self.end_survivor = ends[0] if ends else None

    def entries(self) -> list[BpmnElementCompatibility]:
        result: list[BpmnElementCompatibility] = []
        for element in self.process:
            result.extend(self._visit(element, flattened_into=None))
        return result

    def _visit(
        self, element: ElementTree.Element, *, flattened_into: str | None
    ) -> list[BpmnElementCompatibility]:
        local = _local(element.tag)
        element_id = element.get("id")
        if not element.tag.startswith(f"{{{BPMN_MODEL_NS}}}") or not element_id:
            return []
        entries = [self._classify(element, local, element_id, flattened_into)]
        if local in _SUBPROCESS_TAGS:
            # I passi interni spariscono dentro la scatola nera del sottoprocesso.
            parent = flattened_into or element_id
            for child in element:
                entries.extend(self._visit(child, flattened_into=parent))
        elif local == "laneSet":
            for child in element:
                entries.extend(self._visit_lanes(child))
        return entries

    def _visit_lanes(self, element: ElementTree.Element) -> list[BpmnElementCompatibility]:
        entries: list[BpmnElementCompatibility] = []
        if _local(element.tag) == "lane" and element.get("id"):
            entries.append(
                _entry(
                    element, "lane", "removed", "none",
                    note="Le lane non arrivano al motore, ma restano risorse: si leggono dal BPMN originale.",
                )
            )
        for child in element:
            if _local(child.tag) in {"lane", "childLaneSet"}:
                entries.extend(self._visit_lanes(child))
        return entries

    def _classify(
        self,
        element: ElementTree.Element,
        local: str,
        element_id: str,
        flattened_into: str | None,
    ) -> BpmnElementCompatibility:
        if flattened_into is not None:
            return _entry(
                element, local, "flattened", "none", simulated_as=flattened_into, parent_id=flattened_into,
                note=f"Dentro il sottoprocesso {flattened_into}: conta solo nella sua durata complessiva.",
            )
        if local in _NOISE_TAGS:
            note = (
                "Le lane non arrivano al motore, ma restano risorse: si leggono dal BPMN originale."
                if local == "laneSet"
                else "Elemento descrittivo: il motore non lo simula e i KPI non cambiano."
            )
            return _entry(element, local, "removed", "none", note=note)
        if local in _SUBPROCESS_TAGS:
            return _entry(
                element, local, "flattened", "high", simulated_as="task",
                note=(
                    "Simulato come un'unica attività: i passi interni non hanno durate, "
                    "risorse né rami propri. La durata va configurata per l'intero sottoprocesso."
                ),
            )
        if local in _ACTIVITY_TAGS or local == "task":
            return self._activity(element, local)
        if local in _GATEWAY_REWRITE:
            return _entry(
                element, local, "approximated", "medium", simulated_as=_GATEWAY_REWRITE[local],
                note="Instradato come gateway esclusivo: ogni caso prende una sola uscita.",
            )
        if local in _SUPPORTED_GATEWAYS:
            return _entry(element, local, "preserved", "none", simulated_as=local)
        if local == "boundaryEvent":
            return self._boundary(element)
        if local in _PASSTHROUGH_EVENT_TAGS:
            return self._intermediate(element, local)
        if local in {"startEvent", "endEvent"}:
            return self._start_or_end(element, local, element_id)
        if local == "sequenceFlow":
            return self._flow(element, element_id)
        if element_id in self.after.tags:
            return _entry(element, local, "preserved", "none", simulated_as=self.after.tags[element_id])
        if element_id in self.exception_nodes:
            return _exception_entry(element, local)
        return _entry(element, local, "removed", "low", note="Elemento che il motore non supporta: non viene simulato.")

    def _activity(self, element: ElementTree.Element, local: str) -> BpmnElementCompatibility:
        element_id = element.get("id", "")
        if element_id not in self.after.tags:
            return _exception_entry(element, local)
        if any(_local(child.tag) in _LOOP_TAGS for child in element):
            return _entry(
                element, local, "approximated", "high", simulated_as="task",
                note=(
                    "Eseguita una volta per caso: ripetizioni e istanze multiple non sono simulate, "
                    "quindi durata, costo e carico della risorsa sono sottostimati."
                ),
            )
        if local == "receiveTask":
            return _entry(
                element, local, "approximated", "medium", simulated_as="task",
                note="L'attesa del messaggio non è simulata: conta solo la durata configurata.",
            )
        if local == "callActivity":
            return _entry(
                element, local, "approximated", "medium", simulated_as="task",
                note="Il processo chiamato è una scatola nera con una durata sola.",
            )
        note = "" if local == "task" else f"{local} simulato come task: per il motore durata e risorsa sono le stesse."
        return _entry(element, local, "preserved", "none", simulated_as="task", note=note)

    def _boundary(self, element: ElementTree.Element) -> BpmnElementCompatibility:
        element_id = element.get("id", "")
        attached = element.get("attachedToRef", "")
        has_branch = any(
            flow.get("sourceRef") == element_id for flow in self.process.findall(_q("sequenceFlow"))
        )
        if not has_branch:
            return _entry(
                element, "boundaryEvent", "removed", "low",
                note=f"Evento sul bordo di {attached} senza un ramo in uscita: non cambia il percorso.",
            )
        kind = _event_kind(element)
        return _entry(
            element, "boundaryEvent", "removed", "high",
            note=(
                f"Evento {kind} sul bordo di {attached}: il ramo d'eccezione non viene mai percorso, "
                "quindi i casi che nella realtà lo prendono seguono sempre il percorso normale."
            ),
        )

    def _intermediate(self, element: ElementTree.Element, local: str) -> BpmnElementCompatibility:
        definitions = {_local(child.tag) for child in element}
        if "timerEventDefinition" in definitions and local == "intermediateCatchEvent":
            impact: KpiImpact = "high"
            note = "L'attesa del timer non è simulata: il cycle time e il tempo di attesa sono sottostimati."
        elif definitions & _WAITING_DEFINITIONS and local == "intermediateCatchEvent":
            impact = "medium"
            note = "L'attesa dell'evento non è simulata: il caso prosegue subito."
        else:
            impact = "none"
            note = "Evento senza durata: saltato, il flusso prima e dopo resta collegato."
        return _entry(element, local, "removed", impact, note=note)

    def _start_or_end(self, element: ElementTree.Element, local: str, element_id: str) -> BpmnElementCompatibility:
        if element_id in self.after.tags:
            return _entry(element, local, "preserved", "none", simulated_as=local)
        if element_id in self.exception_nodes:
            return _exception_entry(element, local)
        if local == "startEvent":
            return _entry(
                element, local, "approximated", "low", simulated_as=self.start_survivor,
                note=(
                    f"Unito all'evento di inizio {self.start_survivor}: tutti i casi arrivano "
                    "con la stessa distribuzione degli arrivi."
                ),
            )
        return _entry(
            element, local, "approximated", "none", simulated_as=self.end_survivor,
            note=f"Unito all'evento di fine {self.end_survivor}: il motore ne accetta uno solo.",
        )

    def _flow(self, element: ElementTree.Element, element_id: str) -> BpmnElementCompatibility:
        source, target = element.get("sourceRef", ""), element.get("targetRef", "")
        if element_id not in self.after.flows:
            if source in self.exception_nodes or target in self.exception_nodes:
                return _entry(
                    element, "sequenceFlow", "removed", "none",
                    note="Parte del ramo d'eccezione tolto: l'impatto è sull'evento di bordo.",
                )
            return _entry(
                element, "sequenceFlow", "removed", "none",
                note="Assorbito nel ricollegamento attorno a un evento saltato.",
            )
        new_source, new_target = self.after.flows[element_id]
        if (new_source, new_target) != (source, target):
            return _entry(
                element, "sequenceFlow", "approximated", "none", simulated_as=f"{new_source} → {new_target}",
                note=f"Ricollegato: da {source} → {target} a {new_source} → {new_target}.",
            )
        return _entry(element, "sequenceFlow", "preserved", "none", simulated_as="sequenceFlow")


def _entry(
    element: ElementTree.Element,
    bpmn_type: str,
    status: CompatibilityStatus,
    impact: KpiImpact,
    *,
    simulated_as: str | None = None,
    parent_id: str | None = None,
    note: str = "",
) -> BpmnElementCompatibility:
    return BpmnElementCompatibility(
        element_id=element.get("id", ""),
        name=element.get("name") or "",
        bpmn_type=bpmn_type,
        status=status,
        impact=impact,
        simulated_as=simulated_as,
        parent_id=parent_id,
        note=note,
    )


def _exception_entry(element: ElementTree.Element, local: str) -> BpmnElementCompatibility:
    return _entry(
        element, local, "removed", "high",
        note="Raggiungibile solo da un ramo d'eccezione tolto: nella simulazione non viene mai eseguito.",
    )


def _read_after(normalized_xml: str) -> _After:
    root = _safe_fromstring(normalized_xml.encode("utf-8"))
    tags: dict[str, str] = {}
    flows: dict[str, tuple[str, str]] = {}
    for process in root.iter(_q("process")):
        for element in process.iter():
            element_id = element.get("id")
            if element is process or not element_id or not element.tag.startswith(f"{{{BPMN_MODEL_NS}}}"):
                continue
            tags[element_id] = _local(element.tag)
            if _local(element.tag) == "sequenceFlow":
                flows[element_id] = (element.get("sourceRef", ""), element.get("targetRef", ""))
    return _After(tags=tags, flows=flows)


def _undeclared(
    root: ElementTree.Element, after: _After, elements: list[BpmnElementCompatibility]
) -> int:
    """Elementi che il normalizer ha cambiato senza dirlo nel report.

    Cambiato vuol dire: sparito, con un altro tipo, o un flusso ricollegato.
    Dichiarato vuol dire: una voce non ``preserved``, oppure ``preserved`` con
    una nota che spiega il cambio di tipo. I figli di attivita' ed eventi
    (definizioni, caratteristiche di ciclo) contano come parte del loro padre.
    """
    by_id = {entry.element_id: entry for entry in elements}
    missing = 0
    for process in root.iter(_q("process")):
        for element in _flow_level(process):
            element_id = element.get("id", "")
            local = _local(element.tag)
            changed = (
                element_id not in after.tags
                or after.tags[element_id] != local
                or (
                    local == "sequenceFlow"
                    and after.flows.get(element_id)
                    != (element.get("sourceRef", ""), element.get("targetRef", ""))
                )
            )
            if not changed:
                continue
            entry = by_id.get(element_id)
            if entry is None or (entry.status == "preserved" and not entry.note):
                missing += 1
    return missing


def _flow_level(process: ElementTree.Element):
    """Gli elementi con un id che hanno senso da soli: figli del processo, dei
    sottoprocessi e dei laneSet. Non i figli di attivita' ed eventi."""
    pending = list(process)
    while pending:
        element = pending.pop()
        if not element.tag.startswith(f"{{{BPMN_MODEL_NS}}}"):
            continue
        local = _local(element.tag)
        if element.get("id"):
            yield element
        if local in _SUBPROCESS_TAGS or local in {"laneSet", "lane", "childLaneSet"}:
            pending.extend(element)


def _exception_branch(process: ElementTree.Element) -> set[str]:
    """Gli elementi raggiungibili da un evento di bordo e non dagli inizi."""
    successors: dict[str, list[str]] = {}
    for flow in process.findall(_q("sequenceFlow")):
        successors.setdefault(flow.get("sourceRef", ""), []).append(flow.get("targetRef", ""))

    def reach(seeds: list[str]) -> set[str]:
        seen: set[str] = set()
        while seeds:
            node = seeds.pop()
            if node and node not in seen:
                seen.add(node)
                seeds.extend(successors.get(node, []))
        return seen

    boundaries = [e.get("id", "") for e in process.findall(_q("boundaryEvent"))]
    starts = [e.get("id", "") for e in process if _local(e.tag) == "startEvent"]
    return reach(boundaries) - reach(starts)


def _event_kind(element: ElementTree.Element) -> str:
    names = {
        "timerEventDefinition": "timer",
        "errorEventDefinition": "di errore",
        "escalationEventDefinition": "di escalation",
        "messageEventDefinition": "di messaggio",
        "signalEventDefinition": "di segnale",
        "conditionalEventDefinition": "condizionale",
        "compensateEventDefinition": "di compensazione",
        "cancelEventDefinition": "di annullamento",
    }
    for child in element:
        kind = names.get(_local(child.tag))
        if kind:
            return kind
    return "senza tipo"


def _q(tag: str) -> str:
    return f"{{{BPMN_MODEL_NS}}}{tag}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
