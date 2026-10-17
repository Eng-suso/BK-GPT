"""Contratto del runner. Gira nell'ambiente del runner (Python 3.12 + prosimos 2.x):

    pip install -r ops/prosimos/runner/requirements-test.txt
    pytest ops/prosimos/runner
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "spike"))

import contract_spike  # noqa: E402
import runner  # noqa: E402

BPMN = (HERE.parent / "spike" / "p2p_mini.bpmn").read_bytes()
START = "2026-01-05T09:00:00.000000+00:00"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "DATA_DIR", tmp_path / "data")
    runner.app.config["TESTING"] = True
    return runner.app.test_client()


def _post(client, scenario: dict, cases: int = 60, **form):
    data = {
        "modelFile": (io.BytesIO(BPMN), "model.bpmn"),
        "simScenarioFile": (io.BytesIO(json.dumps(scenario).encode()), "scenario.json"),
        "numProcesses": str(cases),
        "startDate": START,
        **form,
    }
    return client.post("/api/simulate", data=data, content_type="multipart/form-data")


def _log(client, body: dict) -> str:
    response = client.get("/api/simulationFile", query_string={"fileName": body["LogsFilename"]})
    assert response.status_code == 200, response.data
    return response.data.decode()


def test_the_response_keeps_the_shape_the_adapter_decodes(client):
    response = _post(client, contract_spike.base_scenario())

    assert response.status_code == 200, response.data
    body = response.get_json()
    for key in ("ResourceUtilization", "IndividualTaskStatistics", "OverallScenarioStatistics"):
        records = json.loads(json.loads(body[key]))
        assert isinstance(records, list) and records, key
    kpis = {row["KPI"] for row in json.loads(json.loads(body["OverallScenarioStatistics"]))}
    assert {"cycle_time", "processing_time", "waiting_time"} <= kpis
    assert body["EngineVersion"].startswith("2.")
    assert _log(client, body).startswith("case_id,activity,enable_time,start_time,end_time,resource")


def test_the_same_seed_gives_the_same_log_and_another_seed_does_not(client):
    scenario = contract_spike.base_scenario()
    first = _log(client, _post(client, scenario, seed="11").get_json())
    again = _log(client, _post(client, scenario, seed="11").get_json())
    other = _log(client, _post(client, scenario, seed="12").get_json())

    assert first == again
    assert first != other


def test_a_run_without_seed_reports_the_seed_that_reproduces_it(client):
    scenario = contract_spike.base_scenario()
    body = _post(client, scenario).get_json()

    assert isinstance(body["Seed"], int)
    replay = _post(client, scenario, seed=str(body["Seed"])).get_json()
    assert _log(client, body) == _log(client, replay)


def test_conditional_routing_follows_the_case_attribute(client):
    """La ragione dell'upgrade: la 1.2.6 accettava le regole e le ignorava."""
    scenario = contract_spike.cap_branch_rules(contract_spike.base_scenario())
    rows = contract_spike.parse_log(_log(client, _post(client, scenario, seed="3").get_json()))

    assert contract_spike.check_branch_rules(rows) is None


def test_an_attribute_changed_during_the_process_reaches_the_log(client):
    scenario = contract_spike.cap_event_attributes(contract_spike.base_scenario())
    rows = contract_spike.parse_log(_log(client, _post(client, scenario, seed="3").get_json()))

    assert contract_spike.check_event_attributes(rows) is None


@pytest.mark.parametrize("name", ["../secret.csv", "logs_x.txt", "other_abc.csv", "", "logs_a/b.csv"])
def test_only_files_the_runner_wrote_can_be_downloaded(client, name):
    response = client.get("/api/simulationFile", query_string={"fileName": name})

    assert response.status_code == 400


def test_a_missing_or_expired_file_is_a_404(client):
    response = client.get("/api/simulationFile", query_string={"fileName": "logs_gone.csv"})

    assert response.status_code == 404


@pytest.mark.parametrize(
    "form, message",
    [
        ({"numProcesses": "zero"}, "numProcesses"),
        ({"numProcesses": "0"}, "numProcesses"),
        ({"seed": "abc"}, "seed"),
        ({"seed": "-1"}, "seed"),
    ],
)
def test_bad_parameters_are_a_400_with_the_reason(client, form, message):
    data = {
        "modelFile": (io.BytesIO(BPMN), "model.bpmn"),
        "simScenarioFile": (io.BytesIO(json.dumps(contract_spike.base_scenario()).encode()), "s.json"),
        "numProcesses": "10",
        **form,
    }
    response = client.post("/api/simulate", data=data, content_type="multipart/form-data")

    assert response.status_code == 400
    assert message in response.get_json()["errorMessage"]


def test_missing_files_are_a_400(client):
    response = client.post("/api/simulate", data={"numProcesses": "10"}, content_type="multipart/form-data")

    assert response.status_code == 400


def test_a_broken_scenario_says_why_instead_of_a_bare_500(client):
    scenario = contract_spike.base_scenario()
    del scenario["task_resource_distribution"]

    response = _post(client, scenario)

    assert response.status_code in (400, 500)
    assert response.get_json()["errorMessage"]


def test_old_files_are_purged(client, tmp_path):
    runner.DATA_DIR.mkdir(parents=True, exist_ok=True)
    stale = runner.DATA_DIR / "logs_old.csv"
    stale.write_text("x")
    leftover = runner.DATA_DIR / "tmp_interrupted"
    leftover.mkdir()
    (leftover / "model.bpmn").write_text("x")
    runner._purge_old_files(now=max(stale.stat().st_mtime, leftover.stat().st_mtime) + runner.FILE_TTL_SECONDS + 1)

    assert not stale.exists()
    assert not leftover.exists()


def test_health_names_the_engine(client):
    body = client.get("/health").get_json()

    assert body["engine"] == "prosimos" and body["engineVersion"].startswith("2.")


# --- SIM-08: arrivi per fascia oraria -------------------------------------------

import numpy  # noqa: E402

import arrival_bands  # noqa: E402

MORNING = {"from": "MONDAY", "to": "FRIDAY", "beginTime": "09:00:00", "endTime": "12:00:00", "meanSeconds": 300}
AFTERNOON = {"from": "MONDAY", "to": "FRIDAY", "beginTime": "14:00:00", "endTime": "17:00:00", "meanSeconds": 1800}


def test_arrivals_follow_the_rate_of_each_band_and_never_fall_outside():
    from datetime import UTC, datetime, timedelta

    numpy.random.seed(7)
    start = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)  # un lunedi'
    offsets = arrival_bands.arrival_offsets([MORNING, AFTERNOON], start, 2000)
    moments = [start + timedelta(seconds=s) for s in offsets]

    assert offsets == sorted(offsets)
    assert all(m.weekday() < 5 and (9 <= m.hour < 12 or 14 <= m.hour < 17) for m in moments)
    morning = sum(1 for m in moments if m.hour < 12)
    # Ritmi 1/300 e 1/1800 su fasce di uguale durata: sei arrivi al mattino per uno al pomeriggio.
    assert 5.0 < morning / (len(moments) - morning) < 7.2


def test_the_same_seed_gives_the_same_arrivals_and_a_mid_week_start_is_respected():
    from datetime import UTC, datetime

    start = datetime(2026, 1, 7, 10, 30, tzinfo=UTC)  # mercoledi' dentro la fascia
    numpy.random.seed(3)
    first = arrival_bands.arrival_offsets([MORNING], start, 50)
    numpy.random.seed(3)
    assert arrival_bands.arrival_offsets([MORNING], start, 50) == first
    # Il primo arrivo e' dopo l'inizio, non all'inizio della fascia gia' cominciata.
    assert 0 < first[0] < 90 * 60


@pytest.mark.parametrize("bands", [
    [MORNING, {**MORNING, "beginTime": "11:00:00", "endTime": "13:00:00"}],
    [{**MORNING, "meanSeconds": 0}],
    [],
])
def test_bands_that_do_not_make_sense_are_refused(bands):
    with pytest.raises(ValueError):
        arrival_bands.weekly_intervals(bands)


def test_the_runner_applies_the_bands_and_says_so(client):
    scenario = {**contract_spike.base_scenario(), arrival_bands.SECTION: [MORNING]}
    response = _post(client, scenario, cases=40, seed="11")

    assert response.status_code == 200, response.data
    body = response.get_json()
    assert body["ArrivalBands"] == 1
    rows = contract_spike.parse_log(_log(client, body))
    starts = {}
    for row in rows:
        starts.setdefault(row["case_id"], row["enable"])
    from datetime import UTC, datetime

    hours = {datetime.fromtimestamp(t, UTC).hour for t in starts.values()}
    assert hours <= {9, 10, 11}, hours


def test_a_scenario_without_bands_keeps_the_engine_arrivals(client):
    body = _post(client, contract_spike.base_scenario(), cases=10).get_json()
    assert body["ArrivalBands"] == 0


def test_overlapping_bands_are_a_bad_request(client):
    scenario = {**contract_spike.base_scenario(), arrival_bands.SECTION: [MORNING, MORNING]}
    response = _post(client, scenario, cases=10)
    assert response.status_code == 400
    assert "si sovrappongono" in response.get_json()["errorMessage"]
