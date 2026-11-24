"""Semantic round-trip guard for the experimental canvas DSL."""

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


def test_delir_dsl_rejects_qname_values_it_cannot_preserve():
    xml = ('<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" '
           'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
           'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
           '<process id="P"><sequenceFlow id="F" sourceRef="A" targetRef="B">'
           '<conditionExpression xsi:type="bpmn:tFormalExpression">x</conditionExpression>'
           '</sequenceFlow></process></definitions>')
    with pytest.raises(ValueError, match="valori QName"):
        encode_delir_dsl(xml)


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
