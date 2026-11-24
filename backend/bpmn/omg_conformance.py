"""BPMN 2.0.2 schema and limited L3 gate for agent-authored canvas versions.

The schema files are the OMG BPMN 2.0.2 machine-readable definitions. An XSD
pass is necessary for interchange, but does not prove behavioral soundness or
that a model faithfully represents the customer's process.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path
from threading import Lock

from lxml import etree

from backend.agents.run_context import BpmnSaveRejected

_XSD_PATH = Path(__file__).resolve().parent / "xsd" / "BPMN20.xsd"
_SCHEMA_LOCK = Lock()
_LOCAL_EDIT_SOURCES = {
    "canvas_facade_update", "canvas_facade_add", "canvas_facade_delete",
    "canvas_facade_clear", "canvas_facade_connect", "canvas_facade_reconnect",
    "canvas_facade_layout", "canvas_agent_update", "canvas_agent_add",
    "canvas_agent_delete", "canvas_agent_connect", "canvas_agent_reconnect",
    "canvas_agent_layout",
}
_COMPLETE_MODEL_SOURCES = {"canvas_construction_apply", "review_approval"}


_UNCHANGED = "Il canvas resta com'era."


def _step(finding: dict) -> str:
    name = finding.get("element_name")
    return f"il passaggio «{name}»" if name else "un passaggio senza nome"


def _behavior_sentence(finding: dict) -> str:
    code = finding.get("code")
    step = _step(finding)
    if code == "deadlock":
        name = finding.get("element_name")
        point = f"il punto di sincronizzazione «{name}»" if name else "un punto di sincronizzazione"
        return f"{point} aspetterebbe per sempre rami che, dopo una scelta, non arrivano"
    if code == "lack_of_synchronization":
        return (f"{step} verrebbe eseguito due volte per la stessa pratica, perche' rami "
                "paralleli si riuniscono senza sincronizzarsi")
    if code == "unreachable_node":
        return f"{step} non si raggiunge dall'inizio del processo"
    if code == "dead_end_node":
        return f"da {step} non si arriva a una fine del processo"
    if code == "no_start_event":
        return "manca l'evento che fa partire il processo"
    if code == "no_end_event":
        return "manca un evento che chiude il processo"
    if code == "no_option_to_complete":
        return "alcuni percorsi girano in tondo senza poter terminare"
    return "un collegamento porta a un elemento che non fa parte di questo processo"


def _behavior_message(findings: list[dict]) -> str:
    sentences = list(dict.fromkeys(_behavior_sentence(item) for item in findings))
    if not sentences:
        return f"Il diagramma non e' stato salvato: il flusso non e' stato verificato per intero. {_UNCHANGED}"
    head = sentences[0]
    more = len(sentences) - 1
    tail = f" (e {more} {'altro problema' if more == 1 else 'altri problemi'} nel flusso)" if more else ""
    return f"Il diagramma non e' stato salvato: {head}{tail}. {_UNCHANGED}"


@lru_cache(maxsize=1)
def _schema() -> etree.XMLSchema:
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    return etree.XMLSchema(etree.parse(str(_XSD_PATH), parser))


def omg_xsd_issues(xml: str) -> list[str]:
    """Return stable diagnostics; reject DTDs and external entities before parsing."""
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        return ["DTD ed entita' XML non sono consentite nei modelli BPMN."]
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    try:
        document = etree.fromstring(xml.encode("utf-8"), parser)
    except etree.XMLSyntaxError as exc:
        return [f"XML non leggibile: {exc.msg}"]
    # libxml's error_log belongs to the shared schema; keep each report isolated.
    with _SCHEMA_LOCK:
        schema = _schema()
        if schema.validate(document):
            return []
        return [f"{entry.path or '/'}: {entry.message}" for entry in schema.error_log]


def assert_agent_bpmn_xsd_transition(*, previous_xml: str | None, proposed_xml: str, source: str) -> None:
    """Gate complete writes on XSD and reachability; preserve legacy local edits.

    Existing, invalid diagrams may receive a local delta while their old XSD
    findings remain. A broad agent replacement must be conformant. No repair is
    applied silently and a failure occurs before the database mutates. Local
    drafts may be incomplete; approval and complete construction may not be.
    """
    if not (source in _LOCAL_EDIT_SOURCES or source in {"canvas_construction_apply", "review_approval", "plan_draft"}):
        return
    if "<!DOCTYPE" in proposed_xml.upper() or "<!ENTITY" in proposed_xml.upper():
        raise BpmnSaveRejected(
            f"Il diagramma non e' stato salvato: contiene istruzioni XML non ammesse. {_UNCHANGED}",
            technical_issues=["BPMN 2.0.2 XSD: DTD ed entita' XML non sono consentite."],
            level="L2",
        )
    from backend.workspace_services.bpmn_canvas_edit import validate_bpmn_xml

    local = validate_bpmn_xml(proposed_xml)
    if local["issues"]:
        raise BpmnSaveRejected(
            f"Il diagramma non e' stato salvato: la struttura BPMN non e' completa. {_UNCHANGED}",
            technical_issues=["BPMN non valido: " + issue for issue in local["issues"]],
            level="L2",
        )
    proposed = omg_xsd_issues(proposed_xml)
    if proposed:
        previous = omg_xsd_issues(previous_xml) if source in _LOCAL_EDIT_SOURCES and previous_xml else []
        if not (previous and not (Counter(proposed) - Counter(previous))):
            count = len(proposed)
            raise BpmnSaveRejected(
                "Il diagramma non e' stato salvato: non rispetta lo standard BPMN 2.0 "
                f"({count} {'problema tecnico' if count == 1 else 'problemi tecnici'}). {_UNCHANGED}",
                technical_issues=["BPMN 2.0.2 XSD: " + issue for issue in proposed],
                level="L2",
            )
    if source in _COMPLETE_MODEL_SOURCES:
        from backend.bpmn.xml_behavior import analyze_canvas_xml_behavior

        behavior = analyze_canvas_xml_behavior(proposed_xml)
        if behavior["processes_analyzed"] == 0 or behavior["processes_skipped"]:
            raise BpmnSaveRejected(
                _behavior_message([]),
                technical_issues=["BPMN L3: il grafo principale non e' stato analizzato per intero.",
                                  *behavior["warnings"]],
                level="L3",
            )
        if behavior["issues"]:
            raise BpmnSaveRejected(
                _behavior_message(behavior["findings"]),
                technical_issues=["BPMN L3: " + issue for issue in behavior["issues"]],
                level="L3",
            )
