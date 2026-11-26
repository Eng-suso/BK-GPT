"""Read-only navigation map for local canvas edits.

The canonical XML stays in runtime storage. This incomplete map only helps the
agent choose exact IDs and inspect connections. It cannot replace BPMN XML.
"""

from __future__ import annotations

from defusedxml.ElementTree import fromstring

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")


def compact_canvas_map(xml: str) -> str:
    """Return exact IDs, labels, lane membership and sequence/message edges."""
    root = fromstring(xml)
    lines = ["canvas-map 1", "N id\ttype\tname | F id\tsource\ttarget\tname | R lane\tnode"]
    for element in root.iter():
        if not element.tag.startswith("{" + BPMN_NS + "}"):
            continue
        kind = element.tag.rsplit("}", 1)[-1]
        element_id = element.attrib.get("id")
        if element_id:
            if kind in {"sequenceFlow", "messageFlow"}:
                fields = ("F", element_id, element.attrib.get("sourceRef", ""),
                          element.attrib.get("targetRef", ""), element.attrib.get("name", ""))
            else:
                fields = ("N", element_id, kind, element.attrib.get("name", ""))
            lines.append("\t".join(_escape(value) for value in fields))
        if kind == "lane" and element_id:
            for child in element:
                if child.tag == "{" + BPMN_NS + "}flowNodeRef" and child.text:
                    lines.append("\t".join(("R", _escape(element_id), _escape(child.text.strip()))))
    return "\n".join(lines) + "\n"
