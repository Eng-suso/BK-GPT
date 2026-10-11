"""Il processo compatto del video hero, disegnato e simulato.

Nell'hero il processo deve leggersi tutto in un colpo d'occhio: tre corsie,
cinque attivita', una decisione con il suo giro di rilavorazione. E' una
versione ridotta del caso acquisti della demo (stessi colli di bottiglia:
richieste incomplete che tornano indietro, un responsabile che autorizza due
volte a settimana), in inglese come la landing.

Esce:
- `e2e/launch-media/data/hero.bpmn`: BPMN con pool, corsie e DI ortogonale;
- `e2e/launch-media/data/hero-runs.json`: run As-Is e To-Be (summary + replay),
  stesso motore e stessa pipeline del prodotto;
- `e2e/launch-media/data/hero-api.json`: template e provenienza per il pannello.

    PYTHONPATH=. uv run python scripts/launch_media_hero_process.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

sys.path.insert(0, str(Path(__file__).resolve().parent))

from launch_media_simulate import DATA, WORKDAY, assumed, finite, lognormal, normal, run  # noqa: E402

from backend.simulation.advisor import suggest_experiments  # noqa: E402
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos  # noqa: E402
from backend.simulation.ir.model import SimulationModel  # noqa: E402
from backend.simulation.scenario_builder import baseline_for_bpmn, describe_scenario_template  # noqa: E402

OUT = DATA / "hero.bpmn"
POOL = ("Participant_hero", "Process_hero", "Purchase request")

# corsia -> (nome, y)
LANES = {"requester": ("Requester", 0), "purchasing": ("Purchasing", 150), "manager": ("Manager", 300)}
LANE_H = 150
POOL_W = 1180

# id -> (tipo, nome, corsia, x, y) con x, y in alto a sinistra
NODES = {
    "start": ("startEvent", "Need spotted", "requester", 90, 57),
    "send_request": ("userTask", "Send purchase request", "requester", 170, 35),
    "complete_request": ("userTask", "Complete the request", "requester", 480, 35),
    "check_request": ("userTask", "Check request", "purchasing", 330, 185),
    "gw_complete": ("exclusiveGateway", "Request complete?", "purchasing", 515, 200),
    "issue_po": ("userTask", "Issue purchase order", "purchasing", 800, 185),
    "end": ("endEvent", "Order sent", "purchasing", 1000, 207),
    "approve_spend": ("userTask", "Approve spend", "manager", 640, 335),
}

# id, sorgente, destinazione, nome, waypoint
FLOWS = [
    ("f_start", "start", "send_request", None, [(126, 75), (170, 75)]),
    ("f_send", "send_request", "check_request", None, [(230, 115), (230, 225), (330, 225)]),
    ("f_check", "check_request", "gw_complete", None, [(450, 225), (515, 225)]),
    ("f_incomplete", "gw_complete", "complete_request", "No", [(540, 200), (540, 115)]),
    ("f_back", "complete_request", "check_request", None, [(480, 75), (390, 75), (390, 185)]),
    ("f_complete", "gw_complete", "approve_spend", "Yes", [(540, 250), (540, 375), (640, 375)]),
    ("f_approved", "approve_spend", "issue_po", None, [(760, 375), (860, 375), (860, 265)]),
    ("f_end", "issue_po", "end", None, [(920, 225), (1000, 225)]),
]
FLOW_LABELS = {"f_incomplete": (548, 140), "f_complete": (548, 290)}


def size(kind: str) -> tuple[int, int]:
    return {"startEvent": (36, 36), "endEvent": (36, 36), "exclusiveGateway": (50, 50)}.get(kind, (120, 80))


def bpmn() -> str:
    pid, proc, name = POOL
    incoming: dict[str, list[str]] = {}
    outgoing: dict[str, list[str]] = {}
    for fid, src, dst, *_ in FLOWS:
        outgoing.setdefault(src, []).append(fid)
        incoming.setdefault(dst, []).append(fid)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_hero" targetNamespace="https://delir.ai/bpmn">',
        f'  <bpmn:collaboration id="Collaboration_hero"><bpmn:participant id="{pid}" name={quoteattr(name)} processRef="{proc}" /></bpmn:collaboration>',
        f'  <bpmn:process id="{proc}" name={quoteattr(name)} isExecutable="false">',
        f'    <bpmn:laneSet id="{proc}_lanes">',
    ]
    for lane, (lane_name, _) in LANES.items():
        refs = "".join(f"<bpmn:flowNodeRef>{n}</bpmn:flowNodeRef>" for n, v in NODES.items() if v[2] == lane)
        lines.append(f'      <bpmn:lane id="{lane}" name={quoteattr(lane_name)}>{refs}</bpmn:lane>')
    lines.append("    </bpmn:laneSet>")
    for nid, (kind, label, *_rest) in NODES.items():
        flows = "".join(f"<bpmn:incoming>{f}</bpmn:incoming>" for f in incoming.get(nid, []))
        flows += "".join(f"<bpmn:outgoing>{f}</bpmn:outgoing>" for f in outgoing.get(nid, []))
        default = ' default="f_complete"' if nid == "gw_complete" else ""
        lines.append(f'    <bpmn:{kind} id="{nid}" name={quoteattr(label)}{default}>{flows}</bpmn:{kind}>')
    for fid, src, dst, label, _ in FLOWS:
        named = f" name={quoteattr(label)}" if label else ""
        lines.append(f'    <bpmn:sequenceFlow id="{fid}"{named} sourceRef="{src}" targetRef="{dst}" />')
    lines.append("  </bpmn:process>")
    lines.append('  <bpmndi:BPMNDiagram id="Diagram_hero"><bpmndi:BPMNPlane id="Plane_hero" bpmnElement="Collaboration_hero">')
    lines.append(f'    <bpmndi:BPMNShape id="{pid}_di" bpmnElement="{pid}" isHorizontal="true"><dc:Bounds x="0" y="0" width="{POOL_W}" height="{LANE_H * len(LANES)}" /></bpmndi:BPMNShape>')
    for lane, (_, y) in LANES.items():
        lines.append(f'    <bpmndi:BPMNShape id="{lane}_di" bpmnElement="{lane}" isHorizontal="true"><dc:Bounds x="30" y="{y}" width="{POOL_W - 30}" height="{LANE_H}" /></bpmndi:BPMNShape>')
    for nid, (kind, _label, _lane, x, y) in NODES.items():
        w, h = size(kind)
        marker = ' isMarkerVisible="true"' if kind == "exclusiveGateway" else ""
        label = ""
        if kind in ("startEvent", "endEvent"):
            label = f'<bpmndi:BPMNLabel><dc:Bounds x="{x - 27}" y="{y + 40}" width="90" height="14" /></bpmndi:BPMNLabel>'
        elif kind == "exclusiveGateway":
            label = f'<bpmndi:BPMNLabel><dc:Bounds x="{x - 75}" y="{y - 30}" width="90" height="27" /></bpmndi:BPMNLabel>'
        lines.append(f'    <bpmndi:BPMNShape id="{nid}_di" bpmnElement="{nid}"{marker}><dc:Bounds x="{x}" y="{y}" width="{w}" height="{h}" />{label}</bpmndi:BPMNShape>')
    for fid, _src, _dst, _label, points in FLOWS:
        waypoints = "".join(f'<di:waypoint x="{px}" y="{py}" />' for px, py in points)
        label = ""
        if fid in FLOW_LABELS:
            lx, ly = FLOW_LABELS[fid]
            label = f'<bpmndi:BPMNLabel><dc:Bounds x="{lx}" y="{ly}" width="24" height="14" /></bpmndi:BPMNLabel>'
        lines.append(f'    <bpmndi:BPMNEdge id="{fid}_di" bpmnElement="{fid}">{waypoints}{label}</bpmndi:BPMNEdge>')
    lines.append("  </bpmndi:BPMNPlane></bpmndi:BPMNDiagram>")
    lines.append("</bpmn:definitions>")
    return "\n".join(lines) + "\n"


# Durate (minuti) e risorse: le stesse proporzioni del caso acquisti della demo.
DURATIONS = {
    "send_request": normal(5, 1),
    "check_request": normal(10, 3),
    "complete_request": lognormal(30, 20, 240),
    "approve_spend": normal(3, 1),
    "issue_po": normal(15, 4),
}
RESOURCES = {"Requester": (6, 38.0), "Purchasing": (1, 45.0), "Manager": (1, 70.0)}
TWICE_A_WEEK = [
    {"from_day": "TUESDAY", "to_day": "TUESDAY", "begin": "16:00:00.000", "end": "17:00:00.000"},
    {"from_day": "THURSDAY", "to_day": "THURSDAY", "begin": "16:00:00.000", "end": "17:00:00.000"},
]
DAILY = [{"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "09:00:00.000", "end": "17:00:00.000"}]


def model(base: SimulationModel, *, incomplete: float, manager: list[dict]) -> SimulationModel:
    data = base.model_dump(mode="json")
    data["arrival"]["interarrival"] = {"kind": "exponential", "mean": WORKDAY / 5, "minimum": 0.0, "maximum": WORKDAY}
    data["arrival"]["provenance"] = assumed("About 5 requests a day: demo assumption.")
    data["calendars"].append({"id": "manager", "name": "Manager approvals", "periods": manager})
    for pool in data["pools"]:
        for resource in pool["resources"]:
            amount, cost = RESOURCES[resource["name"]]
            resource["amount"], resource["cost_per_hour"] = amount, cost
            if resource["name"] == "Manager":
                resource["calendar_id"] = "manager"
    for activity in data["activities"]:
        for assignment in activity["assignments"]:
            assignment["duration"] = DURATIONS[activity["element_id"]]
    for gateway in data["gateways"]:
        for branch in gateway["branches"]:
            branch["probability"] = incomplete if branch["flow_id"] == "f_incomplete" else 1 - incomplete
    return SimulationModel.model_validate(data)


async def main() -> None:
    source = bpmn()
    OUT.write_text(source, encoding="utf-8")
    bpmn_xml = normalize_bpmn_for_prosimos(source)
    base = baseline_for_bpmn(bpmn_xml, source_bpmn_xml=source)
    # As-Is: meta' delle richieste torna indietro, il manager autorizza due volte a settimana.
    # To-Be: la richiesta nasce completa (15% di rilavorazione), un delegato autorizza in giornata.
    runs = {
        "as_is": await run("As-Is", bpmn_xml, model(base, incomplete=0.5, manager=TWICE_A_WEEK)),
        "to_be": await run("To-Be · complete request + daily delegate", bpmn_xml, model(base, incomplete=0.15, manager=DAILY)),
    }
    for value in runs.values():
        value["experiments"] = suggest_experiments(value["summary"], value["scenario"]).model_dump(mode="json")
        s = value["summary"]
        print(value["name"], f"ciclo_gg={s['cycle']['avg'] / 86400:.2f}", f"costo={s['cost']['perCase']:.1f}", f"collo={(s.get('bottleneck') or {}).get('name')}")
    (DATA / "hero-runs.json").write_text(json.dumps(finite(runs), ensure_ascii=False, allow_nan=False), encoding="utf-8")
    template = describe_scenario_template(bpmn_xml, source_bpmn_xml=source)
    api = {"simulation_template": template.model_dump(mode="json"), "simulation_provenance": {"has_discovery": False, "elements": []}}
    (DATA / "hero-api.json").write_text(json.dumps(finite(api), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
