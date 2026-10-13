"""Le evidenze del processo demo: per ogni elemento, le citazioni che lo reggono.

Le citazioni sono quelle del golden set `tests/golden/esaote_ciclo_passivo`
(`expected.json`, `expected_evidence_bindings`), alla lettera: lo script si
ferma se una citazione non si trova nell'intervista. Il processo demo e' la
versione semplice del caso, quindi piu' passi del golden set reggono lo stesso
elemento, e due elementi non hanno fonte: li ha aggiunti il consulente e a
schermo restano ipotesi, non fatti.

Esce `e2e/launch-media/data/demo-evidence.json`.

    python3 scripts/launch_media_demo_evidence.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

GOLDEN = Path("tests/golden/esaote_ciclo_passivo")
BPMN = Path("e2e/launch-media/data/demo.bpmn")
OUT = Path("e2e/launch-media/data/demo-evidence.json")

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
CONSULTANT_HYPOTHESES = {
    "Path_Integrazione_Task_Integra": "Chi fa la richiesta la completa quando Acquisti la rimanda indietro: nessuna fonte descrive il passo.",
    "Path_Rifiuto_Task_Rifiuto": "Il rifiuto della spesa: nessuna fonte racconta cosa succede quando l'autorizzazione e' negata.",
    "Event_Respinta": "Esito aggiunto con il ramo di rifiuto.",
}


def main() -> int:
    expected = json.loads((GOLDEN / "expected.json").read_text(encoding="utf-8"))
    texts = {name: (GOLDEN / "sources" / name).read_text(encoding="utf-8") for name in INTERVIEWS}
    xml = BPMN.read_text(encoding="utf-8")
    labels = dict(re.findall(r'<bpmn:\w+ id="([^"]+)" name="([^"]+)"', xml))
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
        elements.append({"element_id": element_id, "label": labels.get(element_id, element_id), "status": "fonte", "evidence": evidence})
    for element_id, note in CONSULTANT_HYPOTHESES.items():
        elements.append({"element_id": element_id, "label": labels.get(element_id, element_id), "status": "ipotesi del consulente", "note": note, "evidence": []})

    unknown = [element_id for element_id in (*BINDINGS, *CONSULTANT_HYPOTHESES) if element_id not in labels]
    if missing or unknown:
        for line in [*missing, *(f"{element_id}: non e' nel BPMN" for element_id in unknown)]:
            print("!", line)
        return 1
    OUT.write_text(
        json.dumps({"elements": elements, "open_gaps": expected["open_gaps"]}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    sourced = sum(1 for item in elements if item["status"] == "fonte")
    print(f"ok {OUT}: {sourced} elementi con fonte, {len(CONSULTANT_HYPOTHESES)} ipotesi del consulente")
    return 0


if __name__ == "__main__":
    sys.exit(main())
