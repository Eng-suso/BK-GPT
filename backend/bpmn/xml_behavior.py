"""Conservative behavioral checks on the BPMN XML currently visible in the canvas.

Two layers, reported separately:

1. Graph reachability: unreachable nodes, paths without an end, sequence flows
   that leave the process.
2. A bounded token game on the top-level control flow (exclusive, parallel and
   event-based gateways, activities, events, boundary events). Exclusive
   choices are treated as free choices, the standard abstraction of workflow
   net soundness: a deadlock found here is possible for *some* data, not
   necessarily for every case. It finds parallel joins that wait forever
   (deadlock) and branches that reach the same step twice for one case (lack of
   synchronization).

The token game is skipped, and the report says so, when the process uses
constructs whose semantics it does not model (inclusive or complex gateways,
conditional flows out of activities) or when the state space exceeds its
budget. Subprocess internals are treated as one atomic step. Nothing here
proves soundness outside the stated scope.
"""

from __future__ import annotations

from collections import defaultdict

from defusedxml.ElementTree import fromstring

from backend.workspace_services.bpmn_canvas_edit import BPMN_NS, FLOW_NODE_TYPES

_FLOW_NODE_TYPES = FLOW_NODE_TYPES | {"callActivity", "transaction", "adHocSubProcess"}
_UNSUPPORTED_FLOW_NODE_TYPES = {"choreographyTask", "callChoreography", "subChoreography"}
_UNMODELED_GATEWAYS = {"inclusiveGateway", "complexGateway"}
_CONCURRENT_GATEWAYS = {"parallelGateway", "inclusiveGateway", "complexGateway"}
# Above this many distinct markings the token game stops and says so.
TOKEN_STATE_BUDGET = 20_000

Marking = tuple[tuple[str, int], ...]


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


def _label(node) -> str:
    name = " ".join((node.get("name") or "").split())
    node_id = node.get("id") or "(senza ID)"
    return f"«{name}» ({node_id})" if name else node_id


def _has_child(node, local_name: str) -> bool:
    return any(_tag(child) == local_name for child in node)


class _TokenGame:
    """Explicit-state exploration of one process's top-level control flow."""

    def __init__(self, nodes: dict, flows: list, budget: int) -> None:
        self.nodes = nodes
        self.budget = budget
        self.incoming: dict[str, list[str]] = defaultdict(list)
        self.outgoing: dict[str, list[str]] = defaultdict(list)
        self.flow_target: dict[str, str] = {}
        self.conditional: set[str] = set()
        for flow in flows:
            flow_id, source, target = flow.get("id"), flow.get("sourceRef"), flow.get("targetRef")
            if not flow_id or source not in nodes or target not in nodes:
                continue
            self.outgoing[source].append(flow_id)
            self.incoming[target].append(flow_id)
            self.flow_target[flow_id] = target
            if _has_child(flow, "conditionExpression"):
                self.conditional.add(flow_id)
        self.boundaries: dict[str, list] = defaultdict(list)
        for node_id, node in nodes.items():
            if _tag(node) == "boundaryEvent" and node.get("attachedToRef") in nodes:
                self.boundaries[node.get("attachedToRef")].append(node_id)

    def unsupported_reason(self) -> str | None:
        for node_id, node in self.nodes.items():
            kind = _tag(node)
            if kind in _UNMODELED_GATEWAYS:
                return f"gateway {kind} {_label(node)}"
            if kind.endswith("Gateway") or kind == "endEvent":
                continue
            if len(self.outgoing[node_id]) > 1 and any(
                flow in self.conditional for flow in self.outgoing[node_id]
            ):
                return f"uscite condizionali senza gateway da {_label(node)}"
        return None

    # A step's firing can end in several ways (exclusive choice, boundary
    # events); each is one successor marking.
    def _productions(self, node_id: str) -> list[tuple[str, ...]]:
        node = self.nodes[node_id]
        kind = _tag(node)
        out = tuple(self.outgoing[node_id])
        if kind in {"exclusiveGateway", "eventBasedGateway"}:
            return [(flow,) for flow in out] or [()]
        options = [out]
        for boundary_id in self.boundaries.get(node_id, ()):
            boundary_out = tuple(self.outgoing[boundary_id])
            if self.nodes[boundary_id].get("cancelActivity", "true") == "false":
                options.append(out + boundary_out)
            else:
                options.append(boundary_out)
        return options

    def _fire(self, marking: dict[str, int], node_id: str, consumed: list[str]) -> list[Marking]:
        node = self.nodes[node_id]
        if _tag(node) == "endEvent" and _has_child(node, "terminateEventDefinition"):
            return [()]
        base = dict(marking)
        for flow in consumed:
            base[flow] -= 1
            if not base[flow]:
                del base[flow]
        result = []
        for produced in self._productions(node_id):
            successor = dict(base)
            for flow in produced:
                successor[flow] = successor.get(flow, 0) + 1
            result.append(tuple(sorted(successor.items())))
        return result

    def successors(self, marking: Marking) -> list[Marking]:
        tokens = dict(marking)
        result: list[Marking] = []
        fired_joins: set[str] = set()
        for flow in tokens:
            node_id = self.flow_target[flow]
            if _tag(self.nodes[node_id]) == "parallelGateway":
                if node_id in fired_joins:
                    continue
                fired_joins.add(node_id)
                if all(tokens.get(item) for item in self.incoming[node_id]):
                    result.extend(self._fire(tokens, node_id, list(self.incoming[node_id])))
                continue
            result.extend(self._fire(tokens, node_id, [flow]))
        return result

    def initial_markings(self) -> list[tuple[str, Marking]]:
        starts = []
        for node_id, node in self.nodes.items():
            kind = _tag(node)
            if kind == "startEvent" or (kind == "eventBasedGateway" and node.get("instantiate") == "true"):
                for produced in self._productions(node_id):
                    counts: dict[str, int] = defaultdict(int)
                    for flow in produced:
                        counts[flow] += 1
                    starts.append((node_id, tuple(sorted(counts.items()))))
        return starts

    def explore(self) -> dict:
        """Return deadlocked joins, duplicated flows and whether the budget held."""
        deadlocked: set[str] = set()
        duplicated: set[str] = set()
        no_completion = False
        seen: set[Marking] = set()
        edges: dict[Marking, list[Marking]] = {}
        pending = [marking for _start, marking in self.initial_markings()]
        while pending:
            marking = pending.pop()
            if marking in seen:
                continue
            if len(seen) >= self.budget:
                return {"complete": False, "deadlocked": deadlocked,
                        "duplicated": duplicated, "no_completion": no_completion}
            seen.add(marking)
            unsafe = [flow for flow, count in marking if count > 1]
            if unsafe:
                # One case runs the same step twice: report and stop here,
                # otherwise a loop around a parallel split never terminates.
                duplicated.update(self.flow_target[flow] for flow in unsafe)
                edges[marking] = []
                continue
            following = self.successors(marking)
            edges[marking] = following
            if marking and not following:
                deadlocked.update(self.flow_target[flow] for flow, _count in marking)
            pending.extend(following)
        # Option to complete: from every live marking, the empty marking (all
        # tokens consumed) must stay reachable. Deadlocks and duplicates are
        # already reported; anything else that cannot finish is a livelock.
        reverse: dict[Marking, set[Marking]] = defaultdict(set)
        for source, targets in edges.items():
            for target in targets:
                reverse[target].add(source)
        can_finish = _reach({marking for marking in seen if not marking}, reverse)
        if not deadlocked and not duplicated:
            no_completion = any(marking and marking not in can_finish for marking in seen)
        return {"complete": True, "deadlocked": deadlocked,
                "duplicated": duplicated, "no_completion": no_completion}


def analyze_canvas_xml_behavior(xml: str, *, token_budget: int = TOKEN_STATE_BUDGET) -> dict:
    """Analyze each process's top-level control graph, without changing XML."""
    root = fromstring(xml)
    issues: list[str] = []
    warnings: list[str] = []
    findings: list[dict] = []
    analyzed = 0
    skipped = 0
    token_analyzed = 0
    token_skipped = 0

    def finding(code: str, process_id: str, node, message: str) -> None:
        issues.append(message)
        findings.append({
            "code": code,
            "process_id": process_id,
            "element_id": node.get("id") if node is not None else None,
            "element_name": (" ".join((node.get("name") or "").split()) or None) if node is not None else None,
        })

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
                finding("flow_outside_process", process_id, flow,
                        f"Processo {process_id}: collegamento {flow.get('id') or '(senza ID)'} "
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
            finding("no_start_event", process_id, None,
                    f"Processo {process_id}: nessun evento iniziale nel grafo principale.")
        if not ends:
            finding("no_end_event", process_id, None,
                    f"Processo {process_id}: nessun evento finale nel grafo principale.")
        reachable, coreachable = _reach(starts, forward), _reach(ends, reverse)
        graph_issues_before = len(issues)
        for node_id, node in nodes.items():
            if _tag(node) == "boundaryEvent" or node.get("isForCompensation") == "true" or (
                _tag(node) == "subProcess" and node.get("triggeredByEvent") == "true"
            ):
                continue
            if starts and node_id not in reachable:
                finding("unreachable_node", process_id, node,
                        f"Processo {process_id}: elemento {node_id} non raggiungibile dall'inizio.")
            if ends and _tag(node) != "endEvent" and node_id not in coreachable:
                finding("dead_end_node", process_id, node,
                        f"Processo {process_id}: elemento {node_id} senza percorso verso la fine.")

        has_concurrency = any(_tag(node) in _CONCURRENT_GATEWAYS for node in nodes.values())
        if len(issues) > graph_issues_before or not starts:
            # A broken graph is already rejected; a token game on it would only
            # repeat the same finding in other words.
            if has_concurrency:
                warnings.append(f"Processo {process_id}: il grafo non prova l'assenza di deadlock "
                                "nei gateway concorrenti (grafo incompleto).")
            token_skipped += 1
            continue
        game = _TokenGame(nodes, flows, token_budget)
        reason = game.unsupported_reason()
        if reason:
            token_skipped += 1
            warnings.append(f"Processo {process_id}: il grafo non prova l'assenza di deadlock "
                            f"nei gateway concorrenti ({reason}).")
            continue
        outcome = game.explore()
        if not outcome["complete"]:
            token_skipped += 1
            warnings.append(f"Processo {process_id}: analisi dei token interrotta oltre {token_budget} stati; "
                            "deadlock non esclusi.")
            continue
        token_analyzed += 1
        for node_id in sorted(outcome["deadlocked"]):
            node = nodes[node_id]
            finding("deadlock", process_id, node,
                    f"Processo {process_id}: deadlock possibile, {_label(node)} attende rami che "
                    "per alcune scelte non arrivano mai.")
        for node_id in sorted(outcome["duplicated"]):
            node = nodes[node_id]
            finding("lack_of_synchronization", process_id, node,
                    f"Processo {process_id}: {_label(node)} puo' ricevere due volte la stessa pratica: "
                    "rami paralleli si riuniscono senza sincronizzazione.")
        if outcome["no_completion"]:
            finding("no_option_to_complete", process_id, None,
                    f"Processo {process_id}: alcune esecuzioni non possono piu' terminare.")

    if not analyzed:
        scope = "no_flow_nodes_analyzed"
    elif skipped:
        scope = "partial_unsupported_nodes"
    elif token_analyzed and not token_skipped:
        scope = "top_level_reachability_and_tokens"
    else:
        scope = "top_level_reachability_only"
    if not analyzed:
        warnings.append("Nessun grafo di processo analizzato: soundness non determinabile.")
    return {
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "findings": findings,
        "coverage": {
            "scope": scope,
            "processes_analyzed": analyzed,
            "processes_skipped": skipped,
            "token_game_processes": token_analyzed,
            "token_game_skipped": token_skipped,
            "subprocess_internals": "atomic",
        },
        "behavioral_scope": scope,
        "processes_analyzed": analyzed,
        "processes_skipped": skipped,
    }
