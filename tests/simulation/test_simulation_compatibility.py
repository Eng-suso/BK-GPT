"""SIM-05: il report di compatibilita' dichiara tutto cio' che il normalizer cambia."""

import pytest

from backend.simulation.compatibility import bpmn_compatibility_report

_NS = 'xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"'

# Un processo con tutto cio' che il motore non sa eseguire.
RICH_BPMN = f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions {_NS}>
  <bpmn:process id="P" isExecutable="false">
    <bpmn:laneSet id="LS">
      <bpmn:lane id="Lane_Ops" name="Operatori"><bpmn:flowNodeRef>T_user</bpmn:flowNodeRef></bpmn:lane>
    </bpmn:laneSet>
    <bpmn:startEvent id="S1" name="Richiesta web" />
    <bpmn:startEvent id="S2" name="Richiesta email" />
    <bpmn:userTask id="T_user" name="Controlla" />
    <bpmn:task id="T_loop" name="Verifica righe">
      <bpmn:multiInstanceLoopCharacteristics />
    </bpmn:task>
    <bpmn:boundaryEvent id="B_timer" attachedToRef="T_user"><bpmn:timerEventDefinition /></bpmn:boundaryEvent>
    <bpmn:boundaryEvent id="B_deco" attachedToRef="T_loop" />
    <bpmn:task id="T_escalate" name="Sollecita" />
    <bpmn:intermediateCatchEvent id="IC_timer" name="Attendi 2 giorni"><bpmn:timerEventDefinition /></bpmn:intermediateCatchEvent>
    <bpmn:intermediateThrowEvent id="IT_none" />
    <bpmn:complexGateway id="G_complex" />
    <bpmn:subProcess id="SP" name="Approvazione">
      <bpmn:startEvent id="SP_s" />
      <bpmn:task id="SP_t" name="Approva" />
      <bpmn:endEvent id="SP_e" />
      <bpmn:sequenceFlow id="SP_f1" sourceRef="SP_s" targetRef="SP_t" />
      <bpmn:sequenceFlow id="SP_f2" sourceRef="SP_t" targetRef="SP_e" />
    </bpmn:subProcess>
    <bpmn:task id="T_a" name="Archivia" />
    <bpmn:task id="T_b" name="Notifica" />
    <bpmn:endEvent id="E1" />
    <bpmn:endEvent id="E2" />
    <bpmn:endEvent id="E_escalated" />
    <bpmn:textAnnotation id="Note_1"><bpmn:text>nota</bpmn:text></bpmn:textAnnotation>
    <bpmn:sequenceFlow id="f1" sourceRef="S1" targetRef="T_user" />
    <bpmn:sequenceFlow id="f2" sourceRef="S2" targetRef="T_user" />
    <bpmn:sequenceFlow id="f3" sourceRef="T_user" targetRef="T_loop" />
    <bpmn:sequenceFlow id="f4" sourceRef="T_loop" targetRef="IC_timer" />
    <bpmn:sequenceFlow id="f5" sourceRef="IC_timer" targetRef="IT_none" />
    <bpmn:sequenceFlow id="f6" sourceRef="IT_none" targetRef="SP" />
    <bpmn:sequenceFlow id="f7" sourceRef="SP" targetRef="G_complex" />
    <bpmn:sequenceFlow id="f8" sourceRef="G_complex" targetRef="T_a" />
    <bpmn:sequenceFlow id="f9" sourceRef="G_complex" targetRef="T_b" />
    <bpmn:sequenceFlow id="f10" sourceRef="T_a" targetRef="E1" />
    <bpmn:sequenceFlow id="f11" sourceRef="T_b" targetRef="E2" />
    <bpmn:sequenceFlow id="fx1" sourceRef="B_timer" targetRef="T_escalate" />
    <bpmn:sequenceFlow id="fx2" sourceRef="T_escalate" targetRef="E_escalated" />
  </bpmn:process>
</bpmn:definitions>
"""

SIMPLE_BPMN = f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions {_NS}>
  <bpmn:process id="P" isExecutable="false">
    <bpmn:startEvent id="S" />
    <bpmn:task id="T" name="Ricevi" />
    <bpmn:exclusiveGateway id="G" />
    <bpmn:task id="A" name="Approva" />
    <bpmn:task id="R" name="Rifiuta" />
    <bpmn:exclusiveGateway id="J" />
    <bpmn:endEvent id="E" />
    <bpmn:sequenceFlow id="f1" sourceRef="S" targetRef="T" />
    <bpmn:sequenceFlow id="f2" sourceRef="T" targetRef="G" />
    <bpmn:sequenceFlow id="f3" sourceRef="G" targetRef="A" />
    <bpmn:sequenceFlow id="f4" sourceRef="G" targetRef="R" />
    <bpmn:sequenceFlow id="f5" sourceRef="A" targetRef="J" />
    <bpmn:sequenceFlow id="f6" sourceRef="R" targetRef="J" />
    <bpmn:sequenceFlow id="f7" sourceRef="J" targetRef="E" />
  </bpmn:process>
</bpmn:definitions>
"""


@pytest.fixture(scope="module")
def rich():
    report = bpmn_compatibility_report(RICH_BPMN)
    return report, {entry.element_id: entry for entry in report.elements}


def test_nothing_the_normalizer_changes_goes_undeclared(rich):
    report, _ = rich
    assert report.undeclared == 0


def test_every_element_of_the_bpmn_has_an_entry(rich):
    _, by_id = rich
    expected = {
        "LS", "Lane_Ops", "S1", "S2", "T_user", "T_loop", "B_timer", "B_deco", "T_escalate",
        "E_escalated", "IC_timer", "IT_none", "G_complex", "SP", "SP_s", "SP_t", "SP_e", "SP_f1",
        "SP_f2", "T_a", "T_b", "E1", "E2", "Note_1",
    } | {f"f{i}" for i in range(1, 12)} | {"fx1", "fx2"}
    assert set(by_id) == expected


@pytest.mark.parametrize(
    ("element_id", "status", "impact"),
    [
        ("SP", "flattened", "high"),
        ("SP_t", "flattened", "none"),
        ("SP_f1", "flattened", "none"),
        ("T_loop", "approximated", "high"),
        ("G_complex", "approximated", "medium"),
        ("B_timer", "removed", "high"),
        ("B_deco", "removed", "low"),
        ("T_escalate", "removed", "high"),
        ("E_escalated", "removed", "high"),
        ("fx1", "removed", "none"),
        ("IC_timer", "removed", "high"),
        ("IT_none", "removed", "none"),
        ("S2", "approximated", "low"),
        ("E2", "approximated", "none"),
        ("Note_1", "removed", "none"),
        ("LS", "removed", "none"),
        ("Lane_Ops", "removed", "none"),
        ("T_user", "preserved", "none"),
        ("T_a", "preserved", "none"),
        ("f1", "preserved", "none"),
    ],
)
def test_each_change_has_its_status_and_kpi_impact(rich, element_id, status, impact):
    _, by_id = rich
    entry = by_id[element_id]
    assert (entry.status, entry.impact) == (status, impact), entry.note


def test_flattened_steps_point_to_their_subprocess(rich):
    _, by_id = rich
    assert {by_id[i].parent_id for i in ("SP_s", "SP_t", "SP_e", "SP_f1", "SP_f2")} == {"SP"}


def test_merged_events_name_the_survivor(rich):
    _, by_id = rich
    assert by_id["S2"].simulated_as == "S1"
    assert by_id["E2"].simulated_as == "E1"


def test_a_spliced_event_reconnects_its_flow_and_says_so(rich):
    _, by_id = rich
    # f4 entrava nel timer: ora entra direttamente nel sottoprocesso.
    assert by_id["f4"].status == "approximated"
    assert by_id["f4"].simulated_as == "T_loop → SP"


def test_a_downcast_activity_is_preserved_but_explains_the_new_type(rich):
    _, by_id = rich
    entry = by_id["T_user"]
    assert entry.simulated_as == "task"
    assert "userTask" in entry.note


def test_counts_and_kpi_affecting_add_up(rich):
    report, by_id = rich
    assert sum(report.counts.values()) == len(by_id)
    assert report.kpi_affecting == sum(
        1 for e in report.elements if e.status != "preserved" and e.impact != "none"
    )
    assert report.kpi_affecting > 0


def test_a_bpmn_the_engine_runs_as_is_is_all_preserved():
    report = bpmn_compatibility_report(SIMPLE_BPMN)
    assert report.counts["preserved"] == len(report.elements) == 14
    assert report.kpi_affecting == 0
    assert report.undeclared == 0


def test_invalid_xml_is_refused():
    with pytest.raises(ValueError, match="XML BPMN non valido"):
        bpmn_compatibility_report("<bpmn:definitions")


def test_entities_are_refused_before_parsing():
    evil = '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x "boom">]><d>&x;</d>'
    with pytest.raises(ValueError):
        bpmn_compatibility_report(evil)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


def _bpmn_model_id(client) -> str:
    client_id = client.post("/v1/workspace/clients", json={"name": "SIM-05 Client"}).json()["id"]
    project_id = client.post(
        "/v1/workspace/projects", json={"client_id": client_id, "name": "SIM-05 Project"}
    ).json()["id"]
    process = client.post(f"/v1/workspace/projects/{project_id}/processes", json={"name": "SIM-05 Process"})
    assert process.status_code == 200
    return process.json()["bpmn_model_id"]


def _url(bpmn_model_id: str) -> str:
    return f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-compatibility"


def test_the_api_reports_the_bpmn_being_edited(client):
    response = client.post(_url(_bpmn_model_id(client)), json={"current_bpmn_xml": RICH_BPMN})

    assert response.status_code == 200
    body = response.json()
    assert body["undeclared"] == 0
    by_id = {entry["element_id"]: entry for entry in body["elements"]}
    assert by_id["SP"]["status"] == "flattened"
    assert by_id["B_timer"]["impact"] == "high"
    assert body["counts"]["removed"] > 0


def test_the_api_without_a_bpmn_says_what_to_do(client):
    response = client.post(_url(_bpmn_model_id(client)), json={})

    assert response.status_code == 400
    assert "BPMN" in response.json()["error"]["message"]


def test_the_api_on_an_unknown_model_is_404(client):
    response = client.post(_url("non-esiste"), json={"current_bpmn_xml": SIMPLE_BPMN})

    assert response.status_code == 404
