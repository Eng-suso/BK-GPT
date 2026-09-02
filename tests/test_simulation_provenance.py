"""Phase 5 — scenario provenance / input confidence.

`map_scenario_provenance` is the pure seam: scenario-template elements + an
(optional) BPMN review dict -> per-element structural provenance.
"""

from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.process_understanding import (
    ProcessActor,
    ProcessDecision,
    ProcessDecisionOutcome,
    ProcessStep,
    ProcessUnderstanding,
)
from backend.schemas.simulation import (
    ScenarioTemplateBranch,
    ScenarioTemplateGateway,
    ScenarioTemplateResponse,
    ScenarioTemplateTask,
)
from backend.simulation.provenance import map_scenario_provenance
from backend.simulation.scenario_builder import describe_scenario_template


def _understanding() -> ProcessUnderstanding:
    return ProcessUnderstanding(
        title="Gestione richieste",
        actors=[ProcessActor(id="Actor_Ops", label="Back office", kind="team")],
        steps=[
            ProcessStep(
                id="Task_Receive",
                label="Ricevi richiesta",
                actor_ids=["Actor_Ops"],
                source_evidence=["Le richieste arrivano via PEC al back office."],
            ),
            ProcessStep(
                id="Task_Review",
                label="Verifica documentazione",
                actor_ids=["Actor_Ops"],
                source_evidence=["Un operatore controlla che gli allegati siano completi."],
            ),
            ProcessStep(id="Task_Approve", label="Approva", actor_ids=["Actor_Ops"]),
        ],
        sequence=["Task_Receive", "Task_Review", "Task_Approve"],
        main_success_path=["Task_Receive", "Task_Review", "Task_Approve"],
        decisions=[
            ProcessDecision(
                id="Decision_Complete",
                label="Documentazione completa?",
                question="La documentazione e completa?",
                outcomes=["Si", "No"],
                outcome_details=[
                    ProcessDecisionOutcome(
                        id="Outcome_Complete_Yes",
                        label="Si",
                        condition="Allegati completi",
                        target_ref="Task_Approve",
                        certainty="explicit",
                    ),
                    ProcessDecisionOutcome(
                        id="Outcome_Complete_No",
                        label="No",
                        condition="Allegati mancanti",
                        target_ref="Task_Review",
                        certainty="assumption",
                    ),
                ],
                source_evidence=["Se manca un documento la pratica torna in verifica."],
            )
        ],
    )


def _review(process: ProcessUnderstanding) -> dict:
    model = build_bpmn_semantic_model(
        process_id="Process_Requests",
        process_name="Gestione richieste",
        process=process,
    )
    return {
        "bpmn_semantic_model": model.model_dump(mode="json"),
        "process_understanding": model.sourceProcessUnderstanding,
        "readiness_score": 7,
        "missing_information": ["Volumi mensili non quantificati"],
    }, model


def test_no_review_marks_every_element_ai_inferred():
    template = ScenarioTemplateResponse(
        tasks=[ScenarioTemplateTask(element_id="Task_A", name="Fai qualcosa", type="task")],
        gateways=[
            ScenarioTemplateGateway(
                element_id="Gw_1",
                name="Bivio",
                type="exclusiveGateway",
                branches=[
                    ScenarioTemplateBranch(flow_id="f1", flow_name="", target_name="A"),
                    ScenarioTemplateBranch(flow_id="f2", flow_name="", target_name="B"),
                ],
            )
        ],
    )

    result = map_scenario_provenance(template, None)

    assert result.has_discovery is False
    assert {e.origin for e in result.elements} == {"ai_inferred"}
    assert {e.confidence for e in result.elements} == {"low"}
    gateway = next(e for e in result.elements if e.kind == "gateway")
    assert gateway.open_questions == 2


def test_discovered_activity_resolves_to_interview_with_evidence():
    process = _understanding()
    review, model = _review(process)
    template = describe_scenario_template(semantic_model_to_bpmn_xml(model))

    result = map_scenario_provenance(template, review)

    assert result.has_discovery is True
    assert result.readiness_score == 70
    assert result.missing_information == ["Volumi mensili non quantificati"]

    review_step = next(e for e in result.elements if e.name == "Verifica documentazione")
    assert review_step.origin == "interview"
    assert review_step.confidence == "high"
    assert review_step.evidence
    assert review_step.hint_ref is not None
    assert review_step.hint_ref.field == "steps"

    approve = next(e for e in result.elements if e.name == "Approva")
    assert approve.origin == "interview"
    # no source_evidence on that step -> medium, not high
    assert approve.confidence == "medium"


def _gateway_template() -> ScenarioTemplateResponse:
    return ScenarioTemplateResponse(
        tasks=[],
        gateways=[
            ScenarioTemplateGateway(
                element_id="Decision_Complete",
                name="Documentazione completa?",
                type="exclusiveGateway",
                branches=[
                    ScenarioTemplateBranch(flow_id="f1", flow_name="Si", target_name="Approva"),
                    ScenarioTemplateBranch(flow_id="f2", flow_name="No", target_name="Verifica"),
                ],
            )
        ],
    )


def _review_with_gateway(certainties: list[str]) -> dict:
    return {
        "bpmn_semantic_model": {
            "flowNodes": [
                {
                    "id": "Decision_Complete",
                    "type": "exclusiveGateway",
                    "name": "Documentazione completa?",
                    "sourceRefs": ["decisions:Decision_Complete"],
                }
            ],
        },
        "process_understanding": {
            "decisions": [
                {
                    "id": "Decision_Complete",
                    "label": "Documentazione completa?",
                    "outcome_details": [
                        {"id": f"o{i}", "label": str(i), "certainty": c}
                        for i, c in enumerate(certainties)
                    ],
                    "source_evidence": ["Se manca un documento la pratica torna in verifica."],
                }
            ]
        },
        "readiness_score": 6,
    }


def test_gateway_confidence_follows_outcome_certainty():
    result = map_scenario_provenance(
        _gateway_template(), _review_with_gateway(["explicit", "assumption"])
    )

    gateway = next(e for e in result.elements if e.kind == "gateway")
    assert gateway.origin == "interview"
    # one outcome is an assumption -> low, and it is flagged for validation
    assert gateway.confidence == "low"
    assert gateway.open_questions == 1
    assert gateway.hint_ref is not None and gateway.hint_ref.field == "decisions"


def test_all_explicit_outcomes_give_high_gateway_confidence():
    result = map_scenario_provenance(
        _gateway_template(), _review_with_gateway(["explicit", "explicit"])
    )

    gateway = next(e for e in result.elements if e.kind == "gateway")
    assert gateway.confidence == "high"
    assert gateway.open_questions == 0


def test_inferred_outcome_gives_medium_gateway_confidence():
    result = map_scenario_provenance(
        _gateway_template(), _review_with_gateway(["explicit", "inferred"])
    )

    gateway = next(e for e in result.elements if e.kind == "gateway")
    assert gateway.confidence == "medium"
    assert gateway.open_questions == 1


def test_element_ids_line_up_between_template_and_semantic_model():
    process = _understanding()
    review, model = _review(process)
    template = describe_scenario_template(semantic_model_to_bpmn_xml(model))

    node_ids = {node["id"] for node in review["bpmn_semantic_model"]["flowNodes"]}
    matched = [
        e
        for e in map_scenario_provenance(template, review).elements
        if e.element_id in node_ids and e.origin == "interview"
    ]
    # every discovered task + the decision gateway resolved by id, not name
    assert len(matched) >= 3
