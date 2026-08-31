"""Phase 1 — Prosimos event-log pipeline: log_processor + storage + endpoint.

The recorded Prosimos contract lives in ``tests/fixtures/prosimos/`` (captured by
the Phase 1 integration spike against the real prosimos-api container).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.flow_graph import build_flow_graph
from backend.simulation.log_processor import (
    ProsimosLogError,
    activity_name_to_element_id,
    parse_prosimos_log,
    process_prosimos_log,
)
from backend.simulation.models import ProsimosSimulationResult
from backend.simulation.scenario_builder import build_prosimos_scenario

FIXTURES = Path(__file__).parent / "fixtures" / "prosimos"

MINIMAL_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="Process_1" isExecutable="false">
    <bpmn:startEvent id="StartEvent_1" />
    <bpmn:task id="Task_A" name="Ricevi richiesta" />
    <bpmn:task id="Task_R" name="Revisione" />
    <bpmn:exclusiveGateway id="Gateway_1" name="Esito" />
    <bpmn:task id="Task_B" name="Approva" />
    <bpmn:task id="Task_C" name="Rifiuta" />
    <bpmn:endEvent id="EndEvent_1" />
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Task_A" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_A" targetRef="Task_R" />
    <bpmn:sequenceFlow id="Flow_3" sourceRef="Task_R" targetRef="Gateway_1" />
    <bpmn:sequenceFlow id="Flow_4" sourceRef="Gateway_1" targetRef="Task_B" />
    <bpmn:sequenceFlow id="Flow_5" sourceRef="Gateway_1" targetRef="Task_C" />
    <bpmn:sequenceFlow id="Flow_6" sourceRef="Task_B" targetRef="EndEvent_1" />
    <bpmn:sequenceFlow id="Flow_7" sourceRef="Task_C" targetRef="EndEvent_1" />
  </bpmn:process>
</bpmn:definitions>
"""

ONE_ACTIVITY_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="P" isExecutable="false">
    <bpmn:startEvent id="S" />
    <bpmn:task id="Task_A" name="Ricevi richiesta" />
    <bpmn:endEvent id="E" />
    <bpmn:sequenceFlow id="f1" sourceRef="S" targetRef="Task_A" />
    <bpmn:sequenceFlow id="f2" sourceRef="Task_A" targetRef="E" />
  </bpmn:process>
</bpmn:definitions>
"""

# 4 cases, one activity, no waiting -> cycle times 100 / 200 / 300 / 400 s.
CRAFTED_LOG = (
    "case_id,activity,enable_time,start_time,end_time,resource\n"
    "0,Ricevi richiesta,2026-01-05 09:00:00.000000+00:00,2026-01-05 09:00:00.000000+00:00,2026-01-05 09:01:40.000000+00:00,Op_0\n"
    "1,Ricevi richiesta,2026-01-05 09:00:00.000000+00:00,2026-01-05 09:00:00.000000+00:00,2026-01-05 09:03:20.000000+00:00,Op_0\n"
    "2,Ricevi richiesta,2026-01-05 09:00:00.000000+00:00,2026-01-05 09:00:00.000000+00:00,2026-01-05 09:05:00.000000+00:00,Op_0\n"
    "3,Ricevi richiesta,2026-01-05 09:00:00.000000+00:00,2026-01-05 09:00:00.000000+00:00,2026-01-05 09:06:40.000000+00:00,Op_0\n"
)


def _scenario_payload():
    return build_prosimos_scenario(
        bpmn_xml=normalize_bpmn_for_prosimos(MINIMAL_BPMN),
        request=CreateSimulationRunRequest(
            total_cases=40,
            default_cost_per_hour=40,
            resource_amount=2,
            resource_name="Operatore",
        ),
    ).payload


def _fixture_log() -> str:
    return (FIXTURES / "sim_log_sample.csv").read_text(encoding="utf-8")


def _fixture_stats() -> dict:
    return json.loads((FIXTURES / "simulate_response.json").read_text(encoding="utf-8"))


def _group_by_case(events):
    out = defaultdict(list)
    for ev in events:
        out[ev.case_id].append(ev)
    return out


@pytest.fixture()
def client():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------- #
# parsing / recorded contract
# --------------------------------------------------------------------------- #

def test_parse_prosimos_log_rejects_unexpected_header():
    with pytest.raises(ProsimosLogError):
        parse_prosimos_log("case,activity,ts\n1,A,2026-01-05 09:00:00+00:00\n")


def test_spike_fixture_matches_the_recorded_prosimos_contract():
    log = _fixture_log()
    assert log.splitlines()[0] == "case_id,activity,enable_time,start_time,end_time,resource"

    response = _fixture_stats()
    assert response["LogsFilename"].startswith("logs_")
    assert {
        "ResourceUtilization",
        "IndividualTaskStatistics",
        "OverallScenarioStatistics",
    } <= set(response)


# --------------------------------------------------------------------------- #
# summary — full-log KPIs, never from the sample
# --------------------------------------------------------------------------- #

def test_summary_percentiles_come_from_the_full_log():
    summary, _ = process_prosimos_log(
        CRAFTED_LOG,
        normalized_bpmn_xml=ONE_ACTIVITY_BPMN,
        scenario_payload={
            "resource_profiles": [
                {"resource_list": [{"name": "Op", "amount": 1, "cost_per_hour": "0"}]}
            ]
        },
        prosimos_stats={},
        name_to_element_id=activity_name_to_element_id(ONE_ACTIVITY_BPMN),
    )
    assert summary["casesCompleted"] == 4
    assert summary["cycle"]["avg"] == pytest.approx(250.0)
    assert summary["cycle"]["p50"] == pytest.approx(250.0)
    assert summary["cycle"]["p90"] == pytest.approx(370.0)
    assert summary["cycle"]["p95"] == pytest.approx(385.0)


def test_summary_is_independent_of_the_display_sample_size():
    log, stats = _fixture_log(), _fixture_stats()
    bpmn = normalize_bpmn_for_prosimos(MINIMAL_BPMN)
    common = dict(
        normalized_bpmn_xml=bpmn,
        scenario_payload=_scenario_payload(),
        prosimos_stats=stats,
        name_to_element_id=activity_name_to_element_id(bpmn),
    )
    full, _ = process_prosimos_log(log, max_cases=500, buckets=120, **common)
    tiny, _ = process_prosimos_log(log, max_cases=5, buckets=40, **common)
    assert full["cycle"] == tiny["cycle"]
    assert full["waiting"] == tiny["waiting"]
    assert full["byActivity"] == tiny["byActivity"]
    assert full["bottleneck"] == tiny["bottleneck"]


def test_summary_cross_checks_prosimos_own_cycle_time():
    log, stats = _fixture_log(), _fixture_stats()
    bpmn = normalize_bpmn_for_prosimos(MINIMAL_BPMN)
    summary, _ = process_prosimos_log(
        log,
        normalized_bpmn_xml=bpmn,
        scenario_payload=_scenario_payload(),
        prosimos_stats=stats,
        name_to_element_id=activity_name_to_element_id(bpmn),
    )
    px = summary["prosimosCrossCheck"]["idleCycleAvg"]
    assert summary["cycle"]["avg"] == pytest.approx(px, rel=0.01)
    assert summary["cycle"]["avg"] == pytest.approx(
        summary["waiting"]["avg"] + summary["processing"]["avg"], rel=1e-6
    )


def test_diagnostic_bottleneck_carries_its_factor_breakdown():
    log, stats = _fixture_log(), _fixture_stats()
    bpmn = normalize_bpmn_for_prosimos(MINIMAL_BPMN)
    summary, _ = process_prosimos_log(
        log,
        normalized_bpmn_xml=bpmn,
        scenario_payload=_scenario_payload(),
        prosimos_stats=stats,
        name_to_element_id=activity_name_to_element_id(bpmn),
    )
    bottleneck = summary["bottleneck"]
    assert bottleneck is not None
    assert set(bottleneck["factors"]) == {
        "waitingContribution",
        "utilization",
        "queueGrowth",
        "casesAffected",
        "cycleContribution",
        "persistence",
    }
    assert bottleneck["el"] in {row["el"] for row in summary["byActivity"]}


# --------------------------------------------------------------------------- #
# replay — display representation
# --------------------------------------------------------------------------- #

def test_replay_series_reaches_the_finished_run_at_the_last_point():
    log, stats = _fixture_log(), _fixture_stats()
    bpmn = normalize_bpmn_for_prosimos(MINIMAL_BPMN)
    summary, replay = process_prosimos_log(
        log,
        normalized_bpmn_xml=bpmn,
        scenario_payload=_scenario_payload(),
        prosimos_stats=stats,
        name_to_element_id=activity_name_to_element_id(bpmn),
    )
    g = replay["series"]["global"]
    assert replay["schemaVersion"] == 1
    assert replay["meta"]["totalCases"] == 60
    assert len(replay["series"]["t"]) == 121
    assert g["done"][-1] == 60
    assert g["wip"][-1] == 0
    assert g["costAccrued"][-1] == pytest.approx(summary["cost"]["total"], rel=0.02)
    assert g["avgCycleSec"][-1] == pytest.approx(summary["cycle"]["avg"], rel=1e-3)


def test_downsample_is_deterministic_and_keeps_the_extremes():
    log = _fixture_log()
    bpmn = normalize_bpmn_for_prosimos(MINIMAL_BPMN)
    common = dict(
        normalized_bpmn_xml=bpmn,
        scenario_payload=_scenario_payload(),
        prosimos_stats={},
        name_to_element_id=activity_name_to_element_id(bpmn),
        max_cases=12,
    )
    _, first = process_prosimos_log(log, **common)
    _, second = process_prosimos_log(log, **common)
    assert [c["id"] for c in first["cases"]] == [c["id"] for c in second["cases"]]

    sampled_cycles = sorted(c["cycleSec"] for c in first["cases"])
    all_cycles = [
        max(e.end for e in evs) - min(e.enable for e in evs)
        for evs in _group_by_case(parse_prosimos_log(log)).values()
    ]
    assert min(sampled_cycles) == pytest.approx(min(all_cycles), abs=0.01)
    assert max(sampled_cycles) == pytest.approx(max(all_cycles), abs=0.01)


# --------------------------------------------------------------------------- #
# flow-volume attribution
# --------------------------------------------------------------------------- #

def test_flow_attribution_only_when_the_bpmn_path_is_unique():
    graph = build_flow_graph(normalize_bpmn_for_prosimos(MINIMAL_BPMN))
    # Task_R -> Gateway_1 -> Task_B : a single activity-free path
    path = graph.unique_flow_path("Task_R", "Task_B")
    assert path is not None and len(path) == 2

    parallel = build_flow_graph(
        """<?xml version="1.0"?>
        <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
          <bpmn:process id="P">
            <bpmn:task id="A" name="A"/>
            <bpmn:parallelGateway id="split"/>
            <bpmn:parallelGateway id="join"/>
            <bpmn:task id="B" name="B"/>
            <bpmn:sequenceFlow id="s1" sourceRef="A" targetRef="split"/>
            <bpmn:sequenceFlow id="s2" sourceRef="split" targetRef="join"/>
            <bpmn:sequenceFlow id="s3" sourceRef="split" targetRef="join"/>
            <bpmn:sequenceFlow id="s4" sourceRef="join" targetRef="B"/>
          </bpmn:process>
        </bpmn:definitions>"""
    )
    assert parallel.unique_flow_path("A", "B") is None


def test_replay_flow_volumes_are_marked_attributed():
    log, stats = _fixture_log(), _fixture_stats()
    bpmn = normalize_bpmn_for_prosimos(MINIMAL_BPMN)
    _, replay = process_prosimos_log(
        log,
        normalized_bpmn_xml=bpmn,
        scenario_payload=_scenario_payload(),
        prosimos_stats=stats,
        name_to_element_id=activity_name_to_element_id(bpmn),
    )
    assert replay["flows"], "the linear fixture model should resolve every transition"
    assert all(entry["attributed"] for entry in replay["flows"].values())


# --------------------------------------------------------------------------- #
# storage + endpoint
# --------------------------------------------------------------------------- #

def test_run_completes_without_an_artifact_when_the_log_is_missing(client, monkeypatch):
    async def fake_run(request):
        return ProsimosSimulationResult(
            payload={"statsFile": "s.csv", "logFile": "l.csv"}, event_log_csv=None
        )

    monkeypatch.setattr("backend.simulation.service.run_prosimos_simulation", fake_run)

    cl = client.post("/v1/workspace/clients", json={"name": "NoLog"}).json()
    pr = client.post(
        "/v1/workspace/projects", json={"client_id": cl["id"], "name": "NoLog P"}
    ).json()
    ps = client.post(
        f"/v1/workspace/projects/{pr['id']}/processes", json={"name": "NoLog Proc"}
    ).json()
    mid = ps["bpmn_model_id"]

    run = client.post(
        f"/v1/workspace/bpmn-models/{mid}/simulation-runs",
        json={"total_cases": 5, "current_bpmn_xml": MINIMAL_BPMN},
    ).json()
    finished = client.get(f"/v1/workspace/simulation-runs/{run['id']}").json()
    assert finished["status"] == "completed"
    assert finished["summary"] is None
    assert "replay" not in finished
    assert client.get(f"/v1/workspace/simulation-runs/{run['id']}/replay").status_code == 404


def test_completed_run_stores_summary_on_the_row_and_replay_behind_its_own_endpoint(
    client, monkeypatch
):
    log, stats = _fixture_log(), _fixture_stats()

    async def fake_run(request):
        return ProsimosSimulationResult(payload=dict(stats), event_log_csv=log)

    monkeypatch.setattr("backend.simulation.service.run_prosimos_simulation", fake_run)

    cl = client.post("/v1/workspace/clients", json={"name": "Art"}).json()
    pr = client.post(
        "/v1/workspace/projects", json={"client_id": cl["id"], "name": "Art P"}
    ).json()
    ps = client.post(
        f"/v1/workspace/projects/{pr['id']}/processes", json={"name": "Art Proc"}
    ).json()
    mid = ps["bpmn_model_id"]

    run = client.post(
        f"/v1/workspace/bpmn-models/{mid}/simulation-runs",
        json={"total_cases": 60, "current_bpmn_xml": MINIMAL_BPMN},
    ).json()
    rid = run["id"]

    detail = client.get(f"/v1/workspace/simulation-runs/{rid}").json()
    assert detail["summary"]["casesCompleted"] == 60
    assert "replay" not in detail

    listed = client.get(f"/v1/workspace/bpmn-models/{mid}/simulation-runs").json()
    assert listed[0]["summary"] is not None
    assert "replay" not in listed[0]

    replay = client.get(f"/v1/workspace/simulation-runs/{rid}/replay").json()
    assert replay["run_id"] == rid
    assert replay["schema_version"] == 1
    assert replay["replay"]["meta"]["totalCases"] == 60
