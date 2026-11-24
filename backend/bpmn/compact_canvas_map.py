"""Read-only navigation map for local canvas edits.

The canonical XML stays in runtime storage. This incomplete map only helps the
agent choose exact IDs and inspect connections. It cannot replace BPMN XML.
"""

from __future__ import annotations

from defusedxml.ElementTree import fromstring

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")


_DATA_ASSOCIATIONS = {"dataInputAssociation", "dataOutputAssociation"}


def _child_ref(element, name: str) -> str:
    for child in element:
        if child.tag == "{" + BPMN_NS + "}" + name and child.text:
            return child.text.strip()
    return ""


def compact_canvas_map(xml: str) -> str:
    """Return exact IDs, labels, lane membership, flows and data links.

    ``A`` lines carry associations and data associations: without them a
    reader of the map cannot tell that a step uses or produces a document,
    and reports the link as missing.
    """
    root = fromstring(xml)
    lines = ["canvas-map 2",
             "N id\ttype\tname | F id\tsource\ttarget\tname | A id\tsource\ttarget (dati) "
             "| R lane\tnode"]
    parents = {child: parent for parent in root.iter() for child in parent}
    for element in root.iter():
        if not element.tag.startswith("{" + BPMN_NS + "}"):
            continue
        kind = element.tag.rsplit("}", 1)[-1]
        element_id = element.attrib.get("id")
        if kind in _DATA_ASSOCIATIONS:
            owner = parents.get(element)
            owner_id = owner.attrib.get("id", "") if owner is not None else ""
            source, target = ((_child_ref(element, "sourceRef"), owner_id)
                              if kind == "dataInputAssociation"
                              else (owner_id, _child_ref(element, "targetRef")))
            lines.append("\t".join(_escape(value) for value in ("A", element_id or "", source, target)))
            continue
        if element_id:
            if kind in {"sequenceFlow", "messageFlow"}:
                fields = ("F", element_id, element.attrib.get("sourceRef", ""),
                          element.attrib.get("targetRef", ""), element.attrib.get("name", ""))
            elif kind == "association":
                fields = ("A", element_id, element.attrib.get("sourceRef", ""),
                          element.attrib.get("targetRef", ""))
            else:
                fields = ("N", element_id, kind, element.attrib.get("name", ""))
            lines.append("\t".join(_escape(value) for value in fields))
        if kind == "lane" and element_id:
            for child in element:
                if child.tag == "{" + BPMN_NS + "}flowNodeRef" and child.text:
                    lines.append("\t".join(("R", _escape(element_id), _escape(child.text.strip()))))
    return "\n".join(lines) + "\n"
