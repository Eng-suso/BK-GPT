"""Synthetic BPMN organisational mapping and strict structured resource requests."""
import pytest
from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.scenario_builder import describe_scenario_template, build_prosimos_scenario


def model(lanes="", pool=True):
    collaboration = '<collaboration id="C"><participant id="Pool" name="Company" processRef="P"/></collaboration>' if pool else ""
    return f'''<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">{collaboration}
    <process id="P"><laneSet id="LS">{lanes}</laneSet><startEvent id="S"/>
    <userTask id="A" name="Receive"/><task id="B" name="Approve"/><endEvent id="E"/>
    <sequenceFlow id="F1" sourceRef="S" targetRef="A"/>
    <sequenceFlow id="F2" sourceRef="A" targetRef="B"/>
    <sequenceFlow id="F3" sourceRef="B" targetRef="E"/>
    </process></definitions>'''


def template(xml):
    return describe_scenario_template(normalize_bpmn_for_prosimos(xml), source_bpmn_xml=xml)


def test_lanes_survive_normalisation_and_define_exact_membership():
    xml = model('<lane id="Front" name="Operations"><flowNodeRef>A</flowNodeRef></lane><lane id="Back" name="Finance"><flowNodeRef>B</flowNodeRef></lane>')
    resources = template(xml).resources
    assert [(r.name, r.kind, r.pool_name, r.task_ids) for r in resources] == [
        ("Operations", "lane", "Company", ["A"]), ("Finance", "lane", "Company", ["B"])]
    assert template(xml).resources == resources
    assert len({r.id for r in resources}) == 2


def test_pool_without_lanes_is_a_candidate_but_no_pool_is_not_an_operator():
    assert template(model()).resources[0].task_ids == ["A", "B"]
    assert template(model()).resources[0].kind == "pool"
    assert template(model(pool=False)).resources == []


def test_task_outside_lanes_remains_unassigned_and_nested_lane_wins():
    lane = '<lane id="Parent" name="Division"><flowNodeRef>A</flowNodeRef><childLaneSet id="Children"><lane id="Child" name="Team"><flowNodeRef>A</flowNodeRef></lane></childLaneSet></lane>'
    resources = template(model(lane)).resources
    assert len(resources) == 1
    assert resources[0].bpmn_id == "Child"
    assert resources[0].parent_name == "Division"
    assert resources[0].task_ids == ["A"]


def test_standalone_lane_does_not_require_a_participant():
    resources = template(model('<lane id="L" name="Team"><flowNodeRef>A</flowNodeRef></lane>', pool=False)).resources
    assert resources[0].pool_name is None
    assert resources[0].task_ids == ["A"]


@pytest.mark.parametrize("resources,tasks", [([], []),
    ([{"id": "r", "name": "Team", "amount": 1, "cost_per_hour": 0}], []),
    ([{"id": "r", "name": "Team", "amount": 1, "cost_per_hour": 0}], [{"element_id": "A", "resource_id": "missing", "mean_seconds": 60}]),
    ([{"id": "r", "name": "  ", "amount": 1, "cost_per_hour": 0}], []),
])
def test_explicit_resources_never_fall_back_to_an_operator(resources, tasks):
    with pytest.raises(ValueError):
        build_prosimos_scenario(bpmn_xml=normalize_bpmn_for_prosimos(model()), request=CreateSimulationRunRequest(resources=resources, tasks=tasks))
