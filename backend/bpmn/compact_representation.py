"""Experimental, lossless semantic BPMN codec for canvas representation tests.

The line based DeliR DSL keeps every semantic XML element and attribute, including
unknown extensions. Diagram geometry is excluded and can be rebuilt by layout.

Namespace declarations travel as ``@xmlns:prefix`` fields on the root, so QName
values such as ``xsi:type="bpmn:tFormalExpression"`` or ``messageRef="tns:M"``
keep resolving to the same namespace after a round trip. Documents that bind
one prefix to two namespaces, or whose prefix ElementTree would reuse for
another namespace on output, are refused instead of being rewritten.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import re
from io import StringIO
from xml.sax.saxutils import quoteattr

from defusedxml.ElementTree import fromstring, iterparse

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
DI_NAMESPACES = {
    "http://www.omg.org/spec/BPMN/20100524/DI",
    "http://www.omg.org/spec/DD/20100524/DI",
    "http://www.omg.org/spec/DD/20100524/DC",
}
ATTRIBUTE_SHORT = {
    "id": "i", "name": "n", "sourceRef": "s", "targetRef": "t",
    "processRef": "p", "isExecutable": "e", "default": "d",
}
ATTRIBUTE_LONG = {short: long for long, short in ATTRIBUTE_SHORT.items()}
TAG_SHORT = {
    "definitions": "D", "process": "P", "collaboration": "C",
    "participant": "p", "laneSet": "L", "lane": "l", "flowNodeRef": "r",
    "startEvent": "S", "endEvent": "E", "intermediateCatchEvent": "I",
    "intermediateThrowEvent": "O", "boundaryEvent": "B",
    "task": "T", "userTask": "U", "serviceTask": "V", "manualTask": "M",
    "sendTask": "N", "receiveTask": "R", "subProcess": "Q",
    "exclusiveGateway": "X", "parallelGateway": "A", "inclusiveGateway": "J",
    "eventBasedGateway": "G", "sequenceFlow": "F", "messageFlow": "f",
    "documentation": "d", "extensionElements": "x",
    "conditionExpression": "c", "outgoing": "o", "incoming": "i",
    "dataObjectReference": "z", "association": "a", "textAnnotation": "t",
}
TAG_LONG = {short: long for long, short in TAG_SHORT.items()}


def _without_di(element: ET.Element) -> ET.Element | None:
    if element.tail and element.tail.strip():
        raise ValueError("DeliR DSL does not support mixed XML content")
    if element.tag.startswith("{") and element.tag[1:].split("}", 1)[0] in DI_NAMESPACES:
        return None
    copy = ET.Element(element.tag, element.attrib)
    copy.text = (element.text or "").strip() or None
    for child in element:
        kept = _without_di(child)
        if kept is not None:
            copy.append(kept)
    return copy


def semantic_tree(xml: str) -> tuple:
    root = _without_di(fromstring(xml))
    if root is None:
        raise ValueError("BPMN root cannot be diagram geometry")

    def walk(element: ET.Element) -> tuple:
        return element.tag, tuple(sorted(element.attrib.items())), element.text or "", tuple(
            walk(child) for child in element
        )

    return walk(root)


def _name(qname: str) -> str:
    prefix = "{" + BPMN_NS + "}"
    return qname[len(prefix):] if qname.startswith(prefix) else "@" + qname


def _qname(name: str) -> str:
    return name[1:] if name.startswith("@") else "{" + BPMN_NS + "}" + name


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def _unescape(value: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "\\":
            result.append(value[index])
            index += 1
            continue
        if index + 1 >= len(value) or value[index + 1] not in "\\tn":
            raise ValueError("Invalid DeliR DSL escape")
        result.append({"\\": "\\", "t": "\t", "n": "\n"}[value[index + 1]])
        index += 2
    return "".join(result)


_XMLNS = "xmlns"
_QNAME_PREFIX = re.compile(r"(?<![\w.-])([A-Za-z_][\w.-]*):[A-Za-z_][\w.-]*")


def _namespace_declarations(xml: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    for _event, (prefix, uri) in iterparse(StringIO(xml), events=("start-ns",)):
        if declarations.get(prefix, uri) != uri:
            raise ValueError(f"DeliR DSL: il prefisso XML '{prefix}' e' legato a due namespace.")
        declarations[prefix] = uri
    return declarations


def _prepared_root(xml: str) -> ET.Element:
    root = _without_di(fromstring(xml))
    if root is None:
        raise ValueError("BPMN root cannot be diagram geometry")
    values = [value for element in root.iter() for value in (*element.attrib.values(), element.text or "")]
    used = {match.group(1) for value in values for match in _QNAME_PREFIX.finditer(value)}
    # Element and attribute names carry their full namespace already; only the
    # prefixes that QName values use, and the default namespace that unprefixed
    # QName values resolve against, need to survive.
    for prefix, uri in _namespace_declarations(xml).items():
        if not prefix or prefix in used:
            root.set(f"{_XMLNS}:{prefix}" if prefix else _XMLNS, uri)
    return root


def _serialize_with_declarations(root: ET.Element) -> str:
    """Serialize and re-declare the source prefixes that QName values rely on."""
    wanted = {key: root.attrib.pop(key) for key in list(root.attrib)
              if key == _XMLNS or key.startswith(_XMLNS + ":")}
    if _XMLNS in wanted and any(not element.tag.startswith("{") for element in root.iter()):
        raise ValueError("DeliR DSL: namespace di default con elementi senza namespace.")
    output = ET.tostring(root, encoding="unicode")
    present = {prefix: uri for _event, (prefix, uri) in iterparse(StringIO(output), events=("start-ns",))}
    extra = []
    for key, uri in sorted(wanted.items()):
        prefix = key.partition(":")[2]
        if prefix in present:
            if present[prefix] != uri:
                raise ValueError(f"DeliR DSL: il prefisso XML '{prefix}' non si puo' ricostruire.")
            continue
        extra.append(f" {key}={quoteattr(uri)}")
    if not extra:
        return output
    head = re.match(r"<[^\s/>]+", output)
    return output[:head.end()] + "".join(extra) + output[head.end():]


def encode_delir_dsl(xml: str) -> str:
    root = _prepared_root(xml)
    lines = [f"delir 1 {sum(1 for _ in root.iter())}"]

    def walk(element: ET.Element, depth: int) -> None:
        fields = [">" * depth + _name(element.tag)]
        fields.extend(
            f"{ATTRIBUTE_SHORT.get(key, '@' + key)}={_escape(value)}"
            for key, value in sorted(element.attrib.items())
        )
        if element.text:
            fields.append("#=" + _escape(element.text))
        lines.append("\t".join(fields))
        for child in element:
            walk(child, depth + 1)

    walk(root, 0)
    return "\n".join(lines) + "\n"


def encode_delir_dsl_v2(xml: str) -> str:
    """Versioned experiment: short BPMN tags plus a dictionary for repeated values."""
    from collections import Counter

    root = _prepared_root(xml)
    elements = list(root.iter())
    frequency = Counter(value for element in elements
                        for value in (*element.attrib.values(), element.text or "") if value)
    # A symbol costs one declaration; only repeated, nontrivial values can win.
    symbols = {value: index for index, (value, count) in enumerate(
        (item for item in frequency.items() if item[1] >= 3 and len(item[0]) >= 5),
    )}
    lines = [f"delir 2 {len(elements)} {len(symbols)}"]
    lines.extend(f"${index}\t{_escape(value)}" for value, index in symbols.items())

    def value_field(value: str) -> str:
        if value in symbols:
            return f"${symbols[value]}"
        escaped = _escape(value)
        return "$" + escaped if escaped.startswith("$") else escaped

    def walk(element: ET.Element, depth: int) -> None:
        name = _name(element.tag)
        tag = ":" + TAG_SHORT[name] if name in TAG_SHORT else name
        fields = [">" * depth + tag]
        fields.extend(f"{ATTRIBUTE_SHORT.get(key, '@' + key)}={value_field(value)}"
                      for key, value in sorted(element.attrib.items()))
        if element.text:
            fields.append("#=" + value_field(element.text))
        lines.append("\t".join(fields))
        for child in element:
            walk(child, depth + 1)

    walk(root, 0)
    return "\n".join(lines) + "\n"


def decode_delir_dsl_v2(source: str) -> str:
    lines = source.splitlines()
    if not lines or not lines[0].startswith("delir 2 "):
        raise ValueError("Invalid DeliR DSL v2 header")
    try:
        _, _, raw_count, raw_symbols = lines[0].split(" ")
        count, symbol_count = int(raw_count), int(raw_symbols)
    except ValueError as exc:
        raise ValueError("Invalid DeliR DSL v2 header") from exc
    if count < 1 or symbol_count < 0 or len(lines) != 1 + symbol_count + count:
        raise ValueError("Incomplete DeliR DSL v2 document")
    symbols = []
    for index, line in enumerate(lines[1:1 + symbol_count]):
        key, separator, value = line.partition("\t")
        if not separator or key != f"${index}":
            raise ValueError("Invalid DeliR DSL v2 dictionary")
        symbols.append(_unescape(value))

    def decode_value(raw: str) -> str:
        if raw.startswith("$$"):
            return _unescape(raw[1:])
        if raw.startswith("$"):
            try:
                return symbols[int(raw[1:])]
            except (ValueError, IndexError) as exc:
                raise ValueError("Invalid DeliR DSL v2 symbol") from exc
        return _unescape(raw)

    root = None
    parents: list[ET.Element] = []
    for line in lines[1 + symbol_count:]:
        fields = line.split("\t")
        raw_tag = fields[0].lstrip(">")
        depth = len(fields[0]) - len(raw_tag)
        if not raw_tag or depth > len(parents):
            raise ValueError("Invalid DeliR DSL v2 tree")
        if raw_tag.startswith(":"):
            if raw_tag[1:] not in TAG_LONG:
                raise ValueError("Unknown DeliR DSL v2 tag")
            tag = TAG_LONG[raw_tag[1:]]
        else:
            tag = raw_tag
        attrs: dict[str, str] = {}
        body = None
        for field in fields[1:]:
            key, separator, value = field.partition("=")
            if not separator:
                raise ValueError("Invalid DeliR DSL v2 field")
            if key == "#":
                if body is not None:
                    raise ValueError("Duplicate DeliR DSL v2 text")
                body = decode_value(value)
            else:
                full_key = ATTRIBUTE_LONG.get(key, _qname(key) if key.startswith("@") else key)
                if not key or full_key in attrs:
                    raise ValueError("Duplicate or empty DeliR DSL v2 attribute")
                attrs[full_key] = decode_value(value)
        element = ET.Element(_qname(tag), attrs)
        element.text = body
        if depth == 0:
            if root is not None:
                raise ValueError("Multiple DeliR DSL v2 roots")
            root = element
        else:
            parents[depth - 1].append(element)
        parents = parents[:depth] + [element]
    if root is None:
        raise ValueError("Empty DeliR DSL v2 document")
    return _serialize_with_declarations(root)


def decode_delir_dsl(source: str) -> str:
    lines = source.splitlines()
    if len(lines) < 2 or not lines[0].startswith("delir 1 "):
        raise ValueError("Invalid DeliR DSL header")
    try:
        count = int(lines[0][8:])
    except ValueError as exc:
        raise ValueError("Invalid DeliR DSL element count") from exc
    if count < 1 or count != len(lines) - 1:
        raise ValueError("Incomplete DeliR DSL document")
    root = None
    parents: list[ET.Element] = []
    for line in lines[1:]:
        fields = line.split("\t")
        tag = fields[0].lstrip(">")
        depth = len(fields[0]) - len(tag)
        if not tag or depth > len(parents):
            raise ValueError("Invalid DeliR DSL tree")
        attrs: dict[str, str] = {}
        body = None
        for field in fields[1:]:
            if "=" not in field:
                raise ValueError("Invalid DeliR DSL field")
            key, value = field.split("=", 1)
            if key == "#":
                if body is not None:
                    raise ValueError("Duplicate DeliR DSL text")
                body = _unescape(value)
            else:
                full_key = ATTRIBUTE_LONG.get(key, _qname(key) if key.startswith("@") else key)
                if not key or full_key in attrs:
                    raise ValueError("Duplicate or empty DeliR DSL attribute")
                attrs[full_key] = _unescape(value)
        element = ET.Element(_qname(tag), attrs)
        element.text = body
        if depth == 0:
            if root is not None:
                raise ValueError("Multiple DeliR DSL roots")
            root = element
        else:
            parents[depth - 1].append(element)
        parents = parents[:depth] + [element]
    if root is None:
        raise ValueError("Empty DeliR DSL document")
    return _serialize_with_declarations(root)
