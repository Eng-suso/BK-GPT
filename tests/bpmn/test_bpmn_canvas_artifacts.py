"""clean_bpmn_visual_metadata_artifacts keeps the data perspective on the canvas."""

from backend.workspace_services.bpmn_canvas_edit import clean_bpmn_visual_metadata_artifacts

_XML = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Definitions_Test">
  <bpmn:process id="Process_Test">
    <bpmn:startEvent id="Start"><bpmn:outgoing>Flow_1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="Task_Review" name="Rivedi ordine"><bpmn:incoming>Flow_1</bpmn:incoming><bpmn:outgoing>Flow_2</bpmn:outgoing></bpmn:userTask>
    <bpmn:endEvent id="End"><bpmn:incoming>Flow_2</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start" targetRef="Task_Review" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_Review" targetRef="End" />
    <bpmn:dataObjectReference id="Data_Order" name="Ordine" />
    <bpmn:dataStoreReference id="Store_Ledger" name="Registro" />
    <bpmn:association id="Assoc_Data_Out" sourceRef="Task_Review" targetRef="Data_Order" associationDirection="One" />
    <bpmn:association id="Assoc_Store_In" sourceRef="Store_Ledger" targetRef="Task_Review" associationDirection="One" />
    <bpmn:textAnnotation id="Note_1"><bpmn:text>Regola visiva</bpmn:text></bpmn:textAnnotation>
    <bpmn:association id="Assoc_Note" sourceRef="Task_Review" targetRef="Note_1" />
  </bpmn:process>
</bpmn:definitions>"""


def test_data_objects_stores_and_their_associations_survive_cleaning():
    cleaned, report = clean_bpmn_visual_metadata_artifacts(_XML)

    assert "<bpmn:dataObjectReference" in cleaned
    assert "<bpmn:dataStoreReference" in cleaned
    assert 'id="Assoc_Data_Out"' in cleaned
    assert 'id="Assoc_Store_In"' in cleaned

    assert "<bpmn:textAnnotation" not in cleaned
    assert 'id="Assoc_Note"' not in cleaned

    removed_types = {item["type"] for item in report["removed"]}
    assert removed_types == {"textAnnotation", "association"}
    assert report["removed_count"] == 2
