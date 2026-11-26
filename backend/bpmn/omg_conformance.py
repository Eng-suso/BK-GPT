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
        raise ValueError("BPMN 2.0.2 XSD: DTD ed entita' XML non sono consentite.")
    from backend.workspace_services.bpmn_canvas_edit import validate_bpmn_xml

    local = validate_bpmn_xml(proposed_xml)
    if local["issues"]:
        raise ValueError("BPMN non valido: " + "; ".join(local["issues"][:3]))
    proposed = omg_xsd_issues(proposed_xml)
    if proposed:
        previous = omg_xsd_issues(previous_xml) if source in _LOCAL_EDIT_SOURCES and previous_xml else []
        if not (previous and not (Counter(proposed) - Counter(previous))):
            raise ValueError("BPMN 2.0.2 XSD: " + "; ".join(proposed[:3]))
    if source in _COMPLETE_MODEL_SOURCES:
        from backend.bpmn.xml_behavior import analyze_canvas_xml_behavior

        behavior = analyze_canvas_xml_behavior(proposed_xml)
        if behavior["processes_analyzed"] == 0 or behavior["processes_skipped"]:
            raise ValueError("BPMN L3: il grafo principale non e' stato analizzato per intero.")
        if behavior["issues"]:
            raise ValueError("BPMN L3: " + "; ".join(behavior["issues"][:3]))
