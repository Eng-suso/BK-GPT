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


def test_a_month_factor_scales_the_rate_of_every_band_in_that_month():
    # SIM-08b: dicembre al triplo di novembre, stesse fasce.
    from datetime import UTC, datetime, timedelta

    numpy.random.seed(5)
    start = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    offsets = arrival_bands.arrival_offsets([MORNING], start, 3500, {12: 3.0})
    moments = [start + timedelta(seconds=s) for s in offsets]
    november = sum(1 for m in moments if m.month == 11)
    december = sum(1 for m in moments if m.month == 12 and m.day <= 30)
    # Novembre 2026 e i primi 30 giorni di dicembre hanno 21 e 22 giorni feriali.
    assert 2.6 < (december / 22) / (november / 21) < 3.4, (november, december)
    assert all(9 <= m.hour < 12 for m in moments)


@pytest.mark.parametrize("raw", [{"13": 1.2}, {"0": 1.0}, {"5": 0}, {"5": -1}, {"maggio": 1.1}])
def test_months_that_do_not_make_sense_are_refused(raw):
    with pytest.raises(ValueError):
        arrival_bands.parse_months(raw)


def test_the_runner_applies_the_months_and_says_so(client):
    scenario = {**contract_spike.base_scenario(), arrival_bands.SECTION: [MORNING],
                arrival_bands.MONTHS_SECTION: {"12": 1.4, "8": 0.5}}
    body = _post(client, scenario, cases=20, seed="11").get_json()
    assert body["ArrivalBands"] == 1 and body["ArrivalMonths"] == 2


def test_months_without_bands_are_a_bad_request(client):
    scenario = {**contract_spike.base_scenario(), arrival_bands.MONTHS_SECTION: {"12": 1.4}}
    response = _post(client, scenario, cases=10)
    assert response.status_code == 400
    assert arrival_bands.MONTHS_SECTION in response.get_data(as_text=True)


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


# --- SIM-33: la fascia di arrivo come attributo del caso -------------------------

def _band_scenario(**extra) -> dict:
    scenario = contract_spike.base_scenario()
    scenario["case_attributes"] = [{"name": "fascia", "type": "discrete", "values": [
        {"key": "Fascia 1", "value": 0.5}, {"key": "Fascia 2", "value": 0.5}]}]
    return {**scenario, arrival_bands.SECTION: [MORNING, AFTERNOON], **extra}


def test_each_case_carries_the_band_it_arrived_in(client):
    from datetime import UTC, datetime

    scenario = _band_scenario(**{arrival_bands.ATTRIBUTE_SECTION: "fascia"})
    rows = contract_spike.parse_log(_log(client, _post(client, scenario, cases=60, seed="5").get_json()))
    first: dict[str, dict] = {}
    for row in sorted(rows, key=lambda r: r["enable"]):
        first.setdefault(row["case_id"], row)
    assert len(first) == 60
    for row in first.values():
        hour = datetime.fromtimestamp(row["enable"], UTC).hour
        assert row["fascia"] == ("Fascia 1" if hour < 12 else "Fascia 2"), (hour, row["fascia"])
    assert {row["fascia"] for row in first.values()} == {"Fascia 1", "Fascia 2"}


def test_a_band_attribute_that_is_not_a_case_attribute_is_a_bad_request(client):
    response = _post(client, _band_scenario(**{arrival_bands.ATTRIBUTE_SECTION: "altro"}), cases=5)
    assert response.status_code == 400
    assert "altro" in response.get_json()["errorMessage"]


def test_the_plan_names_the_band_of_every_arrival():
    from datetime import UTC, datetime, timedelta

    numpy.random.seed(9)
    start = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    offsets, indices = arrival_bands.arrival_plan([MORNING, AFTERNOON], start, 300)
    for offset, index in zip(offsets, indices, strict=True):
        assert ((start + timedelta(seconds=offset)).hour < 12) == (index == 0)


# --- SIM-33b: durate per fascia oraria in cui l'attivita' inizia -----------------

import duration_windows  # noqa: E402

AFTERNOON_SLOWER = {"from": "MONDAY", "to": "FRIDAY", "beginTime": "13:00:00", "endTime": "17:00:00", "factor": 2}


def _windows_scenario(**windows) -> dict:
    scenario = contract_spike.base_scenario()
    # Una durata fissa: lo scarto viene solo dalla fascia, non dal campione.
    scenario["task_resource_distribution"][0]["resources"][0].update(contract_spike._dist("fix", 600))
    return {**scenario, **({duration_windows.SECTION: windows} if windows else {})}


def _receive_durations(client, scenario: dict, seed: str = "3") -> list[tuple[int, float]]:
    from datetime import UTC, datetime

    body = _post(client, scenario, cases=80, seed=seed).get_json()
    rows = [row for row in contract_spike.parse_log(_log(client, body)) if row["activity"] == "Ricevi"]
    # Solo le attivita' finite nello stesso giorno lavorativo: il resto lo allunga il calendario.
    return [
        (datetime.fromtimestamp(row["start"], UTC).hour, row["end"] - row["start"])
        for row in rows
        if datetime.fromtimestamp(row["end"], UTC).hour < 17 and datetime.fromtimestamp(row["end"], UTC).date()
        == datetime.fromtimestamp(row["start"], UTC).date()
    ]


def test_an_activity_that_starts_in_a_window_takes_the_factor_longer(client):
    durations = _receive_durations(client, _windows_scenario(T_receive=[AFTERNOON_SLOWER]))

    morning = [d for hour, d in durations if hour < 13]
    afternoon = [d for hour, d in durations if 13 <= hour < 17]
    assert morning and afternoon
    assert set(morning) == {600}
    assert set(afternoon) == {1200}


def test_the_runner_says_how_many_activities_it_changed_and_forgets_them_after_the_run(client):
    applied = _post(client, _windows_scenario(T_receive=[AFTERNOON_SLOWER]), cases=10).get_json()
    plain = _post(client, _windows_scenario(), cases=10).get_json()

    assert applied["DurationWindows"] == 1
    assert plain["DurationWindows"] == 0
    # Il run dopo, senza sezione, ha di nuovo la durata del motore anche il pomeriggio.
    assert {d for _, d in _receive_durations(client, _windows_scenario())} == {600}


def test_other_activities_keep_their_duration(client):
    from datetime import UTC, datetime

    scenario = _windows_scenario(T_receive=[AFTERNOON_SLOWER])
    with_windows = contract_spike.parse_log(_log(client, _post(client, scenario, cases=40, seed="4").get_json()))
    approvals = [row for row in with_windows if row["activity"] == "Approva"]
    assert approvals
    for row in approvals:
        start = datetime.fromtimestamp(row["start"], UTC)
        end = datetime.fromtimestamp(row["end"], UTC)
        # Normale 1800 +-300, limiti 600-3600: mai il doppio, se non lo allunga la notte.
        if end.date() == start.date() and end.hour < 17:
            assert row["end"] - row["start"] <= 3600


@pytest.mark.parametrize("windows", [
    {"T_receive": [{**AFTERNOON_SLOWER, "factor": 0}]},
    {"T_receive": [{**AFTERNOON_SLOWER, "factor": 11}]},
    {"T_receive": [AFTERNOON_SLOWER, {**AFTERNOON_SLOWER, "beginTime": "16:00:00", "endTime": "17:00:00"}]},
    {"T_receive": []},
    {"T_receive": [{**AFTERNOON_SLOWER, "from": "MOON"}]},
])
def test_windows_that_do_not_make_sense_are_a_bad_request(client, windows):
    response = _post(client, {**contract_spike.base_scenario(), duration_windows.SECTION: windows}, cases=5)

    assert response.status_code == 400
    assert duration_windows.SECTION in response.get_json()["errorMessage"]


def test_another_engine_version_refuses_the_windows(client, monkeypatch):
    monkeypatch.setattr(duration_windows, "SUPPORTED", "9.9.9")

    response = _post(client, _windows_scenario(T_receive=[AFTERNOON_SLOWER]), cases=5)

    assert response.status_code == 400
    assert "9.9.9" in response.get_json()["errorMessage"]


def test_the_factor_is_the_one_of_the_window_the_moment_falls_in():
    from datetime import UTC, datetime

    intervals = duration_windows.parse_windows({"T": [
        {"from": "FRIDAY", "to": "MONDAY", "beginTime": "08:00:00", "endTime": "10:00:00", "factor": 1.5},
    ]})["T"]

    assert duration_windows.factor_at(intervals, datetime(2026, 1, 9, 9, 30, tzinfo=UTC)) == 1.5  # venerdi'
    assert duration_windows.factor_at(intervals, datetime(2026, 1, 11, 8, 0, tzinfo=UTC)) == 1.5  # domenica
    assert duration_windows.factor_at(intervals, datetime(2026, 1, 13, 9, 0, tzinfo=UTC)) == 1.0  # martedi'
    assert duration_windows.factor_at(intervals, datetime(2026, 1, 9, 10, 0, tzinfo=UTC)) == 1.0  # fine esclusa
