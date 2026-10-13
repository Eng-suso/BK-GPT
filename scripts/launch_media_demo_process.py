"""Il processo demo dei video: la "Richiesta d'acquisto" del video hero, in italiano.

Il processo e' quello gia' fatto per l'hero (`e2e/launch-media/data/hero.bpmn`,
`scripts/launch_media_hero_process.py`): una pool, tre corsie, cinque
attivita', una decisione con il suo giro di rilavorazione, gia' simulato con
Prosimos. Qui si tengono gli stessi id (le run restano agganciate) e si cambia
solo cio' che serve alla demo in italiano e a OMG BPMN 2.0:

- nomi in italiano;
- un gateway di merge davanti a "Verifica la richiesta", dove rientra il ritorno;
- la condizione sul ramo "No" (ogni uscita non di default di un gateway
  esclusivo ne ha una, OMG 10.5.2), in linguaggio naturale (tExpression).

Poi layout enterprise del prodotto, lint visivo e schema XSD ufficiale OMG.
Esce `e2e/launch-media/data/demo.bpmn`.

    PYTHONPATH=. uv run python scripts/launch_media_demo_process.py
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from lxml import etree

from backend.bpmn.canvas_layout import apply_enterprise_layout, lint_visual_model

HERO = Path("e2e/launch-media/data/hero.bpmn")
OUT = Path("e2e/launch-media/data/demo.bpmn")
# Lo schema ufficiale OMG BPMN 2.0 (BPMN20.xsd e gli import DI/DC), da bpmn-moddle.
OMG_XSD = Path("frontend/node_modules/bpmn-moddle/resources/bpmn/xsd/BPMN20.xsd")

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
PROCESS_NAME = "Richiesta d'acquisto"

# id -> nome italiano (le parole del caso acquisti, come in heroLocale.ts)
NAMES = {
    "Participant_hero": PROCESS_NAME,
    "Process_hero": PROCESS_NAME,
    "requester": "Reparto",
    "purchasing": "Ufficio Acquisti",
    "manager": "Responsabile Acquisti",
    "start": "Fabbisogno rilevato",
    "send_request": "Invia richiesta ad Acquisti",
    "check_request": "Verifica la richiesta",
    "gw_complete": "Richiesta completa?",
    "complete_request": "Completa la richiesta",
    "approve_spend": "Autorizza la spesa",
    "issue_po": "Emetti l'ordine al fornitore",
    "end": "Ordine inviato",
    "f_complete": "Sì",
    "f_incomplete": "No",
}
MERGE = "gw_check_merge"
NO_CONDITION = "mancano dati nella richiesta"


def q(name: str) -> str:
    return f"{{{BPMN}}}{name}"


def demo_semantics() -> str:
    root = ET.fromstring(HERO.read_text(encoding="utf-8"))
    for diagram in root.findall(f"{{{BPMNDI}}}BPMNDiagram"):
        root.remove(diagram)  # il layout lo rifa' il prodotto
    by_id = {e.get("id"): e for e in root.iter() if e.get("id")}
    for element_id, name in NAMES.items():
        by_id[element_id].set("name", name)

    # Il ritorno da "Completa la richiesta" rientra da un merge esplicito.
    process = by_id["Process_hero"]
    check = by_id["check_request"]
    merge = ET.Element(q("exclusiveGateway"), {"id": MERGE})
    for flow_id in ("f_send", "f_back"):
        by_id[flow_id].set("targetRef", MERGE)
        ET.SubElement(merge, q("incoming")).text = flow_id
    ET.SubElement(merge, q("outgoing")).text = "f_merge"
    for incoming in check.findall(q("incoming")):
        check.remove(incoming)
    entry = ET.Element(q("incoming"))
    entry.text = "f_merge"
    check.insert(0, entry)
    process.insert(list(process).index(check), merge)
    process.append(ET.Element(q("sequenceFlow"), {"id": "f_merge", "sourceRef": MERGE, "targetRef": "check_request"}))
    lane_ref = ET.Element(q("flowNodeRef"))
    lane_ref.text = MERGE
    by_id["purchasing"].insert(0, lane_ref)

    condition = ET.SubElement(by_id["f_incomplete"], q("conditionExpression"), {f"{{{XSI}}}type": "bpmn:tExpression"})
    condition.text = NO_CONDITION
    ET.register_namespace("bpmn", BPMN)
    ET.register_namespace("xsi", XSI)
    return ET.tostring(root, encoding="unicode")


def main() -> int:
    xml = apply_enterprise_layout(demo_semantics(), process_name=PROCESS_NAME)
    problems = list(lint_visual_model(ET.fromstring(xml))["issues"])
    schema = etree.XMLSchema(etree.parse(str(OMG_XSD)))
    if not schema.validate(etree.fromstring(xml.encode())):
        problems += [f"XSD OMG riga {e.line}: {e.message}" for e in schema.error_log]
    for line in problems:
        print("!", line)
    if problems:
        return 1
    OUT.write_text(xml, encoding="utf-8")
    print(f"ok {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
