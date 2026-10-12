"""Every BPMN 2.0 activity the plan can name (OMG BPMN 2.0, 10.3 and 10.6).

Call activity, transaction with its cancel boundary, ad-hoc sub-process, event
sub-process and compensation, on a travel booking.
"""

from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.bpmn.soundness import analyze_control_flow
from backend.bpmn.validation import validate_bpmn_semantic_model
from backend.process_understanding import (
    ProcessActor,
    ProcessBoundaries,
    ProcessExceptionPath,
    ProcessStep,
    ProcessUnderstanding,
)


def _booking(**overrides) -> ProcessUnderstanding:
    base = dict(
        title="Prenotazione viaggio",
        actors=[ProcessActor(id="agenzia", label="Agenzia", kind="team")],
        boundaries=ProcessBoundaries(start_event="Richiesta ricevuta", success_end="Viaggio confermato"),
        steps=[
            ProcessStep(id="prenota", label="Prenota volo e hotel", type="transaction", actor_ids=["agenzia"]),
            ProcessStep(id="paga", label="Incassa il pagamento", type="call_activity",
                        called_process="Processo incassi", actor_ids=["agenzia"]),
            ProcessStep(id="documenti", label="Raccogli i documenti", type="ad_hoc_subprocess", actor_ids=["agenzia"]),
            ProcessStep(id="conferma", label="Invia la conferma", type="send_task", actor_ids=["agenzia"]),
            ProcessStep(id="storno", label="Storna il pagamento", type="service_task",
                        compensates_step_id="paga", actor_ids=["agenzia"]),
            ProcessStep(id="reclamo", label="Gestisci il reclamo", type="event_subprocess",
                        event_trigger="message", interrupting=False, actor_ids=["agenzia"]),
        ],
        main_success_path=["prenota", "paga", "documenti", "conferma"],
        exceptions=[
            ProcessExceptionPath(id="annullo", label="Prenotazione annullata", kind="cancel",
                                 attached_to_step_id="prenota", handling="Avvisa il cliente"),
        ],
    )
    base.update(overrides)
    return ProcessUnderstanding(**base)


def _compile(process: ProcessUnderstanding):
    return build_bpmn_semantic_model(process_id="Viaggio", process_name=process.title, process=process)


def _node(model, name: str):
    return next(node for node in model.flowNodes if node.name == name)


def test_each_activity_takes_the_bpmn_type_the_plan_names():
    model = _compile(_booking())

    assert _node(model, "Prenota volo e hotel").type == "transaction"
    call = _node(model, "Incassa il pagamento")
    assert (call.type, call.calledElement) == ("callActivity", "Processo incassi")
    assert _node(model, "Raccogli i documenti").type == "adHocSubProcess"
    xml = semantic_model_to_bpmn_xml(model, include_di=False)
    assert '<bpmn:callActivity id="paga" name="Incassa il pagamento" calledElement="Processo incassi">' in xml
    assert "<bpmn:transaction " in xml and "<bpmn:adHocSubProcess " in xml


def test_an_event_sub_process_runs_on_its_trigger_outside_the_flow():
    model = _compile(_booking())

    sub = _node(model, "Gestisci il reclamo")
    assert sub.triggeredByEvent and sub.type == "subProcess"
    assert (sub.eventSubProcessStart.eventDefinition, sub.eventSubProcessStart.isInterrupting) == ("message", False)
    assert not [flow for flow in model.sequenceFlows if sub.id in {flow.sourceRef, flow.targetRef}]
    xml = semantic_model_to_bpmn_xml(model, include_di=False)
    assert 'triggeredByEvent="true"' in xml and 'isInterrupting="false"' in xml


def test_a_compensation_activity_is_reached_by_association_from_the_step_it_undoes():
    model = _compile(_booking())

    refund = _node(model, "Storna il pagamento")
    payment = _node(model, "Incassa il pagamento")
    boundary = next(node for node in model.flowNodes if node.eventDefinition == "compensation")
    assert refund.isForCompensation and boundary.attachedToRef == payment.id
    assert any(a.sourceRef == boundary.id and a.targetRef == refund.id and a.direction == "one" for a in model.associations)
    assert not [flow for flow in model.sequenceFlows if refund.id in {flow.sourceRef, flow.targetRef}]


def test_a_cancel_boundary_sits_only_on_a_transaction():
    on_transaction = _compile(_booking())
    elsewhere = _compile(_booking(exceptions=[
        ProcessExceptionPath(id="annullo", label="Pagamento annullato", kind="cancel",
                             attached_to_step_id="paga", handling="Avvisa il cliente"),
    ]))

    cancel = next(node for node in on_transaction.flowNodes if node.eventDefinition == "cancel")
    assert _node(on_transaction, "Prenota volo e hotel").id == cancel.attachedToRef
    assert not any(node.eventDefinition == "cancel" for node in elsewhere.flowNodes)
    assert any("annullamento vale solo su una transazione" in warning for warning in elsewhere.model_warnings)


def test_the_booking_is_sound_and_laid_out():
    model = _compile(_booking())

    structural = [issue for issue in validate_bpmn_semantic_model(model) if not issue.startswith("Soundness:")]
    assert structural == []
    assert not analyze_control_flow(model).errors
    xml = semantic_model_to_bpmn_xml(model)
    for element_id in ("prenota", "paga", "documenti", "storno", "reclamo"):
        assert f'bpmnElement="{element_id}"' in xml
