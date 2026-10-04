"""Preflight the engine's actual BPMN, before creating or submitting a run."""

from collections import defaultdict
from xml.etree import ElementTree

from backend.simulation.bpmn_normalizer import BPMN_MODEL_NS


_NODE_TYPES = {
    "task",
    "userTask",
    "serviceTask",
    "scriptTask",
    "businessRuleTask",
    "manualTask",
    "sendTask",
    "receiveTask",
    "callActivity",
    "startEvent",
    "endEvent",
    "exclusiveGateway",
    "parallelGateway",
    "inclusiveGateway",
    "eventBasedGateway",
    "intermediateCatchEvent",
}


def _reachable(seeds: set[str], links: dict[str, set[str]]) -> set[str]:
    reached: set[str] = set()
    pending = list(seeds)
    while pending:
        node = pending.pop()
        if node not in reached:
            reached.add(node)
            pending.extend(links.get(node, set()) - reached)
    return reached


def validate_simulation_bpmn(bpmn_xml: str) -> None:
    """Reject incomplete paths; message flows are not execution sequence flows.

    This is a structural preflight, not a proof of gateway/liveness soundness.
    It must run after normalization, which can remove flow nodes.
    """
    try:
        root = ElementTree.fromstring(bpmn_xml)
    except ElementTree.ParseError as exc:
        raise ValueError("XML BPMN non valido.") from exc

    ns = f"{{{BPMN_MODEL_NS}}}"
    node_tags = {f"{ns}{kind}" for kind in _NODE_TYPES}
    processes = list(root.iter(f"{ns}process"))
    if not processes:
        raise ValueError("Il BPMN non contiene un processo nel namespace BPMN valido.")

    ids: set[str] = set()
    for element in root.iter():
        element_id = element.get("id")
        if element_id:
            if element_id in ids:
                raise ValueError(f"Il BPMN contiene un ID duplicato: {element_id}.")
            ids.add(element_id)

    for process in processes:
        prefix = (
            f"Simulazione non avviata: processo {process.get('id', '(senza ID)')}. "
        )
        hint = (
            " Collega inizio, attività e fine con flussi di sequenza nello stesso pool; "
            "i flussi di messaggio tra pool non li sostituiscono."
        )
        nodes = {}
        for element in process:
            if element.tag in node_tags:
                if not element.get("id"):
                    raise ValueError(prefix + "Un nodo del processo non ha un ID.")
                nodes[element.get("id")] = element
        if not nodes:
            raise ValueError(prefix + "Non contiene nodi simulabili.")

        starts = {key for key, node in nodes.items() if node.tag == f"{ns}startEvent"}
        ends = {key for key, node in nodes.items() if node.tag == f"{ns}endEvent"}
        if not starts:
            raise ValueError(prefix + "Manca un evento di inizio." + hint)
        if not ends:
            raise ValueError(prefix + "Manca un evento di fine raggiungibile." + hint)

        successors: dict[str, set[str]] = defaultdict(set)
        predecessors: dict[str, set[str]] = defaultdict(set)
        for flow in process.findall(f"{ns}sequenceFlow"):
            source, target = flow.get("sourceRef"), flow.get("targetRef")
            if source not in nodes or target not in nodes:
                raise ValueError(
                    prefix + f"Il collegamento {flow.get('id', '(senza ID)')} "
                    "punta a un nodo inesistente o di un altro pool."
                )
            if not flow.get("id"):
                raise ValueError(prefix + "Un flusso di sequenza non ha un ID.")
            successors[source].add(target)
            predecessors[target].add(source)

        reached = _reachable(starts, successors)
        if not ends & reached:
            raise ValueError(
                prefix + "Nessun evento di fine è raggiungibile dall'inizio." + hint
            )
        disconnected = nodes.keys() - reached
        if disconnected:
            raise ValueError(
                prefix
                + "Nodi scollegati dall'inizio: "
                + ", ".join(sorted(disconnected)[:5])
                + "."
                + hint
            )
        dead_ends = nodes.keys() - _reachable(ends, predecessors)
        if dead_ends:
            raise ValueError(
                prefix
                + "Rami senza percorso verso la fine: "
                + ", ".join(sorted(dead_ends)[:5])
                + "."
                + hint
            )
        if any(predecessors[node] for node in starts) or any(
            successors[node] for node in ends
        ):
            raise ValueError(
                prefix
                + "Un evento di inizio ha ingressi o un evento di fine ha uscite."
            )
