"""Activity loop markers: multi-instance and standard loop."""

from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.process_understanding import (
    ProcessLoop,
    ProcessStep,
    ProcessUnderstanding,
)


def _model(steps, **kw):
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


def test_plain_step_has_no_loop_marker():
    model = _model([ProcessStep(id="T1", label="Firma contratto"), ProcessStep(id="T2", label="Invia copia")])
    assert all(n.loopCharacteristics == "none" for n in model.flowNodes)
    assert "LoopCharacteristics" not in semantic_model_to_bpmn_xml(model)


def test_loop_marker_rejected_on_a_non_activity_node():
    import pytest
    from backend.bpmn.models import BPMNFlowNode

    with pytest.raises(ValueError, match="only valid on an activity"):
        BPMNFlowNode(id="g", type="exclusiveGateway", name="g", loopCharacteristics="standardLoop")
