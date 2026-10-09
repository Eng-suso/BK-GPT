"""L'As-Is v3 della demo di lancio: il modello del compilatore, corretto dal consulente.

`e2e/launch-media/data/as-is.compiled.bpmn` e' l'uscita del compilatore del
prodotto sul piano ideale del golden set. E' BPMN valido ma non rispetta le
regole di stile che un consulente BPM applica (e che il video mostra):

1. un gateway fa due domande (completezza + autorizzazione) con tre uscite;
2. i rami di default non sono dichiarati ne' etichettati;
3. tre elementi ricevono piu' flussi senza un merge esplicito;
4. un solo evento di fine per due esiti diversi (merce verificata, urgenza
   regolarizzata), con nomi generici "Start"/"End";
5. corsie in ordine di compilazione, archi sovrapposti.

Qui il modello si riscrive con le stesse attivita' (stessi id, cosi' evidenze e
citazioni restano agganciate): un gateway per domanda, merge espliciti, default
dichiarati, un evento di fine per esito, corsie nell'ordine del flusso.

    python3 scripts/launch_media_asis.py
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import quoteattr

DATA = Path("e2e/launch-media/data")
COMPILED = DATA / "as-is.compiled.bpmn"
OUT = DATA / "as-is.bpmn"

PROCESS_ID = "Process_acquisti_indiretti"
PROCESS_NAME = "Gestione acquisto materiali indiretti e servizi"

# corsia -> (nome, righe)
LANES = {
    "reparto": ("Reparto", 2),
    "ufficio_tecnico": ("Ufficio Tecnico", 1),
    "acquisti": ("Ufficio Acquisti", 3),
    "responsabile_acquisti": ("Responsabile Acquisti", 1),
    "magazzino": ("Magazzino", 1),
    "amministrazione": ("Amministrazione", 1),
}

# id -> (tipo, nome o None per il nome del compilatore, corsia, riga, colonna)
NODES = {
    "StartEvent_1": ("startEvent", "Fabbisogno rilevato", "reparto", 0, 0),
    "rileva_fabbisogno": ("userTask", None, "reparto", 0, 1),
    "urgenza": ("exclusiveGateway", "Linea ferma?", "reparto", 0, 2),
    "invia_richiesta_ufficio_tecnico": ("userTask", None, "reparto", 0, 3),
    "percorso_urgente_chiama_fornitore_diretto": ("userTask", None, "reparto", 1, 3),
    "percorso_urgente_invia_riferimento_ordine_urgente": ("userTask", None, "reparto", 1, 4),
    "gw_merge_richiesta": ("exclusiveGateway", None, "ufficio_tecnico", 0, 5),
    "ricostruisci_richiesta": ("userTask", None, "ufficio_tecnico", 0, 6),
    "invia_richiesta_acquisti": ("userTask", None, "ufficio_tecnico", 0, 7),
    "percorso_urgente_regolarizza_ordine": ("userTask", None, "acquisti", 2, 4),
    "percorso_urgente_gestione_contabile_fattura": ("userTask", None, "amministrazione", 0, 5),
    "EndEvent_urgente": ("endEvent", "Ordine urgente registrato", "amministrazione", 0, 6),
    "verifica_lavorabilita": ("userTask", "Verifica lavorabilità della richiesta", "acquisti", 0, 8),
    "gw_richiesta_completa": ("exclusiveGateway", "Richiesta completa?", "acquisti", 0, 9),
    "percorso_integrazione_richiedi_integrazione": ("userTask", None, "acquisti", 1, 9),
    "gw_serve_autorizzazione": ("exclusiveGateway", "Serve autorizzazione?", "acquisti", 0, 10),
    "percorso_autorizzazione_richiedi_autorizzazione": ("userTask", None, "acquisti", 1, 10),
    "percorso_autorizzazione_autorizza_spesa": ("userTask", None, "responsabile_acquisti", 0, 11),
    "gw_merge_autorizzazione": ("exclusiveGateway", None, "acquisti", 0, 12),
    "seleziona_fornitore": ("userTask", None, "acquisti", 0, 13),
    "emetti_ordine": ("userTask", None, "acquisti", 0, 14),
    "ricevi_merce": ("userTask", None, "magazzino", 0, 15),
    "verifica_merce": ("userTask", None, "reparto", 0, 16),
    "EndEvent_1": ("endEvent", "Merce verificata", "reparto", 0, 17),
}

# (id, sorgente, destinazione, nome, default)
FLOWS = [
    ("Flow_start", "StartEvent_1", "rileva_fabbisogno", None, False),
    ("Flow_rileva_urgenza", "rileva_fabbisogno", "urgenza", None, False),
    ("Flow_urgenza_ordinaria", "urgenza", "invia_richiesta_ufficio_tecnico", "No", True),
    ("Flow_urgenza_linea_ferma", "urgenza", "percorso_urgente_chiama_fornitore_diretto", "Sì", False),
    ("Flow_chiama_riferimento", "percorso_urgente_chiama_fornitore_diretto", "percorso_urgente_invia_riferimento_ordine_urgente", None, False),
    ("Flow_riferimento_regolarizza", "percorso_urgente_invia_riferimento_ordine_urgente", "percorso_urgente_regolarizza_ordine", None, False),
    ("Flow_regolarizza_contabile", "percorso_urgente_regolarizza_ordine", "percorso_urgente_gestione_contabile_fattura", None, False),
    ("Flow_contabile_fine", "percorso_urgente_gestione_contabile_fattura", "EndEvent_urgente", None, False),
    ("Flow_richiesta_merge", "invia_richiesta_ufficio_tecnico", "gw_merge_richiesta", None, False),
    ("Flow_merge_ricostruisci", "gw_merge_richiesta", "ricostruisci_richiesta", None, False),
    ("Flow_ricostruisci_invia", "ricostruisci_richiesta", "invia_richiesta_acquisti", None, False),
    ("Flow_invia_verifica", "invia_richiesta_acquisti", "verifica_lavorabilita", None, False),
    ("Flow_verifica_completa", "verifica_lavorabilita", "gw_richiesta_completa", None, False),
    ("Flow_completa_no", "gw_richiesta_completa", "percorso_integrazione_richiedi_integrazione", "No", False),
    ("Flow_integrazione_merge", "percorso_integrazione_richiedi_integrazione", "gw_merge_richiesta", None, False),
    ("Flow_completa_si", "gw_richiesta_completa", "gw_serve_autorizzazione", "Sì", True),
    ("Flow_autorizzazione_si", "gw_serve_autorizzazione", "percorso_autorizzazione_richiedi_autorizzazione", "Sì", False),
    ("Flow_richiedi_autorizza", "percorso_autorizzazione_richiedi_autorizzazione", "percorso_autorizzazione_autorizza_spesa", None, False),
    ("Flow_autorizza_merge", "percorso_autorizzazione_autorizza_spesa", "gw_merge_autorizzazione", None, False),
    ("Flow_autorizzazione_no", "gw_serve_autorizzazione", "gw_merge_autorizzazione", "No", True),
    ("Flow_merge_seleziona", "gw_merge_autorizzazione", "seleziona_fornitore", None, False),
    ("Flow_seleziona_emetti", "seleziona_fornitore", "emetti_ordine", None, False),
    ("Flow_emetti_ricevi", "emetti_ordine", "ricevi_merce", None, False),
    ("Flow_ricevi_verifica", "ricevi_merce", "verifica_merce", None, False),
    ("Flow_verifica_fine", "verifica_merce", "EndEvent_1", None, False),
]

ROW, COL = 110, 150
POOL_X, POOL_Y, LANE_HEADER = 40, 40, 30
CONTENT_X = POOL_X + LANE_HEADER * 2
TASK_W, TASK_H, GATE, EVENT = 124, 72, 50, 36


def compiled_names() -> dict[str, str]:
    xml = COMPILED.read_text(encoding="utf-8")
    return dict(re.findall(r'<bpmn:userTask id="([^"]+)" name="([^"]+)"', xml))


def size(kind: str) -> tuple[int, int]:
    if kind.endswith("Event"):
        return EVENT, EVENT
    if kind.endswith("Gateway"):
        return GATE, GATE
    return TASK_W, TASK_H


def layout():
    tops, y = {}, POOL_Y
    for lane, (_, rows) in LANES.items():
        tops[lane] = y
        y += rows * ROW
    bounds = {}
    for node_id, (kind, _, lane, row, col) in NODES.items():
        w, h = size(kind)
        cx = CONTENT_X + col * COL + COL / 2
        cy = tops[lane] + row * ROW + ROW / 2
        bounds[node_id] = (cx - w / 2, cy - h / 2, w, h)
    return tops, bounds, y - POOL_Y


def route(src, dst, src_kind, dst_kind):
    sx, sy, sw, sh = src
    dx, dy, dw, dh = dst
    scx, scy, dcx, dcy = sx + sw / 2, sy + sh / 2, dx + dw / 2, dy + dh / 2
    if abs(scy - dcy) < 1:
        return [(sx + sw, scy), (dx, dcy)] if dcx > scx else [(sx, scy), (dx + dw, dcy)]
    if abs(scx - dcx) < 1:
        return [(scx, sy + sh), (dcx, dy)] if dcy > scy else [(scx, sy), (dcx, dy + dh)]
    if dcx < scx:  # ritorno: si scorre sulla propria riga e si entra dal basso
        return [(sx, scy), (dcx, scy), (dcx, dy + dh if dcy < scy else dy)]
    if src_kind.endswith("Gateway"):  # dal vertice del gateway verso la riga del bersaglio
        return [(scx, sy + sh if dcy > scy else sy), (scx, dcy), (dx, dcy)]
    # A L: si esce di lato e si entra dall'alto o dal basso, senza uncini.
    return [(sx + sw, scy), (dcx, scy), (dcx, dy if dcy > scy else dy + dh)]


def main() -> None:
    names = compiled_names()
    tops, bounds, height = layout()
    width = CONTENT_X - POOL_X + 18 * COL + 20
    kinds = {node_id: spec[0] for node_id, spec in NODES.items()}
    incoming = {node_id: [] for node_id in NODES}
    outgoing = {node_id: [] for node_id in NODES}
    for flow_id, source, target, _, _ in FLOWS:
        outgoing[source].append(flow_id)
        incoming[target].append(flow_id)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
        'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
        'id="Definitions_acquisti_indiretti_v3" targetNamespace="https://delir.ai/bpmn">',
        '  <bpmn:collaboration id="Collaboration_acquisti_indiretti">',
        f'    <bpmn:participant id="Participant_acquisti_indiretti" name={quoteattr(PROCESS_NAME)} processRef="{PROCESS_ID}" />',
        "  </bpmn:collaboration>",
        f'  <bpmn:process id="{PROCESS_ID}" name={quoteattr(PROCESS_NAME)} isExecutable="false">',
        f'    <bpmn:laneSet id="{PROCESS_ID}_LaneSet">',
    ]
    for lane, (lane_name, _) in LANES.items():
        lines.append(f'      <bpmn:lane id="{lane}" name={quoteattr(lane_name)}>')
        lines += [f"        <bpmn:flowNodeRef>{n}</bpmn:flowNodeRef>" for n, spec in NODES.items() if spec[2] == lane]
        lines.append("      </bpmn:lane>")
    lines.append("    </bpmn:laneSet>")

    defaults = {source: flow_id for flow_id, source, _, _, is_default in FLOWS if is_default}
    for node_id, (kind, name, _, _, _) in NODES.items():
        label = name or names.get(node_id, "")
        attrs = f'id="{node_id}"' + (f" name={quoteattr(label)}" if label else "")
        if node_id in defaults:
            attrs += f' default="{defaults[node_id]}"'
        lines.append(f"    <bpmn:{kind} {attrs}>")
        lines += [f"      <bpmn:incoming>{f}</bpmn:incoming>" for f in incoming[node_id]]
        lines += [f"      <bpmn:outgoing>{f}</bpmn:outgoing>" for f in outgoing[node_id]]
        lines.append(f"    </bpmn:{kind}>")
    for flow_id, source, target, name, _ in FLOWS:
        label = f" name={quoteattr(name)}" if name else ""
        lines.append(f'    <bpmn:sequenceFlow id="{flow_id}"{label} sourceRef="{source}" targetRef="{target}" />')
    lines.append("  </bpmn:process>")

    lines += [
        '  <bpmndi:BPMNDiagram id="Diagram_acquisti_indiretti">',
        '    <bpmndi:BPMNPlane id="Plane_acquisti_indiretti" bpmnElement="Collaboration_acquisti_indiretti">',
        f'      <bpmndi:BPMNShape id="Participant_acquisti_indiretti_di" bpmnElement="Participant_acquisti_indiretti" isHorizontal="true">'
        f'<dc:Bounds x="{POOL_X}" y="{POOL_Y}" width="{width}" height="{height}" /></bpmndi:BPMNShape>',
    ]
    for lane, (_, rows) in LANES.items():
        lines.append(
            f'      <bpmndi:BPMNShape id="{lane}_di" bpmnElement="{lane}" isHorizontal="true">'
            f'<dc:Bounds x="{POOL_X + LANE_HEADER}" y="{tops[lane]}" width="{width - LANE_HEADER}" height="{rows * ROW}" /></bpmndi:BPMNShape>'
        )
    for node_id, (x, y, w, h) in bounds.items():
        kind = kinds[node_id]
        marker = ' isMarkerVisible="true"' if kind.endswith("Gateway") else ""
        label = ""
        if kind.endswith("Event") or (kind.endswith("Gateway") and (NODES[node_id][1])):
            label = f'<bpmndi:BPMNLabel><dc:Bounds x="{x + w / 2 - 55:.0f}" y="{y - 30 if kind.endswith("Gateway") else y + h + 6:.0f}" width="110" height="26" /></bpmndi:BPMNLabel>'
        lines.append(
            f'      <bpmndi:BPMNShape id="{node_id}_di" bpmnElement="{node_id}"{marker}>'
            f'<dc:Bounds x="{x:.0f}" y="{y:.0f}" width="{w}" height="{h}" />{label}</bpmndi:BPMNShape>'
        )
    for flow_id, source, target, name, _ in FLOWS:
        points = route(bounds[source], bounds[target], kinds[source], kinds[target])
        waypoints = "".join(f'<di:waypoint x="{px:.0f}" y="{py:.0f}" />' for px, py in points)
        label = ""
        if name:
            (x0, y0), (x1, y1) = points[0], points[1]
            lx, ly = (x0 + 8, y0 + 4) if abs(x0 - x1) < 1 else (x0 + 10, y0 - 22)
            label = f'<bpmndi:BPMNLabel><dc:Bounds x="{lx:.0f}" y="{ly:.0f}" width="24" height="16" /></bpmndi:BPMNLabel>'
        lines.append(f'      <bpmndi:BPMNEdge id="{flow_id}_di" bpmnElement="{flow_id}">{waypoints}{label}</bpmndi:BPMNEdge>')
    lines += ["    </bpmndi:BPMNPlane>", "  </bpmndi:BPMNDiagram>", "</bpmn:definitions>", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"As-Is v3: {len(NODES)} nodi, {len(FLOWS)} flussi -> {OUT}")


if __name__ == "__main__":
    main()
