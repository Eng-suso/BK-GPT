from backend.bpmn_semantic import (
    build_bpmn_semantic_model,
    semantic_model_to_bpmn_xml,
    validate_bpmn_semantic_model,
)
from backend.process_understanding import (
    ActorRelationship,
    ProcessActor,
    ProcessDataObject,
    ProcessDecision,
    ProcessHandoff,
    ProcessLoop,
    ProcessPath,
    ProcessStep,
    ProcessUnderstanding,
)
from backend.workspace_services.bpmn_canvas_edit import validate_bpmn_xml
from backend.workspace_services.bpmn_canvas_validation import validate_canvas_against_process


def test_semantic_compiler_preserves_paths_loops_handoffs_and_data_objects():
    process = ProcessUnderstanding(
        title="Order Review",
        actors=[
            ProcessActor(id="Actor_Customer", label="Cliente", kind="external_party"),
            ProcessActor(id="Actor_Ops", label="Operations", kind="team"),
        ],
        steps=[
            ProcessStep(id="Task_Receive", label="Ricevi ordine", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Review", label="Rivedi ordine", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Correct", label="Richiedi correzione ordine", actor_ids=["Actor_Customer"]),
            ProcessStep(id="Task_Ship", label="Spedisci ordine", actor_ids=["Actor_Ops"]),
        ],
        sequence=["Task_Receive", "Task_Review", "Task_Ship"],
        main_success_path=["Task_Receive", "Task_Review", "Task_Ship"],
        decisions=[
            ProcessDecision(
                id="Gateway_Order_Approved",
                label="Ordine approvato?",
                question="L'ordine e approvato?",
                outcomes=["Si", "No"],
            )
        ],
        alternative_paths=[
            ProcessPath(
                id="Alt_Correction",
                label="Correzione ordine",
                trigger_or_condition="No",
                sequence=["Task_Correct"],
                rejoins_at="Task_Review",
            )
        ],
        loops=[
            ProcessLoop(
                id="Loop_Review",
                label="Ripeti revisione",
                repeated_steps=["Task_Review", "Task_Ship"],
                condition="Serve nuova revisione",
                exit_condition="Ordine pronto per evasione",
            )
        ],
        handoffs=[
            ProcessHandoff(
                id="Handoff_Customer_Ops",
                from_actor_id="Actor_Customer",
                to_actor_id="Actor_Ops",
                artifact="Ordine corretto",
            )
        ],
        data_objects=[
            ProcessDataObject(id="Data_Order", label="Ordine", kind="record"),
        ],
        actor_relationships=[
            ActorRelationship(
                actor_id="Actor_Customer",
                relationship="external_participant",
                bpmn_pool_candidate=True,
            )
        ],
        unknowns=[],
    )

    model = build_bpmn_semantic_model(
        process_id="Process_Order_Review",
        process_name="Order Review",
        process=process,
    )
    warnings = validate_bpmn_semantic_model(model)
    xml = semantic_model_to_bpmn_xml(model)
    xml_validation = validate_bpmn_xml(xml)
    semantic_validation = validate_canvas_against_process(
        xml=xml,
        process_understanding=process,
        bpmn_semantic_model=model,
    )

    outgoing_by_node = {}
    for flow in model.sequenceFlows:
        outgoing_by_node.setdefault(flow.sourceRef, []).append(flow)

    gateway = next(node for node in model.flowNodes if node.type == "exclusiveGateway")

    assert len(outgoing_by_node[gateway.id]) >= 2
    assert any(flow.name == "No" for flow in outgoing_by_node[gateway.id])
    assert any(flow.name == "Serve nuova revisione" for flow in model.sequenceFlows)
    assert model.dataObjects[0].name == "Ordine"
    assert model.associations
    assert any("Handoff" in annotation.text for annotation in model.textAnnotations)
    assert "dataObjectReference" in xml
    assert "textAnnotation" in xml
    assert "association" in xml
    assert not any("senza almeno due uscite" in warning for warning in warnings)
    assert xml_validation["valid"] is True
    assert semantic_validation["semantic_valid"] is True
