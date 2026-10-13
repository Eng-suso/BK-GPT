"""Le evidenze del processo demo: per ogni elemento, le citazioni che lo reggono.

Le citazioni sono quelle del golden set `tests/golden/esaote_ciclo_passivo`
(`expected.json`, `expected_evidence_bindings`), alla lettera: lo script si
ferma se una citazione non si trova nell'intervista. Il processo demo e' la
versione semplice del caso, quindi piu' passi del golden set reggono lo stesso
elemento, e due elementi non hanno fonte: li ha aggiunti il consulente e a
schermo restano ipotesi, non fatti.

Esce `e2e/launch-media/data/demo-evidence.json` e, per il sito in inglese,
`demo-evidence.en.json`: stesse associazioni, citazioni prese alla lettera
dalle interviste tradotte (`data/en/quotes.json`, verificato da
`scripts/launch_media_quotes_en.py`).

Ogni elemento porta il suo riferimento di tracciabilita' (`source_ref`, quello
che il compilatore scrive nella documentazione del nodo) e l'esito entra nel
disegno con la funzione del prodotto (`mark_provenance`): `demo.marked.bpmn` e
`demo.en.marked.bpmn`, dove le ipotesi del consulente sono segnate "da confermare".

    PYTHONPATH=. uv run python scripts/launch_media_demo_evidence.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from backend.workspace_services.bpmn_provenance_marks import mark_provenance

GOLDEN = Path("tests/golden/esaote_ciclo_passivo")
BPMN = Path("e2e/launch-media/data/demo.bpmn")
OUT = Path("e2e/launch-media/data/demo-evidence.json")
EN = Path("e2e/launch-media/data/en")
ROLES_EN = {"Ufficio Tecnico": "Technical Office", "Manutenzione": "Maintenance", "Ufficio Acquisti": "Purchasing Office"}

INTERVIEWS = {
    "a1_laura_conti_ufficio_tecnico.md": ("src-laura-conti", "Laura Conti", "Ufficio Tecnico"),
    "a2_paolo_marchetti_manutenzione.md": ("src-paolo-marchetti", "Paolo Marchetti", "Manutenzione"),
    "a3_francesca_neri_acquisti.md": ("src-francesca-neri", "Francesca Neri", "Ufficio Acquisti"),
}

# elemento del processo demo -> passi del golden set che lo descrivono
BINDINGS = {
    "StartEvent_1": ["rileva_fabbisogno"],
    "Task_Compila": ["ricostruisci_richiesta"],
    "Task_Invia": ["invia_richiesta_ufficio_tecnico", "invia_richiesta_acquisti"],
    "Task_Verifica": ["verifica_lavorabilita"],
    "Decision_Completa": ["richiesta_lavorabile"],
    "Path_Integrazione_Task_Richiedi": ["richiedi_integrazione"],
    # «Sopra una certa cifra devo chiedere una autorizzazione»: non tutte le
    # richieste passano dal responsabile. La soglia e' la lacuna aperta.
    "Decision_Necessaria": ["serve_autorizzazione", "richiedi_autorizzazione"],
    "Task_Valuta": ["richiedi_autorizzazione"],
    # La risposta del responsabile e' l'esito.
    "Decision_Autorizzata": ["autorizza_spesa"],
    "Task_Emetti": ["emetti_ordine"],
    "Event_Emesso": ["emetti_ordine"],
}
# Aggiunti dal consulente nella revisione OMG: nessuna intervista li descrive.
HYPOTHESES_EN = {
    "Path_Integrazione_Task_Integra": "Whoever made the request completes it when Purchasing sends it back: no source describes the step.",
    "Path_Rifiuto_Task_Rifiuto": "The spending rejection: no source says what happens when authorization is denied.",
    "Event_Respinta": "Outcome added with the rejection branch.",
}
CONSULTANT_HYPOTHESES = {
    "Path_Integrazione_Task_Integra": "Chi fa la richiesta la completa quando Acquisti la rimanda indietro: nessuna fonte descrive il passo.",
    "Path_Rifiuto_Task_Rifiuto": "Il rifiuto della spesa: nessuna fonte racconta cosa succede quando l'autorizzazione e' negata.",
    "Event_Respinta": "Esito aggiunto con il ramo di rifiuto.",
}


def source_refs(xml: str) -> dict[str, str]:
    """Il riferimento di tracciabilita' di ogni nodo, dalla sua documentazione."""
    refs = {}
    for element_id, body in re.findall(r'<bpmn:\w+ id="([^"]+)"[^>]*>(.*?)</bpmn:', xml, re.S):
        found = re.search(r'DeliR traceability:\s*(\{.*?\})\s*$', body.split("</bpmn:documentation>")[0], re.S)
        values = [ref for ref in json.loads(found.group(1)).get("source_refs", []) if isinstance(ref, str)] if found else []
        if values:
            refs[element_id] = values[0]
    return refs


def mark(path: Path, elements: list[dict]) -> None:
    """Scrive l'esito di ogni elemento nel disegno, come fa il backend."""
    statuses = {item["source_ref"]: "verified" if item["evidence"] else "unverified" for item in elements}
    xml, counts = mark_provenance(path.read_text(encoding="utf-8"), statuses)
    out = path.with_suffix(".marked.bpmn")
    out.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + xml, encoding="utf-8")
    print(f"ok {out}: {counts}")


def main() -> int:
    expected = json.loads((GOLDEN / "expected.json").read_text(encoding="utf-8"))
    texts = {name: (GOLDEN / "sources" / name).read_text(encoding="utf-8") for name in INTERVIEWS}
    xml = BPMN.read_text(encoding="utf-8")
    labels = dict(re.findall(r'<bpmn:\w+ id="([^"]+)" name="([^"]+)"', xml))
    refs = source_refs(xml)
    by_step: dict[str, list[dict]] = {}
    for binding in expected["expected_evidence_bindings"]:
        by_step.setdefault(binding["element"], []).append(binding)

    missing, elements = [], []
    for element_id, steps in BINDINGS.items():
        evidence = []
        for step in steps:
            for binding in by_step.get(step, []):
                if binding["quote"] not in texts[binding["source"]]:
                    missing.append(f"{element_id}: citazione non trovata in {binding['source']}")
                source_id, person, role = INTERVIEWS[binding["source"]]
                evidence.append({"source_id": source_id, "person": person, "role": role, "quote": binding["quote"]})
        if not evidence:
            missing.append(f"{element_id}: nessuna citazione")
        elements.append({"element_id": element_id, "source_ref": refs.get(element_id), "label": labels.get(element_id, element_id), "status": "fonte", "evidence": evidence})
    for element_id, note in CONSULTANT_HYPOTHESES.items():
        elements.append({"element_id": element_id, "source_ref": refs.get(element_id), "label": labels.get(element_id, element_id), "status": "ipotesi del consulente", "note": note, "evidence": []})

    unknown = [element_id for element_id in (*BINDINGS, *CONSULTANT_HYPOTHESES) if element_id not in labels]
    missing += [f"{item['element_id']}: nessun riferimento di tracciabilita'" for item in elements if not item["source_ref"]]
    if missing or unknown:
        for line in [*missing, *(f"{element_id}: non e' nel BPMN" for element_id in unknown)]:
            print("!", line)
        return 1
    OUT.write_text(
        json.dumps({"elements": elements, "open_gaps": expected["open_gaps"]}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    write_english(elements)
    mark(BPMN, elements)
    mark(BPMN.with_name("demo.en.bpmn"), elements)
    sourced = sum(1 for item in elements if item["status"] == "fonte")
    print(f"ok {OUT}: {sourced} elementi con fonte, {len(CONSULTANT_HYPOTHESES)} ipotesi del consulente")
    return 0


def write_english(elements: list[dict]) -> None:
    """La stessa tabella in inglese: etichette del BPMN inglese, citazioni tradotte."""
    quotes = json.loads((EN / "quotes.json").read_text(encoding="utf-8"))
    xml = BPMN.with_name("demo.en.bpmn").read_text(encoding="utf-8")
    labels = dict(re.findall(r'<bpmn:\w+ id="([^"]+)" name="([^"]+)"', xml))
    english = []
    for item in elements:
        hypothesis = item["status"] != "fonte"
        english.append({
            "element_id": item["element_id"],
            "source_ref": item["source_ref"],
            "label": labels[item["element_id"]],
            "status": "consultant hypothesis" if hypothesis else "source",
            **({"note": HYPOTHESES_EN[item["element_id"]]} if hypothesis else {}),
            "evidence": [evidence | {"role": ROLES_EN[evidence["role"]], "quote": quotes[evidence["quote"]]} for evidence in item["evidence"]],
        })
    out = OUT.with_name("demo-evidence.en.json")
    out.write_text(json.dumps({"elements": english}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"ok {out}")


if __name__ == "__main__":
    sys.exit(main())
