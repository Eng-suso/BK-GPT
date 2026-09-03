"""End events: terminate definition from boundaries.terminating_ends."""

from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.process_understanding import (
    ProcessBoundaries,
    ProcessDecision,
    ProcessDecisionOutcome,
    ProcessEvent,
    ProcessFlowEdge,
    ProcessPath,
    ProcessStep,
    ProcessUnderstanding,
)


def _process(**kw) -> ProcessUnderstanding:
    """
    Construct a default request process model, applying any supplied field overrides.
    
    Parameters:
    	**kw: Field values that override the default process configuration.
    
    Returns:
    	ProcessUnderstanding: The configured request process model.
    """
    base = dict(
        title="Richiesta",
        steps=[
            ProcessStep(id="T1", label="Ricevi richiesta"),
            ProcessStep(id="T2", label="Valuta richiesta"),
            ProcessStep(id="T3", label="Evadi richiesta"),
        ],
        sequence=["T1", "T2", "T3"],
        main_success_path=["T1", "T2", "T3"],
        decisions=[
            ProcessDecision(
                id="D1",
                label="Richiesta valida?",
                outcomes=["Si", "Annullata"],
                outcome_details=[
                    ProcessDecisionOutcome(id="O_ok", label="Si", target_ref="T3"),
                    ProcessDecisionOutcome(id="O_ko", label="Annullata", target_path_id="Alt_Abort"),
                ],
            )
        ],
        alternative_paths=[
            ProcessPath(
                id="Alt_Abort",
                label="Annullamento",
                trigger_or_condition="Annullata",
                sequence=[],
                ends_at="Richiesta annullata",
            )
        ],
        flow_edges=[
            ProcessFlowEdge(id="E1", source_id="T1", target_id="T2", label="ricevuta"),
            ProcessFlowEdge(id="E2", source_id="T2", target_id="D1", label="valutata"),
            ProcessFlowEdge(id="E3", source_id="D1", target_id="T3", label="Si", condition="Si"),
            ProcessFlowEdge(id="E4", source_id="D1", target_id="Alt_Abort", label="Annullata", condition="Annullata", path_id="Alt_Abort"),
        ],
        unknowns=[],
    )
    base.update(kw)
    return ProcessUnderstanding(**base)


def test_terminating_end_compiles_to_a_terminate_end_event():
    process = _process(
        boundaries=ProcessBoundaries(
            success_end="Richiesta evasa",
            terminating_ends=["Richiesta annullata"],
        )
    )
    model = build_bpmn_semantic_model(process_id="P", process_name="P", process=process)

    ends = {node.name: node for node in model.flowNodes if node.type == "endEvent"}
    assert "Richiesta annullata" in ends
    assert ends["Richiesta annullata"].eventDefinition == "terminate"
    # the configured success end is materialised and stays a plain end
    assert "Richiesta evasa" in ends
    assert ends["Richiesta evasa"].eventDefinition is None
    assert all(
        n.eventDefinition is None
        for n in model.flowNodes
        if n.type == "endEvent" and n.name != "Richiesta annullata"
    )

    xml = semantic_model_to_bpmn_xml(model)
    assert "<bpmn:terminateEventDefinition />" in xml


def test_no_terminating_ends_means_no_terminate_definition():
    model = build_bpmn_semantic_model(
        process_id="P", process_name="P",
        process=_process(boundaries=ProcessBoundaries(failure_ends=["Richiesta annullata"])),
    )
    assert all(n.eventDefinition is None for n in model.flowNodes if n.type == "endEvent")
    assert "terminateEventDefinition" not in semantic_model_to_bpmn_xml(model)


def test_declared_end_event_can_be_marked_terminating_by_its_id():
    model = build_bpmn_semantic_model(
        process_id="P",
        process_name="P",
        process=_process(
            events=[ProcessEvent(id="End_Abort", type="end", label="Pratica bloccata")],
            boundaries=ProcessBoundaries(
                success_end="Richiesta evasa",
                terminating_ends=["  end_abort  "],
            ),
        ),
    )

    declared_end = next(
        node for node in model.flowNodes if node.name == "Pratica bloccata"
    )
    assert declared_end.eventDefinition == "terminate"
    assert "<bpmn:terminateEventDefinition />" in semantic_model_to_bpmn_xml(model)


def test_failure_and_terminating_end_labels_are_deduplicated_case_insensitively():
    model = build_bpmn_semantic_model(
        process_id="P",
        process_name="P",
        process=_process(
            boundaries=ProcessBoundaries(
                success_end="Richiesta evasa",
                failure_ends=[" Richiesta annullata "],
                terminating_ends=["richiesta ANNULLATA"],
            )
        ),
    )

    matching_ends = [
        node
        for node in model.flowNodes
        if " ".join(node.name.casefold().split()) == "richiesta annullata"
    ]
    assert len(matching_ends) == 1
    assert matching_ends[0].eventDefinition == "terminate"
    assert semantic_model_to_bpmn_xml(model).count("<bpmn:terminateEventDefinition />") == 1
