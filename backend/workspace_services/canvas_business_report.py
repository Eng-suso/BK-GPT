from __future__ import annotations

import re


TECHNICAL_TERMS = {
    "bpmnsemanticmodel": "struttura del processo",
    "processunderstanding": "lettura del processo",
    "gateway": "punto di decisione",
    "sequence flow": "collegamento tra passaggi",
    "sequenceflow": "collegamento tra passaggi",
    "lane": "ruolo responsabile",
    "dataobjectreference": "documento o informazione",
    "data object": "documento o informazione",
    "xml": "disegno del processo",
    "diagram interchange bpmn": "informazioni grafiche del disegno",
    "sourceref": "collegamento di partenza",
    "targetref": "collegamento di arrivo",
    "node": "passaggio",
}


def canvas_business_report(validation_result: dict) -> dict:
    issues = [_business_text(item) for item in validation_result.get("issues") or []]
    warnings = [_business_text(item) for item in validation_result.get("warnings") or []]
    counts = validation_result.get("counts") or {}
    coverage = validation_result.get("coverage") or {}

    return {
        "summary": _summary(validation_result, issues, warnings),
        "problems_to_fix": _unique(issues),
        "points_to_check": _unique(warnings),
        "process_view": {
            "passaggi": counts.get("flow_nodes", 0),
            "collegamenti": counts.get("sequence_flows", 0),
            "ruoli": counts.get("lanes", 0),
            "punti_di_decisione": counts.get("gateways", 0),
            "documenti_o_informazioni": counts.get("data_objects", 0),
            "note": counts.get("annotations", 0),
        },
        "coverage": {
            "struttura_del_processo_disponibile": bool(coverage.get("semantic_model_available")),
            "lettura_del_processo_disponibile": bool(coverage.get("process_understanding_available")),
            "passaggi_non_ritrovati": coverage.get("missing_semantic_nodes") or [],
            "ruoli_non_ritrovati": coverage.get("missing_lanes") or [],
        },
        "next_actions": _next_actions(issues, warnings),
    }


def construction_business_report(payload: dict) -> dict:
    operation = payload.get("operation")
    validation = payload.get("validation") or {}
    diff_added = payload.get("added") or []
    diff_removed = payload.get("removed") or []
    diff_changed = payload.get("changed") or []

    if operation == "prepare_plan":
        gaps = payload.get("unresolved_gaps") or []
        return {
            "summary": "Ho preparato il piano di lavoro sul disegno del processo.",
            "points_to_check": [_business_text(item) for item in gaps],
            "next_actions": ["Rivedere il piano e confermare se procedere con una bozza."],
        }

    if operation in {"generate_preview", "validate_preview"}:
        return {
            "summary": "Ho preparato una bozza del disegno del processo.",
            "quality_check": canvas_business_report(validation) if validation else {},
            "next_actions": ["Controllare la bozza prima di salvarla come versione del processo."],
        }

    if operation == "compare_with_current":
        return {
            "summary": "Ho confrontato la bozza con il disegno attuale.",
            "changes": {
                "passaggi_aggiunti": [_element_label(item) for item in diff_added],
                "passaggi_rimossi": [_element_label(item) for item in diff_removed],
                "passaggi_modificati": [_element_label(item.get("after", item)) for item in diff_changed],
            },
            "quality_check": canvas_business_report(payload.get("validation") or {}) if payload.get("validation") else {},
            "next_actions": ["Confermare solo se le differenze rappresentano il processo reale."],
        }

    if operation == "apply_approved_preview":
        return {
            "summary": "Ho salvato la nuova versione del disegno del processo.",
            "quality_check": canvas_business_report(validation) if validation else {},
            "next_actions": ["Rivedere il canvas con il team per confermare i punti ancora aperti."],
        }

    return {"summary": "Operazione sul disegno del processo completata.", "next_actions": []}


def _summary(validation_result: dict, issues: list[str], warnings: list[str]) -> str:
    if issues:
        return "Il disegno del processo ha alcuni problemi da correggere prima di considerarlo affidabile."
    if warnings:
        return "Il disegno del processo e utilizzabile, ma ci sono punti da verificare con il team."
    if validation_result:
        return "Il disegno del processo risulta coerente con le informazioni disponibili."
    return "Controllo del processo non disponibile."


def _business_text(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\b[A-Za-z]+_[A-Za-z0-9_]+\b", "riferimento interno", text)
    phrase_replacements = {
        "BPMNSemanticModel non disponibile": "Manca la struttura del processo di riferimento",
        "ProcessUnderstanding non disponibile": "Manca la lettura del processo di riferimento",
        "validazione semantica limitata": "il controllo puo essere solo parziale",
        "Diagram Interchange BPMN mancante": "Mancano alcune informazioni grafiche del disegno",
        "XML BPMN": "disegno del processo",
        "BPMN": "processo",
        "Nodo": "Passaggio",
    }
    for technical, business in phrase_replacements.items():
        text = _replace_case_insensitive(text, technical, business)
    for technical, business in sorted(TECHNICAL_TERMS.items(), key=lambda item: len(item[0]), reverse=True):
        text = _replace_case_insensitive(text, technical, business)
    return text


def _replace_case_insensitive(text: str, technical: str, business: str) -> str:
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(technical)}(?![A-Za-z0-9_])"
    return re.sub(pattern, business, text, flags=re.IGNORECASE)


def _next_actions(issues: list[str], warnings: list[str]) -> list[str]:
    actions = []
    if issues:
        actions.append("Correggere i problemi principali prima di usare il disegno come riferimento.")
    if warnings:
        actions.append("Verificare i punti aperti con chi conosce il processo operativo.")
    if not actions:
        actions.append("Usare il disegno come base per la prossima revisione con il team.")
    return actions


def _element_label(item: dict) -> str:
    return str(item.get("name") or item.get("id") or "Passaggio senza nome")


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        clean = " ".join(str(value or "").split())
        if clean and clean not in result:
            result.append(clean)
    return result
