"""Conservative graph checks on the BPMN XML currently visible in the canvas.

This detects unreachable nodes and paths without an end. It is not a token
simulation and cannot prove deadlock freedom for parallel/inclusive gateways.
"""

from __future__ import annotations

from collections import defaultdict

from defusedxml.ElementTree import fromstring

from backend.workspace_services.bpmn_canvas_edit import BPMN_NS, FLOW_NODE_TYPES

_FLOW_NODE_TYPES = FLOW_NODE_TYPES | {"callActivity", "transaction", "adHocSubProcess"}
_UNSUPPORTED_FLOW_NODE_TYPES = {"choreographyTask", "callChoreography", "subChoreography"}


def _tag(element) -> str:
    return element.tag.rsplit("}", 1)[-1] if element.tag.startswith("{" + BPMN_NS + "}") else ""


def _reach(seeds: set[str], edges: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    pending = list(seeds)
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        pending.extend(edges.get(node, ()))
    return seen


def analyze_canvas_xml_behavior(xml: str) -> dict:
    """Analyze each process's top-level control graph, without changing XML."""
    root = fromstring(xml)
    issues: list[str] = []
    warnings: list[str] = []
    analyzed = 0
    skipped = 0
    for process in root.iter("{" + BPMN_NS + "}process"):
        process_id = process.get("id") or "(senza ID)"
        nodes = {child.get("id"): child for child in process
                 if _tag(child) in _FLOW_NODE_TYPES and child.get("id")}
        if not nodes:
            continue
        flows = [child for child in process if _tag(child) == "sequenceFlow"]
        unsupported_ids = {child.get("id") for child in process
                           if _tag(child) in _UNSUPPORTED_FLOW_NODE_TYPES and child.get("id")}
        if any(flow.get("sourceRef") in unsupported_ids or flow.get("targetRef") in unsupported_ids
               for flow in flows):
            skipped += 1
            warnings.append(f"Processo {process_id}: analisi L3 parziale, tipo di nodo BPMN non supportato.")
            continue
        analyzed += 1
        forward: dict[str, set[str]] = defaultdict(set)
        reverse: dict[str, set[str]] = defaultdict(set)
        for flow in flows:
            source, target = flow.get("sourceRef"), flow.get("targetRef")
            if source not in nodes or target not in nodes:
                issues.append(f"Processo {process_id}: collegamento {flow.get('id') or '(senza ID)'} "
                              "punta fuori dal grafo del processo.")
                continue
            forward[source].add(target)
            reverse[target].add(source)
        for node_id, node in nodes.items():
            if _tag(node) != "boundaryEvent":
                continue
            host = node.get("attachedToRef")
            if host in nodes:
                forward[host].add(node_id)
                reverse[node_id].add(host)
        starts = {node_id for node_id, node in nodes.items()
                  if _tag(node) == "startEvent" or
                  (_tag(node) == "eventBasedGateway" and node.get("instantiate") == "true")}
        ends = {node_id for node_id, node in nodes.items() if _tag(node) == "endEvent"}
        if not starts:
            issues.append(f"Processo {process_id}: nessun evento iniziale nel grafo principale.")
        if not ends:
            issues.append(f"Processo {process_id}: nessun evento finale nel grafo principale.")
        reachable, coreachable = _reach(starts, forward), _reach(ends, reverse)
        for node_id, node in nodes.items():
            if _tag(node) == "boundaryEvent" or node.get("isForCompensation") == "true" or (
                _tag(node) == "subProcess" and node.get("triggeredByEvent") == "true"
            ):
                continue
            if starts and node_id not in reachable:
                issues.append(f"Processo {process_id}: elemento {node_id} non raggiungibile dall'inizio.")
            if ends and _tag(node) != "endEvent" and node_id not in coreachable:
                issues.append(f"Processo {process_id}: elemento {node_id} senza percorso verso la fine.")
        if any(_tag(node) in {"parallelGateway", "inclusiveGateway", "complexGateway"}
               for node in nodes.values()):
            warnings.append(f"Processo {process_id}: il grafo non prova l'assenza di deadlock nei gateway concorrenti.")
    scope = ("partial_unsupported_nodes" if skipped else
             "top_level_reachability_only" if analyzed else "no_flow_nodes_analyzed")
    if not analyzed:
        warnings.append("Nessun grafo di processo analizzato: soundness non determinabile.")
    return {
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "coverage": {"scope": scope, "processes_analyzed": analyzed, "processes_skipped": skipped},
        "behavioral_scope": scope,
        "processes_analyzed": analyzed,
        "processes_skipped": skipped,
    }
