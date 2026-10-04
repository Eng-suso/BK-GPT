"""Organisational candidates from the source BPMN, before normalisation drops lanes.
Names and membership are structural evidence; capacity and costs are not inferred.
"""
from hashlib import sha256
from xml.etree import ElementTree as ET
from backend.schemas.simulation import ScenarioTemplateResource

NS = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"


def describe_bpmn_resources(xml: str, task_ids: set[str]) -> list[ScenarioTemplateResource]:
    root = ET.fromstring(xml)
    result = []
    participants: dict[str, list[ET.Element]] = {}
    for participant in root.iter(NS + "participant"):
        participants.setdefault(participant.get("processRef", ""), []).append(participant)
    for process in root.iter(NS + "process"):
        pools = participants.get(process.get("id", ""), [])
        pool = pools[0] if len(pools) == 1 else None
        pool_name = pool.get("name") or pool.get("id") if pool is not None else None
        parent = {child: node for node in process.iter() for child in node}
        lanes = list(process.iter(NS + "lane"))

        def ancestry(lane: ET.Element) -> list[str]:
            names = []
            node = parent.get(lane)
            while node is not None:
                if node.tag == NS + "lane":
                    names.append(node.get("name") or node.get("id", ""))
                node = parent.get(node)
            return list(reversed(names))

        assigned: set[str] = set()
        for lane in sorted(lanes, key=lambda item: len(ancestry(item)), reverse=True):
            members = [ref.text.strip() for ref in lane.findall(NS + "flowNodeRef") if ref.text and ref.text.strip() in task_ids and ref.text.strip() not in assigned]
            members = list(dict.fromkeys(members))
            lane_id = lane.get("id")
            if not lane_id or not members:
                continue
            assigned.update(members)
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
