"""An XSD rejection must happen before a canvas version is committed."""

import uuid
from pathlib import Path

import pytest

from backend import workspace_database as wd
from backend.bpmn.omg_conformance import omg_xsd_issues
from backend.security import reset_current_tenant_id, set_current_tenant_id

VALID_XML = (Path(__file__).resolve().parents[1] / "fixtures/omg_valid_minimal.bpmn").read_text(
    encoding="utf-8"
)


def test_agent_construction_rejects_invalid_bpmn_without_creating_version():
    token = set_current_tenant_id(f"t-omg-gate-{uuid.uuid4().hex[:8]}")
    try:
        client = wd.create_client(name="Synthetic OMG gate test")
        project = wd.create_project(client_id=client["id"], name="Benchmark")
        process = wd.create_process(project_id=project["id"], name="Test process")
        model_id = process["bpmn_model_id"]
        invalid = VALID_XML.replace(' targetNamespace="urn:delir:test:valid"', "")

        with pytest.raises(ValueError, match="standard BPMN 2.0"):
            wd.update_bpmn_model(model_id, invalid, source="canvas_construction_apply")
        assert wd.get_bpmn_model(model_id)["xml"] is None
        assert wd.list_bpmn_versions(model_id) == []

        saved = wd.update_bpmn_model(model_id, VALID_XML, source="canvas_construction_apply")
        assert saved is not None
        assert omg_xsd_issues(saved["xml"]) == []
        assert len(wd.list_bpmn_versions(model_id)) == 1
    finally:
        reset_current_tenant_id(token)


def test_complete_agent_construction_rejects_orphan_before_database_write():
    token = set_current_tenant_id(f"t-l3-gate-{uuid.uuid4().hex[:8]}")
    try:
        client = wd.create_client(name="Synthetic L3 gate test")
        project = wd.create_project(client_id=client["id"], name="Benchmark")
        process = wd.create_process(project_id=project["id"], name="Test process")
        model_id = process["bpmn_model_id"]
        orphan = VALID_XML.replace('<bpmn:endEvent id="End"',
                                   '<bpmn:task id="Orphan" name="Unconnected" />\n    '
                                   '<bpmn:endEvent id="End"')

        with pytest.raises(ValueError, match="«Unconnected» non si raggiunge"):
            wd.update_bpmn_model(model_id, orphan, source="canvas_construction_apply")
        assert wd.get_bpmn_model(model_id)["xml"] is None
        assert wd.list_bpmn_versions(model_id) == []
    finally:
        reset_current_tenant_id(token)
