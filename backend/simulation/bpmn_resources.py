"""Organisational candidates from the source BPMN, before normalisation drops lanes.
Names and membership are structural evidence; capacity and costs are not inferred.
"""
from hashlib import sha256
from xml.etree import ElementTree as ET
from backend.schemas.simulation import ScenarioTemplateResource

NS = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"


def _reference(value: str) -> str:
    """BPMN references may use namespace-qualified QNames."""
    return value.strip().rsplit(":", 1)[-1]


def describe_bpmn_resources(xml: str, task_ids: set[str]) -> list[ScenarioTemplateResource]:
    root = ET.fromstring(xml)
    result = []
    participants: dict[str, list[ET.Element]] = {}
    for participant in root.iter(NS + "participant"):
        participants.setdefault(_reference(participant.get("processRef", "")), []).append(participant)
    for process in root.iter(NS + "process"):
        pools = participants.get(process.get("id", ""), [])
        pool = pools[0] if len(pools) == 1 else None
        pool_name = (pool.get("name") or pool.get("id")) if pool is not None else None
        parent = {child: node for node in process.iter() for child in node}
        lanes = list(process.iter(NS + "lane"))

        def ancestry(lane: ET.Element, parents: dict[ET.Element, ET.Element] = parent) -> list[str]:
            names = []
            node = parents.get(lane)
            while node is not None:
                if node.tag == NS + "lane":
                    names.append(node.get("name") or node.get("id", ""))
                node = parents.get(node)
            return list(reversed(names))

        # Parent/child overlap selects the deepest lane. Sibling conflicts are
        # ambiguous organisational evidence and require manual assignment.
        memberships: dict[str, list[ET.Element]] = {}
        for lane in lanes:
            for ref in lane.findall(NS + "flowNodeRef"):
                task_id = _reference(ref.text or "")
                if task_id in task_ids and lane.get("id"):
                    if lane not in memberships.setdefault(task_id, []):
                        memberships[task_id].append(lane)
        owners: dict[str, ET.Element] = {}
        for task_id, members in memberships.items():
            deepest = max(len(ancestry(lane)) for lane in members)
            leaves = [lane for lane in members if len(ancestry(lane)) == deepest]
            if len(leaves) == 1:
                owners[task_id] = leaves[0]
        for lane in lanes:
            members = [task_id for task_id, owner in owners.items() if owner is lane]
            lane_id = lane.get("id")
            if not lane_id or not members:
                continue
            result.append(ScenarioTemplateResource(
                id="bpmn-lane-" + sha256(lane_id.encode()).hexdigest()[:16],
                bpmn_id=lane_id, name=lane.get("name") or lane_id, kind="lane",
                pool_name=pool_name, parent_name=" / ".join(ancestry(lane)) or None,
                task_ids=members,
            ))
        if pool is not None and not lanes:
            members = [node.get("id") for node in process.iter() if node.get("id") in task_ids]
            if members:
                pool_id = pool.get("id", "")
                result.append(ScenarioTemplateResource(
                    id="bpmn-pool-" + sha256(pool_id.encode()).hexdigest()[:16],
                    bpmn_id=pool_id, name=pool_name or pool_id, kind="pool", pool_name=pool_name,
                    task_ids=members,
                ))
    return result
