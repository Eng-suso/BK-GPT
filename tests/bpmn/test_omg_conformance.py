"""The runtime OMG schema gate uses the same normative files as evals."""

from pathlib import Path

import pytest

from backend.bpmn.omg_conformance import (
    assert_agent_bpmn_xsd_transition,
    omg_xsd_issues,
)

ROOT = Path(__file__).resolve().parents[2]
VALID_XML = (ROOT / "tests/fixtures/omg_valid_minimal.bpmn").read_text(encoding="utf-8")


def test_valid_fixture_passes_omg_schema_and_keeps_runtime_schemas_identical():
    assert omg_xsd_issues(VALID_XML) == []
    for name in ("BPMN20.xsd", "BPMNDI.xsd", "Semantic.xsd", "DI.xsd", "DC.xsd"):
        assert (ROOT / "backend/bpmn/xsd" / name).read_bytes() == (
            ROOT / "tests/evals/bef4llm_xsd" / name
        ).read_bytes()


def test_new_agent_model_requires_omg_xsd():
    invalid = VALID_XML.replace(' targetNamespace="urn:delir:test:valid"', "")
    with pytest.raises(ValueError, match="targetNamespace"):
        assert_agent_bpmn_xsd_transition(
            previous_xml=None, proposed_xml=invalid, source="canvas_construction_apply"
        )
    assert_agent_bpmn_xsd_transition(
        previous_xml=None, proposed_xml=VALID_XML, source="canvas_construction_apply"
    )


def test_valid_existing_model_cannot_regress_on_local_edit():
    invalid = VALID_XML.replace(' targetNamespace="urn:delir:test:valid"', "")
    with pytest.raises(ValueError, match="targetNamespace"):
        assert_agent_bpmn_xsd_transition(
            previous_xml=VALID_XML, proposed_xml=invalid, source="canvas_facade_update"
        )


def test_agent_model_rejects_dangling_sequence_flow_even_if_xsd_accepts_qname():
    broken = VALID_XML.replace('sourceRef="Review"', 'sourceRef="Unknown"')
    with pytest.raises(ValueError, match="sourceRef non valido"):
        assert_agent_bpmn_xsd_transition(
            previous_xml=VALID_XML, proposed_xml=broken, source="canvas_facade_connect"
        )


def test_legacy_invalid_model_allows_only_unchanged_xsd_findings_on_local_edit():
    legacy = VALID_XML.replace(' targetNamespace="urn:delir:test:valid"', "")
    renamed = legacy.replace("Review request", "Validate request")
    assert_agent_bpmn_xsd_transition(
        previous_xml=legacy, proposed_xml=renamed, source="canvas_facade_update"
    )
    worsened = renamed.replace('name="Validate request"', 'name="Validate request" bogus="x"')
    with pytest.raises(ValueError, match="BPMN 2.0.2 XSD"):
        assert_agent_bpmn_xsd_transition(
            previous_xml=legacy, proposed_xml=worsened, source="canvas_facade_update"
        )
    with pytest.raises(ValueError, match="targetNamespace"):
        assert_agent_bpmn_xsd_transition(
            previous_xml=legacy, proposed_xml=renamed, source="review_approval"
        )


def test_dtd_is_rejected_before_schema_validation():
    with pytest.raises(ValueError, match="DTD"):
        assert_agent_bpmn_xsd_transition(
            previous_xml=None,
            proposed_xml='<!DOCTYPE definitions [<!ENTITY x "unsafe">]>' + VALID_XML,
            source="canvas_construction_apply",
        )


def test_complete_agent_model_rejects_orphan_but_local_draft_may_be_incomplete():
    orphan = VALID_XML.replace('<bpmn:endEvent id="End"',
                               '<bpmn:task id="Orphan" name="Unconnected" />\n    '
                               '<bpmn:endEvent id="End"')
    assert omg_xsd_issues(orphan) == []
    for source in ("canvas_construction_apply", "review_approval"):
        with pytest.raises(ValueError, match="BPMN L3.*Orphan"):
            assert_agent_bpmn_xsd_transition(
                previous_xml=VALID_XML, proposed_xml=orphan, source=source,
            )
    assert_agent_bpmn_xsd_transition(
        previous_xml=VALID_XML, proposed_xml=orphan, source="canvas_facade_add",
    )
