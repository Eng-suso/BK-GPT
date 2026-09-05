import json
import re

from backend.bpmn import (
    build_bpmn_semantic_model,
    semantic_model_to_bpmn_xml,
    validate_bpmn_semantic_model,
)
from backend.process_understanding import (
    ActorRelationship,
    BpmnLaneCandidate,
    BpmnMessageFlowCandidate,
    BpmnParticipantTopology,
    BpmnPoolCandidate,
    ConsultantFinding,
    ExtractionFailure,
    ProcessActor,
    ProcessBoundaries,
    ProcessBusinessRule,
    ProcessControl,
    ProcessDataObject,
    ProcessDecision,
    ProcessDecisionOutcome,
    ProcessDocumentRequirement,
    ProcessEvent,
    ProcessExceptionPath,
    ProcessFlowEdge,
    ProcessHandoff,
    ProcessLoop,
    ProcessParticipant,
    ProcessPath,
    ProcessStep,
    ProcessUnderstanding,
    ProcessUnderstandingExtractionError,
    ProcessUnderstandingQualityReport,
    ProcessUnderstandingResult,
    QualityDimensionScore,
    QualityImprovementAction,
    QualityIssue,
    build_process_understanding,
    conservative_process_quality_report,
    process_understanding_diagnostics,
)
import backend.workspace_services.bpmn_review as bpmn_review_service
from backend.workspace_services.bpmn_review import build_bpmn_review_draft, bpmn_xml_from_review
from backend.workspace_services.bpmn_canvas_edit import (
    add_bpmn_element,
    layout_bpmn_di,
    optimize_bpmn_layout,
    validate_bpmn_layout,
    validate_bpmn_xml,
)
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
                outcome_details=[
                    ProcessDecisionOutcome(
                        id="Outcome_Order_Approved",
                        label="Si",
                        condition="Ordine approvato",
                        target_ref="Task_Ship",
                    ),
                    ProcessDecisionOutcome(
                        id="Outcome_Order_NotApproved",
                        label="No",
                        condition="Ordine non approvato",
                        target_path_id="Alt_Correction",
                    ),
                ],
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
        flow_edges=[
            ProcessFlowEdge(
                id="Edge_Receive_Review",
                source_id="Task_Receive",
                target_id="Task_Review",
                label="Ordine ricevuto",
            ),
            ProcessFlowEdge(
                id="Edge_Review_Gateway",
                source_id="Task_Review",
                target_id="Gateway_Order_Approved",
                label="Controllo completato",
            ),
            ProcessFlowEdge(
                id="Edge_Gateway_Ship",
                source_id="Gateway_Order_Approved",
                target_id="Task_Ship",
                label="Ordine approvato",
                condition="Si",
            ),
            ProcessFlowEdge(
                id="Edge_Gateway_Correct",
                source_id="Gateway_Order_Approved",
                target_id="Task_Correct",
                label="Ordine da correggere",
                condition="No",
                path_id="Alt_Correction",
            ),
            ProcessFlowEdge(
                id="Edge_Correct_Review",
                source_id="Task_Correct",
                target_id="Task_Review",
                label="Ordine corretto",
                path_id="Alt_Correction",
            ),
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
    # "Ordine" is kind=record -> a data store; no step lists it as input/output so
    # it has no association edge.
    assert [store.name for store in model.dataStores] == ["Ordine"]
    assert model.dataObjects == []
    assert model.associations == []
    assert model.textAnnotations == []
    assert model.sourceProcessUnderstanding is not None
    assert model.compilationPlan is not None
    assert model.compilationPlan.coverage.losses == []
    assert model.compilationPlan.coverage.represented_source_items == model.compilationPlan.coverage.total_source_items
    assert model.compilationPlan.data_objects[0].name == "Ordine"
    assert model.compilationPlan.data_objects[0].mapping_status == "semantic_payload"
    assert any(
        link.source.field == "handoffs" and link.source.id == "Handoff_Customer_Ops"
        for link in model.compilationPlan.coverage.traceability
    )
    assert "DeliR semantic payload" in xml
    assert "DeliR traceability" in xml
    assert "<bpmn:dataStoreReference" in xml
    assert "dataObjectReference" not in xml
    assert "textAnnotation" not in xml
    assert not any("senza almeno due uscite" in warning for warning in warnings)
    assert xml_validation["valid"] is True
    assert semantic_validation["semantic_valid"] is True


def test_compiler_builds_collaboration_pools_and_message_flows_from_topology():
    process = ProcessUnderstanding(
        title="Domanda pensione",
        actors=[
            ProcessActor(id="Actor_Richiedente", label="Richiedente", kind="person"),
            ProcessActor(id="Actor_Patronato", label="Patronato", kind="organization"),
            ProcessActor(id="Actor_INPS", label="INPS", kind="organization"),
        ],
        participants=[
            ProcessParticipant(
                id="Participant_Patronato",
                label="Patronato",
                actor_id="Actor_Patronato",
                kind="organization",
                bpmn_container="lane",
                parent_pool_id="Pool_Patronato",
            ),
            ProcessParticipant(
                id="Participant_INPS",
                label="INPS",
                actor_id="Actor_INPS",
                kind="public_authority",
                bpmn_container="pool",
            ),
        ],
        bpmn_topology=BpmnParticipantTopology(
            pools=[
                BpmnPoolCandidate(
                    id="Pool_Patronato",
                    label="Canale patronato",
                    participant_id="Participant_Patronato",
                    actor_ids=["Actor_Richiedente", "Actor_Patronato"],
                ),
                BpmnPoolCandidate(
                    id="Pool_INPS",
                    label="INPS",
                    participant_id="Participant_INPS",
                    actor_ids=["Actor_INPS"],
                    is_external=True,
                    rendering_intent="black_box",
                ),
            ],
            lanes=[
                BpmnLaneCandidate(id="Lane_Richiedente", label="Richiedente", pool_id="Pool_Patronato", actor_ids=["Actor_Richiedente"]),
                BpmnLaneCandidate(id="Lane_Patronato", label="Patronato", pool_id="Pool_Patronato", actor_ids=["Actor_Patronato"]),
            ],
            message_flows=[
                BpmnMessageFlowCandidate(
                    id="MessageFlow_Domanda",
                    label="Domanda trasmessa a INPS",
                    from_participant_id="Participant_Patronato",
                    to_participant_id="Participant_INPS",
                    source_ref="Task_InoltraDomanda",
                    artifact="Domanda pensione",
                )
            ],
            black_box_participant_ids=["Participant_INPS"],
        ),
        steps=[
            ProcessStep(id="Task_Consegna", label="Consegna documenti", actor_ids=["Actor_Richiedente"]),
            ProcessStep(id="Task_Verifica", label="Verifica requisiti", actor_ids=["Actor_Patronato"]),
            ProcessStep(id="Task_InoltraDomanda", label="Inoltra domanda a INPS", actor_ids=["Actor_Patronato"]),
        ],
        main_success_path=["Task_Consegna", "Task_Verifica", "Task_InoltraDomanda"],
        sequence=["Task_Consegna", "Task_Verifica", "Task_InoltraDomanda"],
    )

    model = build_bpmn_semantic_model(
        process_id="Process_Domanda_Pensione",
        process_name="Domanda pensione",
        process=process,
    )

    assert model.collaborationId is not None
    primary = next(p for p in model.participants if p.processRef == model.id)
    external = next(p for p in model.participants if p.processRef is None)
    assert primary.name == "Canale patronato"
    assert external.isExternal is True
    assert external.rendering == "black_box"
    assert {lane.name for lane in model.lanes} == {"Richiedente", "Patronato"}
    assert len(model.messageFlows) == 1
    flow = model.messageFlows[0]
    inoltra_node = next(node for node in model.flowNodes if node.name == "Inoltra domanda a INPS")
    assert flow.sourceRef == inoltra_node.id
    assert flow.targetRef == external.id

    xml = semantic_model_to_bpmn_xml(model)
    assert f'<bpmn:collaboration id="{model.collaborationId}"' in xml
    assert xml.count("<bpmn:participant ") == 2
    assert f'processRef="{model.id}"' in xml
    assert "<bpmn:messageFlow " in xml
    assert f'bpmnElement="{model.collaborationId}"' in xml
    assert f'bpmnElement="{primary.id}"' in xml
    assert f'bpmnElement="{external.id}"' in xml
    assert validate_bpmn_xml(xml)["valid"] is True
    assert validate_canvas_against_process(
        xml=xml, process_understanding=process, bpmn_semantic_model=model
    )["semantic_valid"] is True

    laid_out, report = optimize_bpmn_layout(xml)
    assert "<bpmn:collaboration " in laid_out
    assert f'bpmnElement="{external.id}"' in laid_out
    assert report["valid"] is True
    assert len(report["attempts"]) == 1


def test_loop_gateway_splice_preserves_flow_edge_label_and_condition():
    process = ProcessUnderstanding(
        title="Loop con flow_edge",
        actors=[ProcessActor(id="Actor_Ops", label="Operations", kind="team")],
        steps=[
            ProcessStep(id="Task_Draft", label="Bozza", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Review", label="Revisione", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Publish", label="Pubblica", actor_ids=["Actor_Ops"]),
        ],
        main_success_path=["Task_Draft", "Task_Review", "Task_Publish"],
        sequence=["Task_Draft", "Task_Review", "Task_Publish"],
        loops=[
            ProcessLoop(id="L", label="rework", repeated_steps=["Task_Draft", "Task_Review"], condition="modifiche")
        ],
        flow_edges=[
            # names the loop tail's forward transition; after the gateway splice
            # this flow leaves the gateway, not Task_Review
            ProcessFlowEdge(
                id="e_exit", source_id="Task_Review", target_id="Task_Publish",
                label="bozza approvata", condition="nessuna modifica",
            ),
        ],
    )
    model = build_bpmn_semantic_model(
        process_id="P", process_name="Loop con flow_edge", process=process
    )
    publish = next(n.id for n in model.flowNodes if n.name == "Pubblica")
    exit_flow = next(f for f in model.sequenceFlows if f.targetRef == publish)
    assert exit_flow.name == "bozza approvata"
    assert exit_flow.conditionExpression == "nessuna modifica"
    assert any("flow_edges:e_exit" in ref for ref in exit_flow.sourceRefs)
    gateway = next(n for n in model.flowNodes if n.id == exit_flow.sourceRef)
    assert gateway.type == "exclusiveGateway"


def test_serializer_skips_dangling_sequence_flow_instead_of_crashing():
    model = build_bpmn_semantic_model(
        process_id="P",
        process_name="P",
        process=ProcessUnderstanding(
            title="P",
            actors=[ProcessActor(id="A", label="A", kind="team")],
            steps=[ProcessStep(id="T", label="T", actor_ids=["A"])],
            sequence=["T"],
        ),
    ).model_dump(mode="json")
    model["sequenceFlows"].append({"id": "F_ghost", "sourceRef": "T", "targetRef": "does_not_exist"})
    from backend.bpmn import BPMNSemanticModel

    xml = semantic_model_to_bpmn_xml(BPMNSemanticModel.model_validate(model))
    assert "F_ghost" in xml  # the sequenceFlow element is still written
    assert "F_ghost_di" not in xml  # but its edge is skipped, no KeyError


def test_distinct_end_events_are_kept_separate():
    process = ProcessUnderstanding(
        title="Domanda con esiti distinti",
        actors=[ProcessActor(id="Actor_Ops", label="Operations", kind="team")],
        events=[
            ProcessEvent(id="End_OK", label="Domanda accolta", type="end"),
            ProcessEvent(id="End_KO", label="Domanda respinta", type="end"),
        ],
        steps=[
            ProcessStep(id="Task_Check", label="Valuta domanda", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Grant", label="Concedi", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Reject", label="Rifiuta", actor_ids=["Actor_Ops"]),
        ],
        main_success_path=["Task_Check", "Task_Grant"],
        sequence=["Task_Check", "Task_Grant"],
        boundaries=ProcessBoundaries(success_end="Domanda accolta", failure_ends=["Domanda respinta"]),
        decisions=[
            ProcessDecision(
                id="Gateway_Esito",
                label="Requisiti ok?",
                question="Requisiti soddisfatti?",
                outcomes=["Si", "No"],
                outcome_details=[
                    ProcessDecisionOutcome(id="o_si", label="Si", target_ref="Task_Grant"),
                    ProcessDecisionOutcome(id="o_no", label="No", target_path_id="Alt_Reject"),
                ],
            )
        ],
        alternative_paths=[
            ProcessPath(
                id="Alt_Reject",
                label="Rifiuto domanda",
                trigger_or_condition="No",
                sequence=["Task_Reject"],
                ends_at="End_KO",
            )
        ],
        flow_edges=[
            ProcessFlowEdge(id="e1", source_id="Task_Check", target_id="Gateway_Esito", label="valutazione fatta"),
        ],
    )
    model = build_bpmn_semantic_model(
        process_id="Process_Esiti", process_name="Domanda con esiti distinti", process=process
    )
    end_nodes = [n for n in model.flowNodes if n.type == "endEvent"]
    assert {n.name for n in end_nodes} == {"Domanda accolta", "Domanda respinta"}
    reject_task = next(n.id for n in model.flowNodes if n.name == "Rifiuta")
    ko_end = next(n.id for n in end_nodes if n.name == "Domanda respinta")
    assert any(f.sourceRef == reject_task and f.targetRef == ko_end for f in model.sequenceFlows)


def test_loop_compiles_through_an_exclusive_gateway_and_is_sound():
    from backend.bpmn.soundness import analyze_control_flow

    process = ProcessUnderstanding(
        title="Revisione ciclica",
        actors=[ProcessActor(id="Actor_Ops", label="Operations", kind="team")],
        steps=[
            ProcessStep(id="Task_Draft", label="Prepara bozza", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Review", label="Rivedi", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Publish", label="Pubblica", actor_ids=["Actor_Ops"]),
        ],
        main_success_path=["Task_Draft", "Task_Review", "Task_Publish"],
        sequence=["Task_Draft", "Task_Review", "Task_Publish"],
        loops=[
            ProcessLoop(
                id="Loop_Rework",
                label="Rilavorazione bozza",
                repeated_steps=["Task_Draft", "Task_Review"],
                condition="servono modifiche",
                exit_condition="bozza approvata",
            )
        ],
    )
    model = build_bpmn_semantic_model(
        process_id="Process_Loop", process_name="Revisione ciclica", process=process
    )

    review_node = next(n for n in model.flowNodes if n.name == "Rivedi")
    review_out = [f for f in model.sequenceFlows if f.sourceRef == review_node.id]
    assert len(review_out) == 1  # no implicit split: the single exit goes to the loop gateway
    gateway = next(n for n in model.flowNodes if n.id == review_out[0].targetRef)
    assert gateway.type == "exclusiveGateway"
    gateway_out = [f for f in model.sequenceFlows if f.sourceRef == gateway.id]
    assert {f.targetRef for f in gateway_out} == {
        next(n.id for n in model.flowNodes if n.name == "Prepara bozza"),
        next(n.id for n in model.flowNodes if n.name == "Pubblica"),
    }
    loop_branch = next(f for f in gateway_out if f.conditionExpression == "servono modifiche")
    assert gateway.defaultFlowId and gateway.defaultFlowId != loop_branch.id

    report = analyze_control_flow(model)
    assert not any(i.code == "implicit_parallel_split" for i in report.errors)
    assert report.is_sound
    assert validate_bpmn_xml(semantic_model_to_bpmn_xml(model))["valid"] is True


def _canvas_xml(process_body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
        'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
        'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Test">\n'
        f'  <bpmn:process id="Process_Test">\n{process_body}\n  </bpmn:process>\n'
        '  <bpmndi:BPMNDiagram id="Diagram"><bpmndi:BPMNPlane id="Plane" bpmnElement="Process_Test" /></bpmndi:BPMNDiagram>\n'
        '</bpmn:definitions>'
    )


def test_canvas_validation_rejects_single_branch_decision_gateway():
    xml = _canvas_xml(
        """    <bpmn:startEvent id="Start"><bpmn:outgoing>f1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:exclusiveGateway id="Gw"><bpmn:incoming>f1</bpmn:incoming><bpmn:outgoing>f2</bpmn:outgoing></bpmn:exclusiveGateway>
    <bpmn:task id="Task_Do" name="Esegui"><bpmn:incoming>f2</bpmn:incoming><bpmn:outgoing>f3</bpmn:outgoing></bpmn:task>
    <bpmn:endEvent id="End"><bpmn:incoming>f3</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="f1" sourceRef="Start" targetRef="Gw" />
    <bpmn:sequenceFlow id="f2" sourceRef="Gw" targetRef="Task_Do" />
    <bpmn:sequenceFlow id="f3" sourceRef="Task_Do" targetRef="End" />"""
    )

    result = validate_canvas_against_process(xml=xml)

    assert result["semantic_valid"] is False
    assert any("meno di due rami" in issue for issue in result["issues"])


def test_canvas_validation_rejects_gateway_that_joins_and_splits():
    xml = _canvas_xml(
        """    <bpmn:startEvent id="Start"><bpmn:outgoing>f1</bpmn:outgoing><bpmn:outgoing>f2</bpmn:outgoing></bpmn:startEvent>
    <bpmn:task id="Task_A" name="A"><bpmn:incoming>f1</bpmn:incoming><bpmn:outgoing>f3</bpmn:outgoing></bpmn:task>
    <bpmn:task id="Task_B" name="B"><bpmn:incoming>f2</bpmn:incoming><bpmn:outgoing>f4</bpmn:outgoing></bpmn:task>
    <bpmn:exclusiveGateway id="Gw"><bpmn:incoming>f3</bpmn:incoming><bpmn:incoming>f4</bpmn:incoming><bpmn:outgoing>f5</bpmn:outgoing><bpmn:outgoing>f6</bpmn:outgoing></bpmn:exclusiveGateway>
    <bpmn:task id="Task_X" name="X"><bpmn:incoming>f5</bpmn:incoming><bpmn:outgoing>f7</bpmn:outgoing></bpmn:task>
    <bpmn:task id="Task_Y" name="Y"><bpmn:incoming>f6</bpmn:incoming><bpmn:outgoing>f8</bpmn:outgoing></bpmn:task>
    <bpmn:endEvent id="End"><bpmn:incoming>f7</bpmn:incoming><bpmn:incoming>f8</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="f1" sourceRef="Start" targetRef="Task_A" />
    <bpmn:sequenceFlow id="f2" sourceRef="Start" targetRef="Task_B" />
    <bpmn:sequenceFlow id="f3" sourceRef="Task_A" targetRef="Gw" />
    <bpmn:sequenceFlow id="f4" sourceRef="Task_B" targetRef="Gw" />
    <bpmn:sequenceFlow id="f5" sourceRef="Gw" targetRef="Task_X" />
    <bpmn:sequenceFlow id="f6" sourceRef="Gw" targetRef="Task_Y" />
    <bpmn:sequenceFlow id="f7" sourceRef="Task_X" targetRef="End" />
    <bpmn:sequenceFlow id="f8" sourceRef="Task_Y" targetRef="End" />"""
    )

    result = validate_canvas_against_process(xml=xml)

    assert result["semantic_valid"] is False
    assert any("unisce e divide" in issue for issue in result["issues"])


def test_canvas_validation_rejects_gateway_wired_to_nothing():
    xml = _canvas_xml(
        """    <bpmn:startEvent id="Start"><bpmn:outgoing>f1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:task id="Task_Do" name="Esegui"><bpmn:incoming>f1</bpmn:incoming><bpmn:outgoing>f2</bpmn:outgoing><bpmn:outgoing>f3</bpmn:outgoing></bpmn:task>
    <bpmn:endEvent id="End"><bpmn:incoming>f2</bpmn:incoming></bpmn:endEvent>
    <bpmn:exclusiveGateway id="Gw"><bpmn:incoming>f3</bpmn:incoming></bpmn:exclusiveGateway>
    <bpmn:sequenceFlow id="f1" sourceRef="Start" targetRef="Task_Do" />
    <bpmn:sequenceFlow id="f2" sourceRef="Task_Do" targetRef="End" />
    <bpmn:sequenceFlow id="f3" sourceRef="Task_Do" targetRef="Gw" />"""
    )

    result = validate_canvas_against_process(xml=xml)

    assert result["semantic_valid"] is False
    assert any("non e' collegato al flusso" in issue for issue in result["issues"])


def test_exceptions_compile_to_boundary_events_on_their_step():
    process = ProcessUnderstanding(
        title="Gestione eccezioni",
        actors=[ProcessActor(id="Actor_Ops", label="Operations", kind="team")],
        steps=[
            ProcessStep(id="Task_Wait", label="Attendi pagamento", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Close", label="Chiudi pratica", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Chase", label="Sollecita cliente", actor_ids=["Actor_Ops"]),
        ],
        main_success_path=["Task_Wait", "Task_Close"],
        sequence=["Task_Wait", "Task_Close"],
        exceptions=[
            ProcessExceptionPath(
                id="Exc_Timeout",
                label="Pagamento non ricevuto entro 30 giorni",
                trigger="scadenza 30 giorni",
                handling="Avvia sollecito",
                attached_to_step_id="Task_Wait",
                interrupting=True,
            ),
            ProcessExceptionPath(
                id="Exc_Escalation",
                label="Reclamo aperto durante la lavorazione",
                trigger="segnalazione parallela dal cliente",
                handling="Gestisci reclamo in parallelo",
                attached_to_step_id="Task_Close",
                interrupting=False,
            ),
            ProcessExceptionPath(
                id="Exc_SystemDown",
                label="Sistema non disponibile",
                trigger="errore tecnico bloccante",
                handling="Riprova piu tardi",
                attached_to_step_id="Task_Close",
                interrupting=False,
                is_defined=False,
            ),
        ],
        flow_edges=[
            ProcessFlowEdge(id="e_rejoin", source_id="Exc_Timeout", target_id="Task_Chase", label="dopo timeout"),
        ],
    )
    model = build_bpmn_semantic_model(
        process_id="Process_Exc", process_name="Gestione eccezioni", process=process
    )
    boundary = {n.name: n for n in model.flowNodes if n.type == "boundaryEvent"}
    assert set(boundary) == {
        "Pagamento non ricevuto entro 30 giorni",
        "Reclamo aperto durante la lavorazione",
        "Sistema non disponibile",
    }
    timeout = boundary["Pagamento non ricevuto entro 30 giorni"]
    wait_task = next(n.id for n in model.flowNodes if n.name == "Attendi pagamento")
    assert timeout.attachedToRef == wait_task
    assert timeout.eventDefinition == "timer"
    assert timeout.cancelActivity is True
    # timeout rejoins the recovery step named only in flow_edges: it is compiled
    chase = next(n.id for n in model.flowNodes if n.name == "Sollecita cliente")
    assert any(f.sourceRef == timeout.id and f.targetRef == chase for f in model.sequenceFlows)

    # non-interrupting + no error keyword -> conditional boundary, may stay non-interrupting
    escalation = boundary["Reclamo aperto durante la lavorazione"]
    assert escalation.eventDefinition == "conditional"
    assert escalation.eventConditionExpression == "segnalazione parallela dal cliente"
    assert escalation.cancelActivity is False

    # error keyword -> forced interrupting per BPMN 2.0, with a warning
    system_down = boundary["Sistema non disponibile"]
    assert system_down.eventDefinition == "error"
    assert system_down.cancelActivity is True
    assert any("interrupting" in w for w in model.model_warnings)

    for node in model.flowNodes:
        if node.type == "boundaryEvent":
            assert model.flowNodes  # boundary has an outgoing flow
            assert any(f.sourceRef == node.id for f in model.sequenceFlows)
            assert node.laneId == "Actor_Ops"

    xml = semantic_model_to_bpmn_xml(model)
    assert f'attachedToRef="{wait_task}"' in xml
    assert 'cancelActivity="false"' in xml
    assert "<bpmn:timerEventDefinition />" in xml
    assert "<bpmn:conditionalEventDefinition>" in xml
    assert (
        '<bpmn:condition xsi:type="bpmn:tFormalExpression">'
        "segnalazione parallela dal cliente</bpmn:condition>"
    ) in xml
    assert validate_bpmn_xml(xml)["valid"] is True
    assert not any(
        "senza ingresso" in w or "senza uscita" in w or "non agganciato" in w
        for w in validate_bpmn_semantic_model(model)
    )


def test_flow_graph_completion_wires_gateway_branches_and_warns_on_implicit_splits():
    process = ProcessUnderstanding(
        title="Completamento grafo",
        actors=[ProcessActor(id="Actor_Ops", label="Operations", kind="team")],
        steps=[
            ProcessStep(id="Task_A", label="A", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_B", label="B", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_C", label="C", actor_ids=["Actor_Ops"]),
        ],
        main_success_path=["Task_A", "Task_B", "Task_C"],
        sequence=["Task_A", "Task_B", "Task_C"],
        decisions=[
            ProcessDecision(
                id="Gateway_Rework",
                label="Rifare?",
                question="Servono correzioni?",
                outcomes=["Si", "No"],
                outcome_details=[
                    ProcessDecisionOutcome(id="o1", label="Si", target_ref="Task_A"),
                    ProcessDecisionOutcome(id="o2", label="No", ends_process=True),
                ],
            )
        ],
        flow_edges=[
            ProcessFlowEdge(id="ea", source_id="Task_C", target_id="Gateway_Rework", label="verifica finale"),
            ProcessFlowEdge(id="eb", source_id="Gateway_Rework", target_id="Task_A", label="Si", condition="difetti trovati"),
            ProcessFlowEdge(id="split", source_id="Task_A", target_id="Task_C", label="salta B"),
        ],
    )
    model = build_bpmn_semantic_model(
        process_id="Process_Grafo", process_name="Completamento grafo", process=process
    )
    gateway_node = next(n for n in model.flowNodes if n.type == "exclusiveGateway")
    task_a = next(n.id for n in model.flowNodes if n.name == "A")
    branches = [f for f in model.sequenceFlows if f.sourceRef == gateway_node.id]
    rework = next((f for f in branches if f.targetRef == task_a), None)
    assert rework is not None
    assert rework.conditionExpression == "difetti trovati"
    assert any("ramo implicito" in w for w in model.model_warnings)

    # the unconditioned happy branch is marked as the gateway's default flow
    assert len(branches) == 2
    default_branch = next(f for f in branches if not f.conditionExpression)
    assert gateway_node.defaultFlowId == default_branch.id

    xml = semantic_model_to_bpmn_xml(model)
    assert f'default="{default_branch.id}"' in xml
    assert validate_bpmn_xml(xml)["valid"] is True
    assert validate_canvas_against_process(
        xml=xml, process_understanding=process, bpmn_semantic_model=model
    )["semantic_valid"] is True


def test_step_types_compile_to_the_matching_bpmn_task_kinds():
    process = ProcessUnderstanding(
        title="Tipi task",
        actors=[ProcessActor(id="Actor_Ops", label="Operations", kind="team")],
        steps=[
            ProcessStep(id="Task_U", label="Compila modulo", actor_ids=["Actor_Ops"], type="user_task"),
            ProcessStep(id="Task_S", label="Invia notifica", actor_ids=["Actor_Ops"], type="send_task"),
            ProcessStep(id="Task_R", label="Attendi conferma", actor_ids=["Actor_Ops"], type="receive_task"),
            ProcessStep(id="Task_B", label="Valuta scoring", actor_ids=["Actor_Ops"], type="business_rule_task"),
            ProcessStep(id="Task_C", label="Aggiorna anagrafica", actor_ids=["Actor_Ops"], type="script_task"),
        ],
        main_success_path=["Task_U", "Task_S", "Task_R", "Task_B", "Task_C"],
        sequence=["Task_U", "Task_S", "Task_R", "Task_B", "Task_C"],
    )
    model = build_bpmn_semantic_model(
        process_id="Process_Tipi", process_name="Tipi task", process=process
    )
    types_by_name = {node.name: node.type for node in model.flowNodes}
    assert types_by_name["Invia notifica"] == "sendTask"
    assert types_by_name["Attendi conferma"] == "receiveTask"
    assert types_by_name["Valuta scoring"] == "businessRuleTask"
    assert types_by_name["Aggiorna anagrafica"] == "scriptTask"

    xml = semantic_model_to_bpmn_xml(model)
    assert "<bpmn:sendTask " in xml and "<bpmn:businessRuleTask " in xml
    assert validate_bpmn_xml(xml)["valid"] is True


def test_flow_edges_label_and_condition_the_generated_sequence_flows_without_duplicates():
    process = ProcessUnderstanding(
        title="Revisione",
        actors=[ProcessActor(id="Actor_Ops", label="Operations", kind="team")],
        steps=[
            ProcessStep(id="Task_Receive", label="Ricevi", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Review", label="Rivedi", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Fix", label="Correggi", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Ship", label="Spedisci", actor_ids=["Actor_Ops"]),
        ],
        main_success_path=["Task_Receive", "Task_Review", "Task_Ship"],
        sequence=["Task_Receive", "Task_Review", "Task_Ship"],
        decisions=[
            ProcessDecision(
                id="Gateway_Ok",
                label="Ordine corretto?",
                question="L'ordine e corretto?",
                outcomes=["Si", "No"],
                outcome_details=[
                    ProcessDecisionOutcome(id="O_Si", label="Si", target_ref="Task_Ship"),
                    ProcessDecisionOutcome(id="O_No", label="No", target_path_id="Alt_Fix"),
                ],
            )
        ],
        alternative_paths=[
            ProcessPath(id="Alt_Fix", label="Correzione", trigger_or_condition="No", sequence=["Task_Fix"], rejoins_at="Task_Review")
        ],
        flow_edges=[
            ProcessFlowEdge(id="Edge_Recv_Rev", source_id="Task_Receive", target_id="Task_Review", label="Ordine ricevuto"),
            ProcessFlowEdge(id="Edge_Rev_Gw", source_id="Task_Review", target_id="Gateway_Ok", label="Revisione completata"),
            ProcessFlowEdge(id="Edge_Gw_Ship", source_id="Gateway_Ok", target_id="Task_Ship", label="Ordine ok", condition="stato == corretto"),
            ProcessFlowEdge(id="Edge_Gw_Fix", source_id="Gateway_Ok", target_id="Task_Fix", label="Da correggere", condition="stato == errato", path_id="Alt_Fix"),
        ],
    )
    model = build_bpmn_semantic_model(
        process_id="Process_Revisione", process_name="Revisione", process=process
    )

    pairs = [(flow.sourceRef, flow.targetRef) for flow in model.sequenceFlows]
    assert len(pairs) == len(set(pairs))  # registry deduped overlapping generators

    by_name = {flow.name: flow for flow in model.sequenceFlows if flow.name}
    assert "Ordine ricevuto" in by_name
    assert "Revisione completata" in by_name
    gateway = next(node for node in model.flowNodes if node.type == "exclusiveGateway")
    gateway_out = [flow for flow in model.sequenceFlows if flow.sourceRef == gateway.id]
    assert {flow.conditionExpression for flow in gateway_out} == {"stato == corretto", "stato == errato"}
    assert any("flow_edges:Edge_Gw_Ship" in flow.sourceRefs for flow in gateway_out)

    xml = semantic_model_to_bpmn_xml(model)
    assert '<bpmn:conditionExpression xsi:type="bpmn:tFormalExpression">stato == corretto</bpmn:conditionExpression>' in xml
    assert validate_bpmn_xml(xml)["valid"] is True


def test_layout_bpmn_di_regenerates_collaboration_di_without_dangling_refs():
    process = ProcessUnderstanding(
        title="Domanda",
        actors=[
            ProcessActor(id="Actor_Ops", label="Operations", kind="team"),
            ProcessActor(id="Actor_Ext", label="Ente esterno", kind="external_party"),
        ],
        steps=[
            ProcessStep(id="Task_A", label="Prepara", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_B", label="Invia", actor_ids=["Actor_Ops"]),
        ],
        main_success_path=["Task_A", "Task_B"],
        sequence=["Task_A", "Task_B"],
    )
    model = build_bpmn_semantic_model(
        process_id="Process_Domanda", process_name="Domanda", process=process
    )
    xml = semantic_model_to_bpmn_xml(model)
    external = next(p for p in model.participants if p.processRef is None)

    grown_xml, _ = add_bpmn_element(xml, "task", "Nuovo passo")
    relaid = layout_bpmn_di(grown_xml)

    assert f'bpmnElement="{model.collaborationId}"' in relaid
    assert f'bpmnElement="{external.id}"' in relaid
    assert validate_bpmn_xml(relaid)["valid"] is True
    assert validate_bpmn_layout(relaid)["valid"] is True


def test_decision_gateway_is_created_when_anchored_to_an_intermediate_event():
    process = ProcessUnderstanding(
        title="Attesa esito",
        actors=[ProcessActor(id="Actor_Ops", label="Operations", kind="team")],
        events=[ProcessEvent(id="Msg_Esito", label="Esito ricevuto", type="message")],
        steps=[
            ProcessStep(id="Task_Invia", label="Invia richiesta", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Ok", label="Procedi", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_Ko", label="Gestisci rifiuto", actor_ids=["Actor_Ops"]),
        ],
        main_success_path=["Task_Invia", "Msg_Esito", "Task_Ok"],
        sequence=["Task_Invia", "Task_Ok"],
        decisions=[
            ProcessDecision(
                id="Gateway_Esito",
                label="Esito positivo?",
                question="L'esito e positivo?",
                outcomes=["Si", "No"],
                outcome_details=[
                    ProcessDecisionOutcome(id="O_Si", label="Si", target_ref="Task_Ok"),
                    ProcessDecisionOutcome(id="O_No", label="No", target_path_id="Alt_Ko"),
                ],
            )
        ],
        alternative_paths=[
            ProcessPath(id="Alt_Ko", label="Rifiuto", trigger_or_condition="No", sequence=["Task_Ko"], ends_at="Task_Ko")
        ],
        flow_edges=[
            ProcessFlowEdge(id="E1", source_id="Task_Invia", target_id="Msg_Esito", label="Richiesta inviata"),
            ProcessFlowEdge(id="E2", source_id="Msg_Esito", target_id="Gateway_Esito", label="Esito arrivato"),
        ],
    )
    model = build_bpmn_semantic_model(
        process_id="Process_Attesa", process_name="Attesa esito", process=process
    )
    gateway = next((n for n in model.flowNodes if n.type == "exclusiveGateway"), None)
    assert gateway is not None and gateway.name == "Esito positivo?"
    order = [n.id for n in model.flowNodes]
    event_id = next(n.id for n in model.flowNodes if n.type == "intermediateCatchEvent")
    assert order.index(event_id) < order.index(gateway.id)


def test_ordered_chain_splices_events_regardless_of_events_list_order():
    process = ProcessUnderstanding(
        title="Catena eventi",
        actors=[ProcessActor(id="Actor_Ops", label="Operations", kind="team")],
        events=[
            ProcessEvent(id="Ev_B", label="Secondo", type="message"),
            ProcessEvent(id="Ev_A", label="Primo", type="timer"),
        ],
        steps=[
            ProcessStep(id="Task_1", label="Passo 1", actor_ids=["Actor_Ops"]),
            ProcessStep(id="Task_2", label="Passo 2", actor_ids=["Actor_Ops"]),
        ],
        main_success_path=["Task_1", "Task_2"],
        sequence=["Task_1", "Task_2"],
        flow_edges=[
            ProcessFlowEdge(id="E1", source_id="Task_1", target_id="Ev_A", label="a"),
            ProcessFlowEdge(id="E2", source_id="Ev_A", target_id="Ev_B", label="b"),
        ],
    )
    model = build_bpmn_semantic_model(
        process_id="Process_Catena", process_name="Catena eventi", process=process
    )
    names = [n.name for n in model.flowNodes if n.type == "intermediateCatchEvent"]
    assert names == ["Primo", "Secondo"]


def test_compiler_splices_timer_and_message_intermediate_events_into_the_flow():
    process = ProcessUnderstanding(
        title="Decorrenza pensione",
        actors=[ProcessActor(id="Actor_Patronato", label="Patronato", kind="organization")],
        events=[
            ProcessEvent(id="Timer_Decorrenza", label="Primo del mese successivo", type="timer"),
            ProcessEvent(id="Msg_Esito", label="Esito da INPS", type="message"),
        ],
        steps=[
            ProcessStep(id="Task_Inoltra", label="Inoltra domanda", actor_ids=["Actor_Patronato"]),
            ProcessStep(id="Task_Verifica", label="Verifica ricezione", actor_ids=["Actor_Patronato"]),
        ],
        main_success_path=["Task_Inoltra", "Msg_Esito", "Task_Verifica"],
        sequence=["Task_Inoltra", "Task_Verifica"],
        flow_edges=[
            ProcessFlowEdge(id="E1", source_id="Task_Inoltra", target_id="Timer_Decorrenza", label="Domanda presentata"),
            ProcessFlowEdge(id="E2", source_id="Timer_Decorrenza", target_id="Msg_Esito", label="Alla data prevista"),
        ],
    )

    model = build_bpmn_semantic_model(
        process_id="Process_Decorrenza", process_name="Decorrenza pensione", process=process
    )
    events = [node for node in model.flowNodes if node.type == "intermediateCatchEvent"]
    assert {event.name for event in events} == {"Primo del mese successivo", "Esito da INPS"}
    timer = next(event for event in events if event.name == "Primo del mese successivo")
    message = next(event for event in events if event.name == "Esito da INPS")
    assert timer.eventDefinition == "timer"
    assert message.eventDefinition == "message"

    order = [node.id for node in model.flowNodes]
    inoltra = next(n.id for n in model.flowNodes if n.name == "Inoltra domanda")
    verifica = next(n.id for n in model.flowNodes if n.name == "Verifica ricezione")
    assert order.index(inoltra) < order.index(timer.id) < order.index(message.id) < order.index(verifica)

    xml = semantic_model_to_bpmn_xml(model)
    assert "<bpmn:timerEventDefinition />" in xml
    message_decl_id = re.search(r'<bpmn:message id="([^"]+)" name="Esito da INPS" />', xml).group(1)
    assert f'<bpmn:messageEventDefinition messageRef="{message_decl_id}" />' in xml
    assert validate_bpmn_xml(xml)["valid"] is True
    assert not any(
        "senza ingresso" in warning or "senza uscita" in warning
        for warning in validate_bpmn_semantic_model(model)
    )


def test_compiler_keeps_single_process_when_no_collaboration_topology():
    process = ProcessUnderstanding(
        title="Processo interno",
        actors=[ProcessActor(id="Actor_Ops", label="Operations", kind="team")],
        steps=[ProcessStep(id="Task_A", label="Passo A", actor_ids=["Actor_Ops"])],
        sequence=["Task_A"],
    )
    model = build_bpmn_semantic_model(
        process_id="Process_Interno", process_name="Processo interno", process=process
    )
    assert model.collaborationId is None
    assert model.participants == []
    assert model.messageFlows == []


def test_canvas_validation_requires_lossless_semantic_payload_when_process_context_exists():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" xmlns:di="http://www.omg.org/spec/DD/20100524/DI" id="Definitions_Test">
  <bpmn:process id="Process_Test">
    <bpmn:startEvent id="Start" name="Start"><bpmn:outgoing>Flow_1</bpmn:outgoing></bpmn:startEvent>
    <bpmn:userTask id="Task_Review" name="Rivedi ordine"><bpmn:incoming>Flow_1</bpmn:incoming><bpmn:outgoing>Flow_2</bpmn:outgoing></bpmn:userTask>
    <bpmn:endEvent id="End" name="End"><bpmn:incoming>Flow_2</bpmn:incoming></bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="Start" targetRef="Task_Review" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_Review" targetRef="End" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="Diagram"><bpmndi:BPMNPlane id="Plane" bpmnElement="Process_Test" /></bpmndi:BPMNDiagram>
</bpmn:definitions>"""
    process = ProcessUnderstanding(
        title="Order Review",
        steps=[ProcessStep(id="Task_Review", label="Rivedi ordine")],
        sequence=["Task_Review"],
    )

    result = validate_canvas_against_process(xml=xml, process_understanding=process)

    assert result["semantic_valid"] is False
    assert any("Payload semantico DeliR mancante" in issue for issue in result["issues"])


def test_review_xml_rejects_legacy_semantic_model_without_lossless_payload():
    legacy_semantic_model = {
        "id": "Process_Order_Review",
        "name": "Order Review",
        "flowNodes": [
            {"id": "StartEvent_1", "type": "startEvent", "name": "Start"},
            {"id": "Task_Review", "type": "userTask", "name": "Rivedi ordine"},
            {"id": "EndEvent_1", "type": "endEvent", "name": "End"},
        ],
        "sequenceFlows": [
            {"id": "Flow_1", "sourceRef": "StartEvent_1", "targetRef": "Task_Review"},
            {"id": "Flow_2", "sourceRef": "Task_Review", "targetRef": "EndEvent_1"},
        ],
    }

    try:
        bpmn_xml_from_review(
            bpmn_semantic_model_json=json.dumps(legacy_semantic_model),
        )
    except ValueError as exc:
        assert "legacy rifiutato" in str(exc)
    else:
        raise AssertionError("Expected legacy BPMNSemanticModel to be rejected.")


def test_review_xml_uses_only_canonical_semantic_model_source_of_truth():
    process = ProcessUnderstanding(
        title="Order Review",
        actors=[ProcessActor(id="Actor_Ops", label="Operations", kind="team")],
        steps=[ProcessStep(id="Task_Review", label="Rivedi ordine", actor_ids=["Actor_Ops"])],
        sequence=["Task_Review"],
        business_rules=["Gli ordini incompleti non avanzano."],
    )
    model = build_bpmn_semantic_model(
        process_id="Process_Order_Review",
        process_name="Order Review",
        process=process,
    )

    xml = bpmn_xml_from_review(
        bpmn_semantic_model_json=json.dumps(model.model_dump(mode="json")),
    )
    validation = validate_canvas_against_process(
        xml=xml,
        process_understanding=process,
    )

    assert "DeliR semantic payload" in xml
    assert "Gli ordini incompleti non avanzano." in xml
    assert validation["semantic_valid"] is True


def test_process_understanding_supports_consultant_grade_discovery_contract():
    process = ProcessUnderstanding(
        title="Richiesta pensione di vecchiaia tramite patronato",
        actors=[
            ProcessActor(id="Actor_Richiedente", label="Richiedente", kind="person"),
            ProcessActor(id="Actor_Patronato", label="Patronato", kind="organization"),
            ProcessActor(id="Actor_INPS", label="INPS", kind="organization"),
        ],
        participants=[
            ProcessParticipant(
                id="Participant_Richiedente",
                label="Richiedente",
                actor_id="Actor_Richiedente",
                kind="individual",
                responsibility="initiator",
                bpmn_container="lane",
                parent_pool_id="Pool_ProcessoRichiestaPensione",
            ),
            ProcessParticipant(
                id="Participant_INPS",
                label="INPS",
                actor_id="Actor_INPS",
                kind="public_authority",
                responsibility="service_provider",
                bpmn_container="pool",
            ),
        ],
        steps=[
            ProcessStep(id="Task_ScegliPatronato", label="Sceglie il patronato", actor_ids=["Actor_Richiedente"]),
            ProcessStep(id="Task_ConsegnaDocumenti", label="Consegna i documenti", actor_ids=["Actor_Richiedente"]),
        ],
        sequence=["Task_ScegliPatronato", "Task_ConsegnaDocumenti"],
        data_objects=[
            ProcessDataObject(id="Data_ProvvedimentoDivorzio", label="Provvedimento giudiziale di divorzio", kind="document"),
        ],
        document_requirements=[
            ProcessDocumentRequirement(
                id="DocReq_Divorzio",
                label="Copia del provvedimento giudiziale di divorzio",
                data_object_id="Data_ProvvedimentoDivorzio",
                required_when="il richiedente e divorziato",
                provided_by_actor_id="Actor_Richiedente",
                received_by_actor_id="Actor_Patronato",
                mandatory=True,
            ),
        ],
        structured_business_rules=[
            ProcessBusinessRule(
                id="Rule_Divorzio",
                label="Documento divorzio richiesto",
                condition="stato civile divorziato",
                consequence="richiedere copia del provvedimento giudiziale di divorzio",
                applies_to_ids=["Data_ProvvedimentoDivorzio"],
            ),
        ],
        flow_edges=[
            ProcessFlowEdge(
                id="Edge_Scelta_Consegna",
                source_id="Task_ScegliPatronato",
                target_id="Task_ConsegnaDocumenti",
                label="Dopo appuntamento e preparazione documenti",
            ),
        ],
        consultant_findings=[
            ConsultantFinding(
                id="Finding_INPS",
                finding="L'inoltro a INPS e necessario ma implicito nelle note.",
                category="assumption",
            )
        ],
    )

    diagnostics = process_understanding_diagnostics(process)
    review = build_bpmn_review_draft(
        bpmn_process_id="Process_Pensione",
        process_name=process.title,
        source_text="Mario Rossi sceglie il patronato e consegna i documenti.",
        process_understanding=process,
    )

    assert diagnostics.blocking == []
    assert diagnostics.counts["participants"] == 2
    assert diagnostics.counts["document_requirements"] == 1
    assert review.process_understanding.title == process.title
    assert review.bpmn_semantic_model.sourceProcessUnderstanding is not None
    assert review.bpmn_semantic_model_json().find("document_requirements") > 0
    assert "Partecipanti e contenitori BPMN suggeriti" in review.bpmn_brief
    assert "Collegamenti semantici da preservare" in review.bpmn_brief


def test_conservative_quality_fallback_never_auto_approves_flat_summary():
    process = ProcessUnderstanding(
        title="Processo narrativo debole",
        steps=[
            ProcessStep(id="Task_1", label="Riceve una richiesta e poi fa varie verifiche"),
            ProcessStep(id="Task_2", label="Gestisce la pratica"),
            ProcessStep(id="Task_3", label="Comunica esito"),
            ProcessStep(id="Task_4", label="Termina"),
        ],
        sequence=["Task_1", "Task_2", "Task_3", "Task_4"],
        decisions=[
            ProcessDecision(
                id="Gateway_1",
                label="Verifica esito?",
                question="Verifica esito?",
                outcomes=["Si", "No"],
            )
        ],
    )

    quality = conservative_process_quality_report(
        process,
        reason="Evaluator non disponibile durante il test.",
    )

    assert quality.overall_score <= 5
    assert quality.approval_recommendation != "ready_to_generate"
    assert any(issue.category == "quality_evaluator" for issue in quality.warnings)
    assert any(item.dimension == "bpmn_compilability" for item in quality.dimension_scores)


def test_process_understanding_extraction_failure_is_not_reviewable(monkeypatch):
    called = {"quality": False}

    failure = ProcessUnderstandingResult(
        status="failed",
        failure=ExtractionFailure(
            kind="timeout",
            message="request timed out",
            retryable=True,
            attempt=1,
        ),
    )

    def quality_stub(*_args, **_kwargs):
        called["quality"] = True
        raise AssertionError("quality evaluator must not run after extraction failure")

    monkeypatch.setattr(bpmn_review_service, "evaluate_process_understanding_quality", quality_stub)

    try:
        build_bpmn_review_draft(
            bpmn_process_id="Process_Test",
            process_name="Processo Test",
            source_text="descrizione processo",
            process_understanding=failure,
        )
    except ProcessUnderstandingExtractionError as exc:
        assert exc.failure.kind == "timeout"
        assert exc.failure.retryable is True
    else:
        raise AssertionError("Extraction failure must block BPMN review generation")

    assert called["quality"] is False


def test_process_understanding_builder_reports_missing_llm_without_fallback(monkeypatch):
    monkeypatch.setattr("backend.process_understanding.settings.openai_api_key", None)

    result = build_process_understanding("Processo Test", "utente descrive un processo")

    assert result.status == "failed"
    assert result.process is None
    assert result.failure is not None
    assert result.failure.kind == "configuration_error"


def test_process_understanding_builder_does_not_mask_programmer_bug(monkeypatch):
    class BrokenLLM:
        def stream(self, *_args, **_kwargs):
            raise TypeError("bug interno")

    monkeypatch.setattr("backend.process_understanding.settings.openai_api_key", "sk-test")
    monkeypatch.setattr("backend.process_understanding._understanding_llm", lambda: BrokenLLM())

    try:
        build_process_understanding("Processo Test", "descrizione")
    except TypeError as exc:
        assert "bug interno" in str(exc)
    else:
        raise AssertionError("Unexpected programmer bugs must not become ProcessUnderstanding fallback")


def test_quality_report_from_evaluator_drives_structured_review_readiness(monkeypatch):
    process = ProcessUnderstanding(
        title="Richiesta pensione di vecchiaia tramite patronato",
        objective="Presentare domanda di pensione di vecchiaia tramite patronato fino a ricezione o sollecito.",
        scope="AS-IS del canale patronato; canali online e call center fuori dettaglio operativo.",
        actors=[
            ProcessActor(id="Actor_Richiedente", label="Richiedente", kind="person"),
            ProcessActor(id="Actor_Patronato", label="Patronato", kind="organization"),
            ProcessActor(id="Actor_INPS", label="INPS", kind="organization"),
        ],
        participants=[
            ProcessParticipant(
                id="Participant_Richiedente",
                label="Richiedente",
                actor_id="Actor_Richiedente",
                kind="individual",
                responsibility="initiator",
                bpmn_container="lane",
                parent_pool_id="Pool_CanalePatronato",
            ),
            ProcessParticipant(
                id="Participant_Patronato",
                label="Patronato",
                actor_id="Actor_Patronato",
                kind="organization",
                responsibility="intermediary",
                bpmn_container="lane",
                parent_pool_id="Pool_CanalePatronato",
            ),
            ProcessParticipant(
                id="Participant_INPS",
                label="INPS",
                actor_id="Actor_INPS",
                kind="public_authority",
                responsibility="service_provider",
                bpmn_container="pool",
            ),
        ],
        bpmn_topology=BpmnParticipantTopology(
            pools=[
                BpmnPoolCandidate(
                    id="Pool_CanalePatronato",
                    label="Richiesta tramite patronato",
                    participant_id="Participant_Patronato",
                    actor_ids=["Actor_Richiedente", "Actor_Patronato"],
                ),
                BpmnPoolCandidate(
                    id="Pool_INPS",
                    label="INPS",
                    participant_id="Participant_INPS",
                    actor_ids=["Actor_INPS"],
                    is_external=True,
                    rendering_intent="black_box",
                ),
            ],
            lanes=[
                BpmnLaneCandidate(
                    id="Lane_Richiedente",
                    label="Richiedente",
                    pool_id="Pool_CanalePatronato",
                    participant_id="Participant_Richiedente",
                    actor_ids=["Actor_Richiedente"],
                ),
                BpmnLaneCandidate(
                    id="Lane_Patronato",
                    label="Patronato",
                    pool_id="Pool_CanalePatronato",
                    participant_id="Participant_Patronato",
                    actor_ids=["Actor_Patronato"],
                ),
            ],
            message_flows=[
                BpmnMessageFlowCandidate(
                    id="MessageFlow_Domanda_INPS",
                    label="Domanda pensione trasmessa a INPS",
                    from_participant_id="Participant_Patronato",
                    to_participant_id="Participant_INPS",
                    from_actor_id="Actor_Patronato",
                    to_actor_id="Actor_INPS",
                    source_ref="Task_InoltraDomanda",
                    artifact="Domanda pensione",
                )
            ],
            black_box_participant_ids=["Participant_INPS"],
        ),
        events=[
            ProcessEvent(id="StartEvent_Decisione", label="Decisione di richiedere pensione", type="start"),
            ProcessEvent(
                id="Timer_Decorrenza",
                label="Primo giorno del mese successivo",
                type="timer",
                timing="Primo giorno del mese successivo alla domanda",
            ),
            ProcessEvent(id="EndEvent_PensioneRicevuta", label="Pensione ricevuta", type="end"),
            ProcessEvent(id="EndEvent_Sollecito", label="Sollecito attivato", type="end"),
        ],
        steps=[
            ProcessStep(id="Task_ScegliePatronato", label="Sceglie il patronato", actor_ids=["Actor_Richiedente"]),
            ProcessStep(id="Task_TelefonaPatronato", label="Telefona al patronato", actor_ids=["Actor_Richiedente"]),
            ProcessStep(id="Task_FissaAppuntamento", label="Fissa appuntamento", actor_ids=["Actor_Patronato"]),
            ProcessStep(id="Task_ComunicaDocumenti", label="Comunica documenti richiesti", actor_ids=["Actor_Patronato"]),
            ProcessStep(id="Task_PreparaDocumenti", label="Prepara documenti", actor_ids=["Actor_Richiedente"]),
            ProcessStep(id="Task_ConsegnaDocumenti", label="Consegna documenti", actor_ids=["Actor_Richiedente"]),
            ProcessStep(id="Task_VerificaRequisiti", label="Verifica requisiti e documenti", actor_ids=["Actor_Patronato"]),
            ProcessStep(id="Task_InoltraDomanda", label="Inoltra domanda a INPS", actor_ids=["Actor_Patronato"]),
            ProcessStep(id="Task_VerificaRicezione", label="Verifica ricezione pensione", actor_ids=["Actor_Richiedente"]),
            ProcessStep(id="Task_RichiamaPatronato", label="Richiama il patronato", actor_ids=["Actor_Richiedente"]),
            ProcessStep(id="Task_AttivaSollecito", label="Attiva sollecito", actor_ids=["Actor_Patronato"]),
        ],
        main_success_path=[
            "Task_ScegliePatronato",
            "Task_TelefonaPatronato",
            "Task_FissaAppuntamento",
            "Task_ComunicaDocumenti",
            "Task_PreparaDocumenti",
            "Task_ConsegnaDocumenti",
            "Task_VerificaRequisiti",
            "Task_InoltraDomanda",
            "Task_VerificaRicezione",
        ],
        sequence=[
            "Task_ScegliePatronato",
            "Task_TelefonaPatronato",
            "Task_FissaAppuntamento",
            "Task_ComunicaDocumenti",
            "Task_PreparaDocumenti",
            "Task_ConsegnaDocumenti",
            "Task_VerificaRequisiti",
            "Task_InoltraDomanda",
            "Task_VerificaRicezione",
        ],
        decisions=[
            ProcessDecision(
                id="Gateway_Modalita",
                label="Modalita scelta?",
                question="Quale modalita di presentazione viene scelta?",
                outcomes=["Patronato", "Online", "Call center"],
                outcome_details=[
                    ProcessDecisionOutcome(id="Outcome_Patronato", label="Patronato", target_ref="Task_TelefonaPatronato"),
                    ProcessDecisionOutcome(id="Outcome_Online", label="Online", target_path_id="Alt_Online"),
                    ProcessDecisionOutcome(id="Outcome_CallCenter", label="Call center", target_path_id="Alt_CallCenter"),
                ],
            ),
            ProcessDecision(
                id="Gateway_PensioneRicevuta",
                label="Pensione ricevuta alla data prevista?",
                question="La pensione e stata ricevuta alla data prevista?",
                outcomes=["Si", "No"],
                outcome_details=[
                    ProcessDecisionOutcome(id="Outcome_Ricevuta", label="Si", target_ref="EndEvent_PensioneRicevuta", ends_process=True),
                    ProcessDecisionOutcome(id="Outcome_NonRicevuta", label="No", target_ref="Task_RichiamaPatronato"),
                ],
            ),
        ],
        alternative_paths=[
            ProcessPath(
                id="Alt_Sollecito",
                label="Pensione non ricevuta",
                trigger_or_condition="No alla verifica ricezione pensione",
                sequence=["Task_RichiamaPatronato", "Task_AttivaSollecito"],
                ends_at="EndEvent_Sollecito",
            ),
        ],
        out_of_scope_alternatives=[
            ProcessPath(id="Alt_Online", label="Presentazione online", trigger_or_condition="Scelta online", ends_at="EndEvent_PensioneRicevuta"),
            ProcessPath(
                id="Alt_CallCenter",
                label="Presentazione tramite call center",
                trigger_or_condition="Scelta call center",
                ends_at="EndEvent_PensioneRicevuta",
            ),
        ],
        data_objects=[
            ProcessDataObject(id="Data_DocumentoIdentita", label="Documento identita valido", kind="document"),
            ProcessDataObject(id="Data_ProvvedimentoDivorzio", label="Provvedimento giudiziale di divorzio", kind="document"),
        ],
        document_requirements=[
            ProcessDocumentRequirement(
                id="DocReq_DocumentoIdentita",
                label="Copia documento identita valido",
                data_object_id="Data_DocumentoIdentita",
                required_when="sempre",
                provided_by_actor_id="Actor_Richiedente",
                received_by_actor_id="Actor_Patronato",
                validation_owner_actor_id="Actor_Patronato",
                mandatory=True,
            ),
            ProcessDocumentRequirement(
                id="DocReq_Divorzio",
                label="Copia provvedimento giudiziale di divorzio",
                data_object_id="Data_ProvvedimentoDivorzio",
                required_when="richiedente divorziato",
                provided_by_actor_id="Actor_Richiedente",
                received_by_actor_id="Actor_Patronato",
                validation_owner_actor_id="Actor_Patronato",
                mandatory=True,
            ),
        ],
        controls=[
            ProcessControl(
                id="Control_Requisiti",
                label="Controllo requisiti pensione",
                control_type="eligibility",
                checked_item="67 anni di eta e 20 anni di contributi",
                control_owner_actor_id="Actor_Patronato",
                pass_condition="requisiti soddisfatti",
                fail_condition="requisiti non soddisfatti",
                pass_target_ref="Task_InoltraDomanda",
            ),
            ProcessControl(
                id="Control_Documenti",
                label="Controllo documentazione",
                control_type="document_correctness",
                checked_item="completezza e correttezza documenti richiesti",
                control_owner_actor_id="Actor_Patronato",
                pass_condition="documentazione corretta",
                fail_condition="documentazione mancante o errata",
                pass_target_ref="Task_InoltraDomanda",
            ),
        ],
        structured_business_rules=[
            ProcessBusinessRule(
                id="Rule_Decorrenza",
                label="Decorrenza pensione",
                condition="domanda presentata e requisiti/documenti corretti",
                consequence="pensione attesa dal primo giorno del mese successivo",
                applies_to_ids=["Timer_Decorrenza"],
            ),
            ProcessBusinessRule(
                id="Rule_Divorzio",
                label="Documento divorzio richiesto",
                condition="richiedente divorziato",
                consequence="richiedere copia del provvedimento giudiziale di divorzio",
                applies_to_ids=["DocReq_Divorzio"],
            ),
            ProcessBusinessRule(
                id="Rule_InoltroINPS",
                label="Inoltro domanda implicito",
                consequence="il patronato inoltra la domanda a INPS",
                applies_to_ids=["Task_InoltraDomanda"],
                certainty="inferred",
            ),
        ],
        handoffs=[
            ProcessHandoff(
                id="Handoff_Richiedente_Patronato",
                from_actor_id="Actor_Richiedente",
                to_actor_id="Actor_Patronato",
                artifact="Documentazione pensione",
                trigger="Appuntamento al patronato",
            ),
            ProcessHandoff(
                id="Handoff_Patronato_INPS",
                from_actor_id="Actor_Patronato",
                to_actor_id="Actor_INPS",
                artifact="Domanda pensione",
                trigger="Documentazione corretta",
            ),
        ],
        flow_edges=[
            ProcessFlowEdge(id="Edge_Start_Scelta", source_id="StartEvent_Decisione", target_id="Task_ScegliePatronato", label="Decisione di presentare domanda"),
            ProcessFlowEdge(id="Edge_Scelta_Modalita", source_id="Task_ScegliePatronato", target_id="Gateway_Modalita", label="Dopo confronto delle modalita"),
            ProcessFlowEdge(id="Edge_Modalita_Telefono", source_id="Gateway_Modalita", target_id="Task_TelefonaPatronato", label="Canale patronato scelto", condition="Patronato"),
            ProcessFlowEdge(id="Edge_Telefono_Appuntamento", source_id="Task_TelefonaPatronato", target_id="Task_FissaAppuntamento", label="Richiesta appuntamento"),
            ProcessFlowEdge(id="Edge_Appuntamento_Documenti", source_id="Task_FissaAppuntamento", target_id="Task_ComunicaDocumenti", label="Appuntamento fissato"),
            ProcessFlowEdge(id="Edge_Documenti_Prepara", source_id="Task_ComunicaDocumenti", target_id="Task_PreparaDocumenti", label="Lista documenti ricevuta"),
            ProcessFlowEdge(id="Edge_Prepara_Consegna", source_id="Task_PreparaDocumenti", target_id="Task_ConsegnaDocumenti", label="Documenti preparati"),
            ProcessFlowEdge(id="Edge_Consegna_Verifica", source_id="Task_ConsegnaDocumenti", target_id="Task_VerificaRequisiti", label="Documentazione consegnata"),
            ProcessFlowEdge(id="Edge_Verifica_Inoltro", source_id="Task_VerificaRequisiti", target_id="Task_InoltraDomanda", label="Requisiti e documenti corretti"),
            ProcessFlowEdge(id="Edge_Inoltro_Timer", source_id="Task_InoltraDomanda", target_id="Timer_Decorrenza", label="Domanda presentata"),
            ProcessFlowEdge(id="Edge_Timer_Verifica", source_id="Timer_Decorrenza", target_id="Task_VerificaRicezione", label="Alla data prevista"),
            ProcessFlowEdge(id="Edge_Verifica_Gateway", source_id="Task_VerificaRicezione", target_id="Gateway_PensioneRicevuta", label="Controllo accredito pensione"),
            ProcessFlowEdge(id="Edge_Gateway_Fine", source_id="Gateway_PensioneRicevuta", target_id="EndEvent_PensioneRicevuta", label="Pensione ricevuta", condition="Si"),
            ProcessFlowEdge(id="Edge_Gateway_Richiamo", source_id="Gateway_PensioneRicevuta", target_id="Task_RichiamaPatronato", label="Pensione non ricevuta", condition="No"),
            ProcessFlowEdge(id="Edge_Richiamo_Sollecito", source_id="Task_RichiamaPatronato", target_id="Task_AttivaSollecito", label="Richiesta sollecito"),
            ProcessFlowEdge(id="Edge_Sollecito_Fine", source_id="Task_AttivaSollecito", target_id="EndEvent_Sollecito", label="Sollecito attivato"),
        ],
        boundaries=ProcessBoundaries(
            start_event="Decisione di richiedere pensione di vecchiaia",
            success_end="Pensione ricevuta",
            failure_ends=["Sollecito attivato"],
            in_scope=["Presentazione tramite patronato"],
            out_of_scope=["Presentazione online", "Presentazione tramite call center"],
        ),
        assumptions=["L'inoltro della domanda a INPS e implicito nel ruolo del patronato."],
        consultant_findings=[
            ConsultantFinding(
                id="Finding_Inoltro",
                finding="L'inoltro a INPS e necessario ma implicito nelle note.",
                category="assumption",
                recommendation="Mantenerlo come attivita inferita nella review.",
            )
        ],
    )

    def evaluator_stub(
        candidate: ProcessUnderstanding,
        *,
        source_text: str = "",
        bpmn_warnings: list[str] | None = None,
        use_llm: bool = True,
    ) -> ProcessUnderstandingQualityReport:
        assert candidate.title == process.title
        assert source_text == "Caso pensione tramite patronato"
        assert bpmn_warnings is not None
        assert use_llm is True
        return ProcessUnderstandingQualityReport(
            overall_score=9,
            dimension_scores=[
                QualityDimensionScore(
                    dimension="pool_lane_separation",
                    score=9,
                    findings=["Pool/lane e black box separati in modo coerente."],
                ),
                QualityDimensionScore(
                    dimension="flow_edge_readability",
                    score=9,
                    findings=["Flow edge leggibili e orientati alla generazione canvas."],
                ),
            ],
            blocking_issues=[],
            warnings=[
                QualityIssue(
                    id="QualityWarning_Assumption",
                    severity="note",
                    category="assumption",
                    message="Inoltro a INPS mantenuto come inferenza esplicita.",
                )
            ],
            improvement_actions=[
                QualityImprovementAction(
                    id="Improve_Layout",
                    priority="low",
                    target_field="bpmn_layout",
                    action="Mantenere il ramo di sollecito sotto il main path.",
                )
            ],
            approval_recommendation="ready_to_generate",
        )

    monkeypatch.setattr(
        bpmn_review_service,
        "evaluate_process_understanding_quality",
        evaluator_stub,
    )
    review = build_bpmn_review_draft(
        bpmn_process_id="Process_Pensione",
        process_name=process.title,
        source_text="Caso pensione tramite patronato",
        process_understanding=process,
    )

    assert review.readiness_score >= 9
    assert review.quality_report.approval_recommendation == "ready_to_generate"
    assert json.loads(review.process_understanding_json())["quality_report"]["overall_score"] == 9
    assert "Controlli e verifiche" in review.bpmn_brief
    assert "Topologia BPMN proposta" in review.bpmn_brief
