"""SIM-11f: un'attivita' multi-istanza con un numero fisso si esegue quel numero di volte.

Prima si eseguiva una volta per caso (report: "approssimato, alto"). Con
``loopCardinality`` intero l'attivita' diventa copie in sequenza o in parallelo
nel BPMN del motore; il modello del run resta quello del consulente.
"""

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.compatibility import bpmn_compatibility_report
from backend.simulation.scenario_builder import build_prosimos_scenario, describe_scenario_template

_NS = 'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"'


def _bpmn(loop: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions {_NS} id="D"><bpmn:process id="P" isExecutable="false">
  <bpmn:startEvent id="S" /><bpmn:userTask id="SIGN" name="Firma un documento">{loop}</bpmn:userTask><bpmn:endEvent id="E" />
  <bpmn:sequenceFlow id="f1" sourceRef="S" targetRef="SIGN" /><bpmn:sequenceFlow id="f2" sourceRef="SIGN" targetRef="E" />
</bpmn:process></bpmn:definitions>"""


SEQUENTIAL = '<bpmn:multiInstanceLoopCharacteristics isSequential="true"><bpmn:loopCardinality>3</bpmn:loopCardinality></bpmn:multiInstanceLoopCharacteristics>'
PARALLEL = '<bpmn:multiInstanceLoopCharacteristics><bpmn:loopCardinality>3</bpmn:loopCardinality></bpmn:multiInstanceLoopCharacteristics>'


def _scenario(loop: str, **task):
    bpmn = normalize_bpmn_for_prosimos(_bpmn(loop))
    request = CreateSimulationRunRequest(total_cases=5, tasks=[{"element_id": "SIGN", "mean_seconds": 600, **task}])
    return build_prosimos_scenario(bpmn_xml=bpmn, request=request)


def test_sequential_instances_become_a_chain_of_the_same_activity():
    scenario = _scenario(SEQUENTIAL)

    [activity] = scenario.model["activities"]
    assert (activity["instances"], activity["sequential_instances"]) == (3, True)
    engine = scenario.bpmn_xml or ""
    assert engine.count('name="Firma un documento"') == 3
    assert 'sourceRef="SIGN" targetRef="SIGN__mi_2"' in engine and 'sourceRef="SIGN__mi_2" targetRef="SIGN__mi_3"' in engine
    assert 'sourceRef="SIGN__mi_3" targetRef="E"' in engine
    assert {t["task_id"] for t in scenario.payload["task_resource_distribution"]} == {"SIGN", "SIGN__mi_2", "SIGN__mi_3"}


def test_parallel_instances_split_and_join():
    scenario = _scenario(PARALLEL)

    engine = scenario.bpmn_xml or ""
    assert engine.count("parallelGateway") >= 2
    assert 'sourceRef="S" targetRef="SIGN__mi_split"' in engine and 'sourceRef="SIGN__mi_join" targetRef="E"' in engine
    assert scenario.model["activities"][0]["sequential_instances"] is False


@pytest.mark.parametrize("loop", [
    '<bpmn:multiInstanceLoopCharacteristics><bpmn:loopCardinality>${righe.size()}</bpmn:loopCardinality></bpmn:multiInstanceLoopCharacteristics>',
    '<bpmn:multiInstanceLoopCharacteristics><bpmn:loopCardinality>1</bpmn:loopCardinality></bpmn:multiInstanceLoopCharacteristics>',
    '<bpmn:multiInstanceLoopCharacteristics><bpmn:loopCardinality>3</bpmn:loopCardinality><bpmn:completionCondition>x</bpmn:completionCondition></bpmn:multiInstanceLoopCharacteristics>',
    "<bpmn:standardLoopCharacteristics />",
], ids=["espressione", "una sola", "condizione di fine", "ciclo"])
def test_other_loops_still_run_once_and_the_report_says_so(loop):
    scenario = _scenario(loop)
    report = {e.element_id: e for e in bpmn_compatibility_report(_bpmn(loop)).elements}["SIGN"]

    assert scenario.model["activities"][0]["instances"] == 1
    assert scenario.bpmn_xml is None
    assert (report.status, report.impact) == ("approximated", "high")


def test_the_report_says_how_many_times_the_activity_runs():
    report = {e.element_id: e for e in bpmn_compatibility_report(_bpmn(SEQUENTIAL)).elements}["SIGN"]

    assert (report.status, report.simulated_as) == ("preserved", "task × 3")
    assert "3 volte per caso" in report.note


def test_the_panel_sees_one_activity_not_three():
    template = describe_scenario_template(normalize_bpmn_for_prosimos(_bpmn(SEQUENTIAL)))

    assert [t.element_id for t in template.tasks] == ["SIGN"]


def test_an_activity_with_categories_skips_or_rework_runs_once():
    from backend.simulation.ir.instances import expandable
    from backend.simulation.ir.model import DurationByAttribute, DurationVariant, Fixed, SimulationModel, Skip

    model = SimulationModel.model_validate(_scenario(SEQUENTIAL).model)
    sign = model.activities[0]
    by_category = DurationByAttribute(attribute="tipo", variants=(DurationVariant(value="a", duration=Fixed(value=60)),))

    assert expandable(model) == [sign]
    for change in ({"duration_by": by_category}, {"skip": Skip(probability=0.5)}):
        assert expandable(model.model_copy(update={"activities": (sign.model_copy(update=change),)})) == []
