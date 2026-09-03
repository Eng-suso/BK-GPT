"""Activity loop markers: multi-instance and standard loop."""

import pytest
from pydantic import ValidationError

from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.bpmn.models import BPMNFlowNode
from backend.process_understanding import (
    ProcessDecision,
    ProcessDecisionOutcome,
    ProcessFlowEdge,
    ProcessLoop,
    ProcessPath,
    ProcessStep,
    ProcessUnderstanding,
)


def _model(steps, **kw):
    """Build a BPMN semantic model from the supplied process steps and metadata.
    
    Parameters:
    	steps: Process steps used to construct the model.
    	**kw: Additional process attributes passed to `ProcessUnderstanding`.
    
    Returns:
    	The resulting BPMN semantic model.
    """
    process = ProcessUnderstanding(
        title="P",
        steps=steps,
        sequence=[s.id for s in steps],
        main_success_path=[s.id for s in steps],
        unknowns=[],
        **kw,
    )
    return build_bpmn_semantic_model(process_id="P", process_name="P", process=process)


def test_per_item_step_becomes_a_parallel_multi_instance_activity():
    model = _model([
        ProcessStep(id="T1", label="Ricevi lotto documenti"),
        ProcessStep(id="T2", label="Verifica firma documento", multiplicity="per_item"),
        ProcessStep(id="T3", label="Archivia lotto"),
    ])
    node = next(n for n in model.flowNodes if n.name == "Verifica firma documento")
    assert node.loopCharacteristics == "multiInstanceParallel"
    xml = semantic_model_to_bpmn_xml(model)
    assert '<bpmn:multiInstanceLoopCharacteristics isSequential="false" />' in xml


def test_per_item_sequential_step_becomes_sequential_multi_instance():
    model = _model([
        ProcessStep(id="T1", label="Prendi coda richieste"),
        ProcessStep(id="T2", label="Evadi richiesta", multiplicity="per_item_sequential"),
    ])
    node = next(n for n in model.flowNodes if n.name == "Evadi richiesta")
    assert node.loopCharacteristics == "multiInstanceSequential"
    assert '<bpmn:multiInstanceLoopCharacteristics isSequential="true" />' in semantic_model_to_bpmn_xml(model)


def test_single_step_loop_becomes_a_standard_loop_marker():
    model = _model(
        [
            ProcessStep(id="T1", label="Apri chiamata"),
            ProcessStep(id="T2", label="Chiama cliente"),
            ProcessStep(id="T3", label="Chiudi esito"),
        ],
        loops=[ProcessLoop(id="L1", label="Ritenta chiamata", repeated_steps=["T2"], condition="cliente non risponde")],
    )
    node = next(n for n in model.flowNodes if n.name == "Chiama cliente")
    assert node.loopCharacteristics == "standardLoop"
    assert node.loopConditionExpression == "cliente non risponde"
    assert "loops:L1" in node.sourceRefs
    xml = semantic_model_to_bpmn_xml(model)
    assert "<bpmn:standardLoopCharacteristics>" in xml
    assert '<bpmn:loopCondition xsi:type="bpmn:tFormalExpression">cliente non risponde</bpmn:loopCondition>' in xml
    # no spurious "non mappabile" warning for the single-step loop
    assert not any("non mappabile su almeno due step" in w for w in model.model_warnings)


def test_standard_loop_condition_is_escaped_in_xml():
    model = _model(
        [ProcessStep(id="T1", label="Riprova elaborazione")],
        loops=[
            ProcessLoop(
                id="L1",
                label="Riprova entro il limite",
                repeated_steps=["T1"],
                condition="  tentativi < 3 & richiesta aperta  ",
            )
        ],
    )

    node = next(n for n in model.flowNodes if n.name == "Riprova elaborazione")
    assert node.loopCharacteristics == "standardLoop"
    assert node.loopConditionExpression == "  tentativi < 3 & richiesta aperta  "
    assert (
        '<bpmn:loopCondition xsi:type="bpmn:tFormalExpression">'
        "tentativi &lt; 3 &amp; richiesta aperta</bpmn:loopCondition>"
        in semantic_model_to_bpmn_xml(model)
    )


def test_standard_loop_without_a_condition_uses_self_closing_xml():
    model = _model(
        [ProcessStep(id="T1", label="Riprova")],
        loops=[ProcessLoop(id="L1", label="Riprova", repeated_steps=["T1"])],
    )

    xml = semantic_model_to_bpmn_xml(model)
    assert "<bpmn:standardLoopCharacteristics />" in xml
    assert "<bpmn:loopCondition" not in xml


def test_alternative_path_preserves_multi_instance_multiplicity():
    process = ProcessUnderstanding(
        title="Revisione pratiche",
        steps=[
            ProcessStep(id="T1", label="Controlla lotto"),
            ProcessStep(
                id="T_Fix",
                label="Correggi pratica",
                multiplicity="per_item_sequential",
            ),
            ProcessStep(id="T2", label="Chiudi lotto"),
        ],
        sequence=["T1", "T2"],
        main_success_path=["T1", "T2"],
        decisions=[
            ProcessDecision(
                id="D1",
                label="Correzioni necessarie?",
                outcomes=["No", "Si"],
                outcome_details=[
                    ProcessDecisionOutcome(id="O1", label="No", target_ref="T2"),
                    ProcessDecisionOutcome(
                        id="O2", label="Si", target_path_id="P_Fix"
                    ),
                ],
            )
        ],
        alternative_paths=[
            ProcessPath(
                id="P_Fix",
                label="Correzioni",
                trigger_or_condition="Si",
                sequence=["T_Fix"],
                rejoins_at="T2",
            )
        ],
        flow_edges=[
            ProcessFlowEdge(id="E1", source_id="T1", target_id="D1", label="controllato"),
            ProcessFlowEdge(
                id="E2", source_id="D1", target_id="T2", label="No", condition="No"
            ),
            ProcessFlowEdge(
                id="E3",
                source_id="D1",
                target_id="T_Fix",
                label="Si",
                condition="Si",
                path_id="P_Fix",
            ),
        ],
        unknowns=[],
    )

    model = build_bpmn_semantic_model(
        process_id="P", process_name="P", process=process
    )
    branch = next(n for n in model.flowNodes if n.name == "Correggi pratica")
    assert branch.loopCharacteristics == "multiInstanceSequential"
    assert (
        '<bpmn:multiInstanceLoopCharacteristics isSequential="true" />'
        in semantic_model_to_bpmn_xml(model)
    )


def test_plain_step_has_no_loop_marker():
    model = _model([ProcessStep(id="T1", label="Firma contratto"), ProcessStep(id="T2", label="Invia copia")])
    assert all(n.loopCharacteristics == "none" for n in model.flowNodes)
    xml = semantic_model_to_bpmn_xml(model)
    assert "<bpmn:standardLoopCharacteristics" not in xml
    assert "<bpmn:multiInstanceLoopCharacteristics" not in xml


def test_loop_marker_rejected_on_a_non_activity_node():
    with pytest.raises(ValueError, match="only valid on an activity"):
        BPMNFlowNode(id="g", type="exclusiveGateway", name="g", loopCharacteristics="standardLoop")


def test_unknown_step_multiplicity_is_rejected():
    with pytest.raises(ValidationError, match="multiplicity"):
        ProcessStep(id="T1", label="Lavora pratica", multiplicity="per_batch")


def test_single_step_loop_on_a_multi_instance_activity_warns_and_is_skipped():
    model = _model(
        [
            ProcessStep(id="T1", label="Prepara batch"),
            ProcessStep(id="T2", label="Elabora elemento", multiplicity="per_item"),
        ],
        loops=[ProcessLoop(id="L1", label="Ripeti elemento", repeated_steps=["T2"], condition="errore")],
    )
    node = next(n for n in model.flowNodes if n.name == "Elabora elemento")
    assert node.loopCharacteristics == "multiInstanceParallel"  # unchanged
    assert node.loopConditionExpression is None
    assert any("gia' un'attivita" in w or "multi-instance" in w for w in model.model_warnings)


def test_exit_only_loop_condition_warns_and_renders_bare_standard_loop():
    model = _model(
        [ProcessStep(id="T1", label="Apri"), ProcessStep(id="T2", label="Ritenta"), ProcessStep(id="T3", label="Chiudi")],
        loops=[ProcessLoop(id="L1", label="Ritenta", repeated_steps=["T2"], exit_condition="pratica chiusa")],
    )
    node = next(n for n in model.flowNodes if n.name == "Ritenta")
    assert node.loopCharacteristics == "standardLoop"
    assert node.loopConditionExpression is None
    assert "<bpmn:standardLoopCharacteristics />" in semantic_model_to_bpmn_xml(model)
    assert any("condizione di continuazione" in w for w in model.model_warnings)
