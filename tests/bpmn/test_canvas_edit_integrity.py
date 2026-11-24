"""A local canvas command may change only its declared semantic slice."""

from pathlib import Path

import pytest

from backend.bpmn.edit_integrity import assert_local_edit_integrity
from backend.workspace_services.bpmn_canvas_edit import (
    add_bpmn_element,
    clear_bpmn_process,
    connect_bpmn_elements,
    delete_bpmn_element,
    layout_bpmn_di,
    reconnect_bpmn_flow,
    update_bpmn_element,
)

XML = (Path(__file__).resolve().parents[1] / "fixtures/omg_valid_minimal.bpmn").read_text(
    encoding="utf-8"
)


@pytest.mark.parametrize(
    ("operation", "apply"),
    [
        ("update_element", lambda xml: (update_bpmn_element(xml, "Review", name="Validate request"))),
        ("add_element", lambda xml: (add_bpmn_element(xml, "task", "Archive request"))),
        ("add_element", lambda xml: (add_bpmn_element(xml, "lane", "New role"))),
        ("delete_element", lambda xml: (delete_bpmn_element(xml, "Review"))),
        ("clear_canvas", lambda xml: (clear_bpmn_process(xml))),
        ("connect_elements", lambda xml: (connect_bpmn_elements(xml, "Start", "End"))),
        ("reconnect_flow", lambda xml: (reconnect_bpmn_flow(xml, "Flow_1", target_id="End"))),
        ("layout", lambda xml: (layout_bpmn_di(xml), {})),
    ],
)
def test_local_operations_preserve_unrelated_semantics(operation, apply):
    after, change = apply(XML)
    assert_local_edit_integrity(
        before_xml=XML, after_xml=after, operation=operation, change=change,
        element_id="Review" if operation == "update_element" else None,
    )


def test_local_edit_rejects_an_unrequested_name_change():
    after, change = update_bpmn_element(XML, "Review", name="Validate request")
    after = after.replace('name="Request reviewed"', 'name="Unexpected change"')
    with pytest.raises(ValueError, match="non richiesti"):
        assert_local_edit_integrity(
            before_xml=XML, after_xml=after, operation="update_element", change=change,
            element_id="Review",
        )


def test_facade_rejects_collateral_change_before_database_write(monkeypatch):
    from backend.toolsets import bpmn as canvas_tools

    def corrupt_patch(xml, element_id, name=None, documentation=None):
        patched, change = update_bpmn_element(xml, element_id, name=name, documentation=documentation)
        return patched.replace('name="Request reviewed"', 'name="Unexpected change"'), change

    monkeypatch.setattr(canvas_tools, "_state_or_saved_canvas_xml", lambda *_args: (XML, "saved"))
    monkeypatch.setattr(canvas_tools, "update_bpmn_element", corrupt_patch)
    monkeypatch.setattr(
        canvas_tools.workspace_database, "update_bpmn_model",
        lambda *_args, **_kwargs: pytest.fail("collateral change reached database write"),
    )

    with pytest.raises(ValueError, match="non richiesti"):
        canvas_tools.manage_canvas_bpmn_model.func(
            bpmn_model_id="model-1", operation="update_element", state={},
            element_id="Review", name="Validate request", tool_call_id="call-1",
        )


def test_clear_canvas_preserves_process_documentation():
    xml = XML.replace('<bpmn:process id="Process_Valid" isExecutable="false">',
                      '<bpmn:process id="Process_Valid" isExecutable="false">'
                      '<bpmn:documentation>DeliR semantic payload: {"source":"synthetic"}'
                      '</bpmn:documentation>')
    after, change = clear_bpmn_process(xml)
    assert 'DeliR semantic payload: {"source":"synthetic"}' in after
    assert_local_edit_integrity(
        before_xml=xml, after_xml=after, operation="clear_canvas", change=change,
    )


def test_second_lane_addition_preserves_existing_pool_and_lane():
    with_first, _ = add_bpmn_element(XML, "lane", "First role")
    with_second, change = add_bpmn_element(with_first, "lane", "Second role")
    assert_local_edit_integrity(
        before_xml=with_first, after_xml=with_second,
        operation="add_element", change=change,
    )


def test_deleting_a_task_also_removes_its_data_association():
    purchase = (Path(__file__).resolve().parents[1] / "fixtures/purchase_layout.bpmn").read_text(
        encoding="utf-8"
    )
    after, change = delete_bpmn_element(purchase, "Open_Request")
    assert change["removed_connectors"] == ["Request_Data"]
    assert 'id="Request_Data"' not in after and 'bpmnElement="Request_Data"' not in after
    assert 'id="Request_Document"' in after
    assert_local_edit_integrity(
        before_xml=purchase, after_xml=after, operation="delete_element", change=change,
    )


def test_delete_without_connector_ids_fails_closed():
    with pytest.raises(ValueError, match="collegamenti senza ID"):
        assert_local_edit_integrity(
            before_xml=XML, after_xml=XML, operation="delete_element",
            change={"id": "Review", "removed_connectors": [""]},
        )


def test_connectors_nested_in_the_deleted_task_leave_with_it():
    xml = XML.replace(
        '<bpmn:task id="Review" name="Review request" />',
        '<bpmn:task id="Review" name="Review request"><bpmn:dataInputAssociation id="Review_Input">'
        '<bpmn:sourceRef>Doc</bpmn:sourceRef></bpmn:dataInputAssociation></bpmn:task>'
        '<bpmn:dataObjectReference id="Doc" name="Request form" />',
    )
    after, change = delete_bpmn_element(xml, "Review")
    assert change["removed_connectors"] == []
    assert "dataInputAssociation" not in after and 'id="Doc"' in after
    assert_local_edit_integrity(before_xml=xml, after_xml=after, operation="delete_element", change=change)
