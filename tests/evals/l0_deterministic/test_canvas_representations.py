"""Semantic round-trip guard for the experimental canvas DSL."""

import re

from pathlib import Path

import pytest

from backend.bpmn.compact_representation import (
    decode_delir_dsl, decode_delir_dsl_v2, encode_delir_dsl, encode_delir_dsl_v2, semantic_tree,
)
from tests.evals.bef4llm import validity

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.mark.parametrize("name", [
    "purchase_layout.bpmn", "multibranch_layout.bpmn", "omg_issue_list.bpmn",
])
def test_delir_dsl_preserves_every_semantic_element(name):
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    encoded = encode_delir_dsl(xml)
    assert semantic_tree(decode_delir_dsl(encoded)) == semantic_tree(xml)


def test_delir_dsl_rejects_truncated_and_malformed_documents():
    xml = (FIXTURES / "purchase_layout.bpmn").read_text(encoding="utf-8")
    lines = encode_delir_dsl(xml).splitlines()
    with pytest.raises(ValueError):
        decode_delir_dsl("\n".join(lines[:2]))
    lines[3] = "[2,0,[],\"\"]"
    with pytest.raises(ValueError):
        decode_delir_dsl("\n".join(lines))


def test_delir_dsl_preserves_unknown_extensions_and_escaped_text():
    xml = ('<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" '
           'xmlns:ext="urn:delir:test" i="literal" id="Defs">'
           '<process id="Process"><ext:rule ext:i="x\\y" n="literal">'
           'first&#10;second&#9;third</ext:rule></process></definitions>')
    assert semantic_tree(decode_delir_dsl(encode_delir_dsl(xml))) == semantic_tree(xml)


def test_delir_dsl_rejects_mixed_content_instead_of_dropping_it():
    xml = ('<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">'
           '<process id="Process"><documentation>before<b>inside</b>after'
           '</documentation></process></definitions>')
    with pytest.raises(ValueError, match="mixed XML content"):
        encode_delir_dsl(xml)


def _resolved_qnames(xml: str) -> list[tuple]:
    """Every prefixed value, resolved against the namespaces in scope."""
    from lxml import etree

    pattern = re.compile(r"([A-Za-z_][\w.-]*):([A-Za-z_][\w.-]*)")
    resolved = []
    for index, element in enumerate(etree.fromstring(xml.encode("utf-8")).iter()):
        if not isinstance(element.tag, str):
            continue
        for key, value in (*sorted(element.attrib.items()), ("#text", (element.text or "").strip())):
            match = pattern.fullmatch(value)
            if match and match.group(1) in element.nsmap:
                resolved.append((index, element.tag, key, element.nsmap[match.group(1)], match.group(2)))
    return resolved


QNAME_XML = (
    '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" '
    'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xmlns:tns="urn:delir:test:messages" id="D" targetNamespace="urn:delir:test:messages">'
    '<message id="Order"/>'
    '<process id="P"><startEvent id="S"><messageEventDefinition messageRef="tns:Order"/></startEvent>'
    '<sequenceFlow id="F" sourceRef="S" targetRef="E">'
    '<conditionExpression xsi:type="bpmn:tFormalExpression">ok</conditionExpression>'
    '</sequenceFlow><endEvent id="E"/></process></definitions>'
)


@pytest.mark.parametrize("codec", [
    (encode_delir_dsl, decode_delir_dsl), (encode_delir_dsl_v2, decode_delir_dsl_v2),
])
def test_delir_dsl_keeps_qname_values_resolving_to_the_same_namespace(codec):
    encode, decode = codec
    rebuilt = decode(encode(QNAME_XML))
    assert semantic_tree(rebuilt) == semantic_tree(QNAME_XML)
    assert _resolved_qnames(rebuilt) == _resolved_qnames(QNAME_XML)
    assert {item[3] for item in _resolved_qnames(rebuilt)} == {
        "urn:delir:test:messages", "http://www.omg.org/spec/BPMN/20100524/MODEL",
    }


def test_delir_dsl_keeps_nested_prefix_declarations():
    xml = QNAME_XML.replace(' xmlns:tns="urn:delir:test:messages"', "").replace(
        '<process id="P">', '<process xmlns:tns="urn:delir:test:messages" id="P">',
    )
    rebuilt = decode_delir_dsl(encode_delir_dsl(xml))
    assert _resolved_qnames(rebuilt) == _resolved_qnames(xml)


def test_delir_dsl_refuses_prefixes_it_cannot_rebuild_faithfully():
    rebound = QNAME_XML.replace(
        '<process id="P">', '<process xmlns:tns="urn:other" id="P">',
    )
    with pytest.raises(ValueError, match="legato a due namespace"):
        encode_delir_dsl(rebound)
    # ElementTree names unregistered namespaces ns0, ns1...: a source prefix
    # with the same spelling is either rebuilt exactly or refused, never bound
    # silently to another namespace.
    generated = QNAME_XML.replace("xmlns:tns=", "xmlns:ns0=").replace('"tns:Order"', '"ns0:Order"')
    try:
        rebuilt = decode_delir_dsl(encode_delir_dsl(generated))
    except ValueError as exc:
        assert "non si puo' ricostruire" in str(exc)
    else:
        assert _resolved_qnames(rebuilt) == _resolved_qnames(generated)


def test_delir_dsl_drops_declarations_no_value_needs():
    xml = QNAME_XML.replace('messageRef="tns:Order"', 'messageRef="Order"')
    assert "xmlns:tns" not in encode_delir_dsl(xml)


def test_delir_dsl_preserves_omg_xsd_valid_model():
    xml = (
        '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="Defs" targetNamespace="urn:delir:test"><process id="P" isExecutable="false">'
        '<startEvent id="S"/><task id="T" name="Work"/><endEvent id="E"/>'
        '<sequenceFlow id="F1" sourceRef="S" targetRef="T"/>'
        '<sequenceFlow id="F2" sourceRef="T" targetRef="E"/>'
        '</process></definitions>'
    )
    rebuilt = decode_delir_dsl(encode_delir_dsl(xml))
    assert semantic_tree(rebuilt) == semantic_tree(xml)
    assert validity(xml)[0] == validity(rebuilt)[0] == 1.0


@pytest.mark.parametrize("name", [
    "purchase_layout.bpmn", "multibranch_layout.bpmn", "omg_issue_list.bpmn",
])
def test_delir_v2_preserves_fixture_semantics(name):
    xml = (FIXTURES / name).read_text(encoding="utf-8")
    assert semantic_tree(decode_delir_dsl_v2(encode_delir_dsl_v2(xml))) == semantic_tree(xml)


def test_delir_v2_rejects_missing_symbols_and_preserves_literal_dollar():
    xml = ('<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" '
           'id="D" targetNamespace="urn:test"><process id="P">'
           '<task id="T" name="$literal"/></process></definitions>')
    encoded = encode_delir_dsl_v2(xml)
    assert semantic_tree(decode_delir_dsl_v2(encoded)) == semantic_tree(xml)
    with pytest.raises(ValueError):
        decode_delir_dsl_v2(encoded.replace("$$literal", "$99"))
