"""Il caso semplice dei video della landing: una richiesta di acquisto, end-to-end.

Un processo che si legge in un colpo d'occhio (tre corsie, cinque attivita',
una decisione con il suo giro di rilavorazione) su cui i video mostrano tutto
il prodotto: fonti, As-Is con le evidenze, lacune, review, simulazione,
scenari, consegna al cliente. Le fonti (due interviste e la procedura) sono in
`e2e/launch-media/simple/case.ts`; qui il disegno e le simulazioni, con lo
stesso motore e la stessa pipeline del prodotto.

Esce in `e2e/launch-media/data/simple/`:
- `it.bpmn`, `en.bpmn`: stesso processo e stessi id, nomi nelle due lingue;
- `runs.json`: As-Is e To-Be con summary e replay (seed fisso);
- `scenarios.json`: AS-IS, A e B ripetuti 6 volte sullo stesso seed comune;
- `api.json`: template, provenienza dei parametri e compatibilita' per il pannello.

    # Prosimos: ops/prosimos/runner (http://127.0.0.1:5000)
    PYTHONPATH=. uv run python scripts/launch_media_simple_case.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

sys.path.insert(0, str(Path(__file__).resolve().parent))

from launch_media_simulate import WORKDAY, finite, lognormal, normal  # noqa: E402

from backend.simulation.advisor import suggest_experiments  # noqa: E402
from backend.simulation.compatibility import bpmn_compatibility_report  # noqa: E402
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos  # noqa: E402
from backend.simulation.ir.model import SimulationModel  # noqa: E402
from backend.simulation.log_processor import activity_name_to_element_id, process_prosimos_log  # noqa: E402
from backend.simulation.models import ProsimosSimulationRequest  # noqa: E402
from backend.simulation.prosimos_adapter import run_prosimos_simulation  # noqa: E402
from backend.simulation.result_parser import with_output_files  # noqa: E402
from backend.simulation.scenario_builder import (  # noqa: E402
    baseline_for_bpmn,
    build_prosimos_scenario_from_model,
    describe_scenario_template,
)

OUT = Path("e2e/launch-media/data/simple")
SEED = 20261021
TOTAL_CASES = 300
START = "2026-09-07T08:00:00+02:00"
REPLICATIONS = 6

# Le fonti del caso (stessi id di case.ts).
SOURCES = {
    "francesca": ("src-francesca-neri", "Intervista Francesca Neri · Ufficio Acquisti"),
    "paolo": ("src-paolo-marchetti", "Intervista Paolo Marchetti · Manutenzione"),
    "procedura": ("src-procedura-acquisti", "Procedura acquisti v3.pdf"),
}

POOL = ("Participant_richiesta", "Process_richiesta")
LANE_H = 150
POOL_W = 1180

NAMES = {
    "it": {
        "pool": "Richiesta di acquisto",
        "requester": "Richiedente", "purchasing": "Ufficio Acquisti", "manager": "Responsabile",
        "start": "Fabbisogno rilevato", "send_request": "Invia richiesta d'acquisto", "complete_request": "Completa la richiesta",
        "check_request": "Verifica la richiesta", "gw_complete": "Richiesta completa?", "issue_po": "Emetti l'ordine",
        "end": "Ordine inviato", "approve_spend": "Autorizza la spesa", "yes": "Sì", "no": "No",
    },
    "en": {
        "pool": "Purchase request",
        "requester": "Requester", "purchasing": "Purchasing", "manager": "Manager",
        "start": "Need spotted", "send_request": "Send purchase request", "complete_request": "Complete the request",
        "check_request": "Check the request", "gw_complete": "Request complete?", "issue_po": "Issue the order",
        "end": "Order sent", "approve_spend": "Approve spend", "yes": "Yes", "no": "No",
    },
}

LANES = {"requester": 0, "purchasing": 150, "manager": 300}

# id -> (tipo, corsia, x, y) in alto a sinistra
NODES = {
    "start": ("startEvent", "requester", 90, 57),
    "send_request": ("userTask", "requester", 170, 35),
    "complete_request": ("userTask", "requester", 480, 35),
    "check_request": ("userTask", "purchasing", 330, 185),
    "gw_complete": ("exclusiveGateway", "purchasing", 515, 200),
    "issue_po": ("userTask", "purchasing", 800, 185),
    "end": ("endEvent", "purchasing", 1000, 207),
    "approve_spend": ("userTask", "manager", 640, 335),
}

FLOWS = [
    ("f_start", "start", "send_request", None, [(126, 75), (170, 75)]),
    ("f_send", "send_request", "check_request", None, [(230, 115), (230, 225), (330, 225)]),
    ("f_check", "check_request", "gw_complete", None, [(450, 225), (515, 225)]),
    ("f_incomplete", "gw_complete", "complete_request", "no", [(540, 200), (540, 115)]),
    ("f_back", "complete_request", "check_request", None, [(480, 75), (390, 75), (390, 185)]),
    ("f_complete", "gw_complete", "approve_spend", "yes", [(540, 250), (540, 375), (640, 375)]),
    ("f_approved", "approve_spend", "issue_po", None, [(760, 375), (860, 375), (860, 265)]),
    ("f_end", "issue_po", "end", None, [(920, 225), (1000, 225)]),
]
FLOW_LABELS = {"f_incomplete": (548, 140), "f_complete": (548, 290)}

# Gli attributi del pannello Proprieta' e la citazione che regge ogni attivita'.
DETAILS = {
    "it": {
        "send_request": {"owner": "Paolo Marchetti", "office": "Manutenzione", "systems": "Mail", "files": "procedura;paolo",
                         "quote": ("paolo", "Quando mi serve qualcosa mando una mail ad Acquisti con quello che mi serve.")},
        "check_request": {"owner": "Francesca Neri", "office": "Ufficio Acquisti", "systems": "Mail, gestionale",
                          "rules": "Completa: codice articolo, quantità e centro di costo.", "files": "francesca;procedura",
                          "quote": ("francesca", "Controllo che ci siano codice articolo, quantità e centro di costo.")},
        "complete_request": {"owner": "Paolo Marchetti", "office": "Manutenzione", "systems": "Mail",
                             "risks": "Una richiesta su due torna indietro (stima di Francesca, non misurata).", "files": "francesca",
                             "quote": ("francesca", "Una richiesta su due arriva senza codice o senza quantità, e la rimando indietro.")},
        "approve_spend": {"owner": "Laura Conti", "office": "Responsabile Acquisti", "systems": "Mail",
                          "rules": "Serve sopra una soglia di importo che nessuna fonte dichiara: domanda aperta.",
                          "risks": "Nessun sostituto: quando la responsabile non c'è la richiesta resta ferma.", "files": "francesca;procedura",
                          "quote": ("francesca", "Laura firma il martedì e il giovedì, quando è in sede.")},
        "issue_po": {"owner": "Francesca Neri", "office": "Ufficio Acquisti", "systems": "Gestionale", "files": "francesca",
                     "quote": ("francesca", "Con la firma emetto l'ordine nel gestionale e lo mando al fornitore.")},
    },
    "en": {
        "send_request": {"owner": "Paolo Marchetti", "office": "Maintenance", "systems": "Email", "files": "procedura;paolo",
                         "quote": ("paolo", "When I need something I email Purchasing with what I need.")},
        "check_request": {"owner": "Francesca Neri", "office": "Purchasing", "systems": "Email, ERP",
                          "rules": "Complete: item code, quantity and cost centre.", "files": "francesca;procedura",
                          "quote": ("francesca", "I check there is an item code, a quantity and a cost centre.")},
        "complete_request": {"owner": "Paolo Marchetti", "office": "Maintenance", "systems": "Email",
                             "risks": "One request in two comes back (Francesca's estimate, not measured).", "files": "francesca",
                             "quote": ("francesca", "One request in two arrives without a code or a quantity, and I send it back.")},
        "approve_spend": {"owner": "Laura Conti", "office": "Purchasing Manager", "systems": "Email",
                          "rules": "Needed above an amount threshold that no source states: open question.",
                          "risks": "No stand-in: when the manager is away the request waits.", "files": "francesca;procedura",
                          "quote": ("francesca", "Laura signs on Tuesdays and Thursdays, when she is in the office.")},
        "issue_po": {"owner": "Francesca Neri", "office": "Purchasing", "systems": "ERP", "files": "francesca",
                     "quote": ("francesca", "Once it is signed I issue the order in the ERP and send it to the supplier.")},
    },
}
WHO = {"it": {"francesca": "Francesca Neri", "paolo": "Paolo Marchetti"}, "en": {"francesca": "Francesca Neri", "paolo": "Paolo Marchetti"}}
SOURCE_LABEL = {
    "it": {"francesca": SOURCES["francesca"][1], "paolo": SOURCES["paolo"][1], "procedura": SOURCES["procedura"][1]},
    "en": {"francesca": "Interview Francesca Neri · Purchasing", "paolo": "Interview Paolo Marchetti · Maintenance", "procedura": "Purchasing procedure v3.pdf"},
}


def size(kind: str) -> tuple[int, int]:
    return {"startEvent": (36, 36), "endEvent": (36, 36), "exclusiveGateway": (50, 50)}.get(kind, (120, 80))


def bpmn(lang: str) -> str:
    names = NAMES[lang]
    pid, proc = POOL
    incoming: dict[str, list[str]] = {}
    outgoing: dict[str, list[str]] = {}
    for fid, src, dst, *_ in FLOWS:
        outgoing.setdefault(src, []).append(fid)
        incoming.setdefault(dst, []).append(fid)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
        'xmlns:delir="https://delir.app/schema/bpmn/1.0" id="Definitions_richiesta" targetNamespace="https://delir.ai/bpmn">',
        f'  <bpmn:collaboration id="Collaboration_richiesta"><bpmn:participant id="{pid}" name={quoteattr(names["pool"])} processRef="{proc}" /></bpmn:collaboration>',
        f'  <bpmn:process id="{proc}" name={quoteattr(names["pool"])} isExecutable="false">',
        f'    <bpmn:laneSet id="{proc}_lanes">',
    ]
    for lane in LANES:
        refs = "".join(f"<bpmn:flowNodeRef>{n}</bpmn:flowNodeRef>" for n, v in NODES.items() if v[1] == lane)
        lines.append(f'      <bpmn:lane id="{lane}" name={quoteattr(names[lane])}>{refs}</bpmn:lane>')
    lines.append("    </bpmn:laneSet>")
    for nid, (kind, *_rest) in NODES.items():
        flows = "".join(f"<bpmn:incoming>{f}</bpmn:incoming>" for f in incoming.get(nid, []))
        flows += "".join(f"<bpmn:outgoing>{f}</bpmn:outgoing>" for f in outgoing.get(nid, []))
        default = ' default="f_complete"' if nid == "gw_complete" else ""
        attrs, doc = "", ""
        detail = DETAILS[lang].get(nid)
        if detail:
            files = "; ".join(SOURCE_LABEL[lang][key] for key in detail["files"].split(";"))
            for key in ("owner", "office", "rules", "risks", "systems"):
                if detail.get(key):
                    attrs += f" delir:{key}={quoteattr(detail[key])}"
            attrs += f" delir:files={quoteattr(files)}"
            who, quote = detail["quote"]
            trace = json.dumps({"source_refs": [f"steps:{nid}"]})
            doc = f"<bpmn:documentation>{escape(f'«{quote}» ({WHO[lang][who]})')}\n\nDeliR traceability: {escape(trace)}</bpmn:documentation>"
        lines.append(f'    <bpmn:{kind} id="{nid}" name={quoteattr(names[nid])}{default}{attrs}>{doc}{flows}</bpmn:{kind}>')
    for fid, src, dst, label, _ in FLOWS:
        named = f" name={quoteattr(names[label])}" if label else ""
        lines.append(f'    <bpmn:sequenceFlow id="{fid}"{named} sourceRef="{src}" targetRef="{dst}" />')
    lines.append("  </bpmn:process>")
    lines.append('  <bpmndi:BPMNDiagram id="Diagram_richiesta"><bpmndi:BPMNPlane id="Plane_richiesta" bpmnElement="Collaboration_richiesta">')
    lines.append(f'    <bpmndi:BPMNShape id="{pid}_di" bpmnElement="{pid}" isHorizontal="true"><dc:Bounds x="0" y="0" width="{POOL_W}" height="{LANE_H * len(LANES)}" /></bpmndi:BPMNShape>')
    for lane, y in LANES.items():
        lines.append(f'    <bpmndi:BPMNShape id="{lane}_di" bpmnElement="{lane}" isHorizontal="true"><dc:Bounds x="30" y="{y}" width="{POOL_W - 30}" height="{LANE_H}" /></bpmndi:BPMNShape>')
    for nid, (kind, _lane, x, y) in NODES.items():
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


def declared(*who: str, note: str) -> dict:
    return {
        "origin": "declared",
        "confidence": "medium",
        "sources": [{"kind": "source", "id": SOURCES[w][0], "label": SOURCES[w][1]} for w in who],
        "note": note,
    }


def assumed(note: str) -> dict:
    return {"origin": "manual", "confidence": "low", "sources": [], "note": note}


# Durate (minuti): Francesca le dice per le sue attivita', le altre sono stime del consulente.
DURATIONS = {
    "send_request": (normal(5, 1), assumed("Stima del consulente.")),
    "check_request": (normal(10, 3), declared("francesca", note="«Dieci minuti, se la richiesta è completa.»")),
    "complete_request": (lognormal(30, 20, 240), declared("francesca", note="«Mezz'ora, a volte giorni se non trovano il codice.»")),
    "approve_spend": (normal(3, 1), assumed("La firma in sé richiede pochi minuti: stima del consulente.")),
    "issue_po": (normal(15, 4), declared("francesca", note="«Un quarto d'ora per ordine.»")),
}
RESOURCES = {"Richiedente": (6, 38.0), "Ufficio Acquisti": (1, 45.0), "Responsabile": (1, 70.0)}
TWICE_A_WEEK = [
    {"from_day": "TUESDAY", "to_day": "TUESDAY", "begin": "16:00:00.000", "end": "17:00:00.000"},
    {"from_day": "THURSDAY", "to_day": "THURSDAY", "begin": "16:00:00.000", "end": "17:00:00.000"},
]
DAILY = [{"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "16:00:00.000", "end": "17:00:00.000"}]


def model(base: SimulationModel, *, incomplete: float, daily: bool) -> SimulationModel:
    data = base.model_dump(mode="json")
    data["arrival"]["interarrival"] = {"kind": "exponential", "mean": WORKDAY / 5, "minimum": 0.0, "maximum": WORKDAY}
    data["arrival"]["provenance"] = assumed("Circa 5 richieste al giorno: assunzione del consulente.")
    calendar = ("responsabile-con-delega", "Autorizzazione ogni giorno (delega)", DAILY) if daily else ("responsabile-martedi-giovedi", "Firma il martedì e il giovedì", TWICE_A_WEEK)
    data["calendars"].append({"id": calendar[0], "name": calendar[1], "periods": calendar[2]})
    for pool in data["pools"]:
        for resource in pool["resources"]:
            amount, cost = RESOURCES[resource["name"]]
            resource["amount"], resource["cost_per_hour"] = amount, cost
            resource["provenance"] = assumed("Persone e costo orario: assunzione del consulente.")
            if resource["name"] == "Responsabile":
                resource["calendar_id"] = calendar[0]
                resource["provenance"] = (
                    {**declared("francesca", note="To-Be: un delegato firma ogni giorno: assunzione del consulente."), "origin": "manual", "confidence": "low"}
                    if daily
                    else declared("francesca", note="«Laura firma il martedì e il giovedì, quando è in sede.»")
                )
    for activity in data["activities"]:
        duration, provenance = DURATIONS[activity["element_id"]]
        for assignment in activity["assignments"]:
            assignment["duration"] = duration
            assignment["provenance"] = provenance
    for gateway in data["gateways"]:
        provenance = (
            declared("francesca", note="«Una richiesta su due arriva senza codice o senza quantità.»")
            if incomplete == 0.5
            else {**declared("francesca", note="To-Be: campi obbligatori, rilavorazione stimata al 15%."), "origin": "manual", "confidence": "low"}
        )
        for branch in gateway["branches"]:
            branch["probability"] = incomplete if branch["flow_id"] == "f_incomplete" else 1 - incomplete
            branch["provenance"] = provenance
    return SimulationModel.model_validate(data)


async def simulate(bpmn_xml: str, sim: SimulationModel, seed: int) -> tuple[dict, dict, dict]:
    scenario = build_prosimos_scenario_from_model(bpmn_xml=bpmn_xml, model=sim)
    result = with_output_files(
        await run_prosimos_simulation(ProsimosSimulationRequest(bpmn_xml=bpmn_xml, scenario=scenario, total_cases=TOTAL_CASES, start_date=START, seed=seed))
    )
    if not result.event_log_csv:
        raise RuntimeError("Prosimos non ha restituito il log")
    summary, replay = process_prosimos_log(
        result.event_log_csv,
        normalized_bpmn_xml=bpmn_xml,
        scenario_payload=scenario.payload,
        prosimos_stats=result.payload,
        name_to_element_id=activity_name_to_element_id(bpmn_xml),
    )
    return summary, replay, {"scenario": scenario.payload, "result": result.payload}


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for lang in NAMES:
        (OUT / f"{lang}.bpmn").write_text(bpmn(lang), encoding="utf-8")
    source = bpmn("it")
    bpmn_xml = normalize_bpmn_for_prosimos(source)
    base = baseline_for_bpmn(bpmn_xml, source_bpmn_xml=source)
    # As-Is: una richiesta su due torna indietro, la responsabile firma due volte a settimana.
    # A: solo la delega (firma ogni giorno). B: delega + richiesta con campi obbligatori (15% di rilavorazione).
    scenarios = {
        "AS-IS": ("Situazione attuale", model(base, incomplete=0.5, daily=False)),
        "A": ("Delega giornaliera", model(base, incomplete=0.5, daily=True)),
        "B": ("Richiesta completa + delega", model(base, incomplete=0.15, daily=True)),
    }
    runs = {}
    for key, label, name in (("as_is", "AS-IS", "As-Is · validato"), ("to_be", "B", "To-Be · richiesta completa + delega")):
        sim = scenarios[label][1]
        summary, replay, raw = await simulate(bpmn_xml, sim, SEED)
        runs[key] = {
            "name": name, "model": sim.model_dump(mode="json"), **raw, "summary": summary, "replay": replay,
            "request": {"total_cases": TOTAL_CASES, "start_date": START, "seed": SEED},
            "experiments": suggest_experiments(summary, raw["scenario"]).model_dump(mode="json"),
        }
        print(key, f"ciclo_gg={summary['cycle']['avg'] / 86400:.2f}", f"costo={summary['cost']['perCase']:.1f}",
              f"collo={(summary.get('bottleneck') or {}).get('name')}")
    (OUT / "runs.json").write_text(json.dumps(finite(runs), ensure_ascii=False, allow_nan=False), encoding="utf-8")

    out = {"seed": SEED, "total_cases": TOTAL_CASES, "scenarios": []}
    for label, (name, sim) in scenarios.items():
        reps = []
        for index in range(REPLICATIONS):
            summary, _replay, _raw = await simulate(bpmn_xml, sim, SEED + index)
            reps.append({"seed": SEED + index, "summary": summary})
        print(label, [round(r["summary"]["cycle"]["avg"] / 86400, 2) for r in reps])
        out["scenarios"].append({"label": label, "name": name, "model": sim.model_dump(mode="json"), "runs": reps})
    (OUT / "scenarios.json").write_text(json.dumps(finite(out), ensure_ascii=False, allow_nan=False), encoding="utf-8")

    template = describe_scenario_template(bpmn_xml, source_bpmn_xml=source)
    api = {
        "simulation_template": template.model_dump(mode="json"),
        "simulation_provenance": {"has_discovery": True, "elements": []},
        "simulation_compatibility": bpmn_compatibility_report(source).model_dump(mode="json"),
    }
    (OUT / "api.json").write_text(json.dumps(finite(api), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
