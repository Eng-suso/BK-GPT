"""SIM-04: lo stesso scenario ripetuto con seed consecutivi, in un gruppo."""

from tests.simulation.test_simulation_replay import MINIMAL_BPMN


def _url(api_client, new_bpmn_model) -> str:
    return f"/v1/workspace/bpmn-models/{new_bpmn_model()}/simulation-runs"


def test_replications_become_runs_with_consecutive_seeds_in_one_group(api_client, new_bpmn_model, fake_engine):
    url = _url(api_client, new_bpmn_model)
    first = api_client.post(url, json={"total_cases": 10, "seed": 100, "replications": 3, "scenario_name": "Base",
                                       "current_bpmn_xml": MINIMAL_BPMN})
    assert first.status_code == 200, first.text

    runs = sorted(api_client.get(url).json(), key=lambda run: run["request"]["replication_index"])
    assert [run["request"]["seed"] for run in runs] == [100, 101, 102]
    assert len({run["request"]["replication_group"] for run in runs}) == 1
    assert [run["scenario_name"] for run in runs] == ["Base · 1/3", "Base · 2/3", "Base · 3/3"]
    assert first.json()["request"]["replication_index"] == 1
    assert sorted(request.seed for request in fake_engine) == [100, 101, 102]


def test_a_single_run_has_no_group(api_client, new_bpmn_model, fake_engine):
    run = api_client.post(_url(api_client, new_bpmn_model), json={"total_cases": 10, "current_bpmn_xml": MINIMAL_BPMN}).json()
    assert run["request"]["replication_group"] is None


def test_a_group_that_does_not_fit_the_queue_is_refused_whole(api_client, new_bpmn_model, fake_engine, monkeypatch):
    from backend.settings import settings

    monkeypatch.setattr(settings, "simulation_max_queued_runs", 2)
    url = _url(api_client, new_bpmn_model)
    response = api_client.post(url, json={"total_cases": 10, "replications": 3, "current_bpmn_xml": MINIMAL_BPMN})
    assert response.status_code == 429
    assert "3 ripetizioni non ci stanno" in response.json()["error"]["message"]
    assert api_client.get(url).json() == []


def _hold_the_queue(monkeypatch) -> None:
    """Nessuno esegue: i run restano in coda, come durante un invio ritentato."""
    async def idle(*_args, **_kwargs) -> int:
        return 0

    monkeypatch.setattr("backend.api.routes.simulation.drain_simulation_queue", idle)


def test_a_retried_unseeded_group_finds_the_group_already_queued(api_client, new_bpmn_model, fake_engine, monkeypatch):
    _hold_the_queue(monkeypatch)
    url = _url(api_client, new_bpmn_model)
    body = {"total_cases": 10, "replications": 3, "current_bpmn_xml": MINIMAL_BPMN}
    first = api_client.post(url, json=body).json()
    again = api_client.post(url, json=body).json()

    assert again["id"] == first["id"]
    assert len(api_client.get(url).json()) == 3


def test_group_and_position_sent_by_the_client_are_ignored(api_client, new_bpmn_model, fake_engine, monkeypatch):
    _hold_the_queue(monkeypatch)
    url = _url(api_client, new_bpmn_model)
    single = api_client.post(url, json={"total_cases": 10, "current_bpmn_xml": MINIMAL_BPMN,
                                        "replication_group": "altrui", "replication_index": 4}).json()
    assert single["request"]["replication_group"] is None
    assert single["request"]["replication_index"] is None

    api_client.post(url, json={"total_cases": 10, "seed": 7, "replications": 2, "current_bpmn_xml": MINIMAL_BPMN,
                               "replication_group": "altrui"})
    groups = {run["request"]["replication_group"] for run in api_client.get(url).json()} - {None}
    assert len(groups) == 1
    assert "altrui" not in groups


def test_seeds_past_the_engine_limit_are_refused(api_client, new_bpmn_model, fake_engine):
    url = _url(api_client, new_bpmn_model)
    response = api_client.post(url, json={"total_cases": 10, "seed": 2**32 - 2, "replications": 3,
                                          "current_bpmn_xml": MINIMAL_BPMN})
    assert response.status_code == 400
    assert "seed iniziale" in response.json()["error"]["message"]
    assert api_client.get(url).json() == []


def test_a_group_that_fails_halfway_leaves_no_runs(api_client, new_bpmn_model, fake_engine, monkeypatch):
    from backend.simulation import storage

    real = storage._new_run
    calls = {"n": 0}

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ValueError("Ripetizione non registrata.")
        return real(**kwargs)

    monkeypatch.setattr(storage, "_new_run", flaky)
    url = _url(api_client, new_bpmn_model)
    response = api_client.post(url, json={"total_cases": 10, "replications": 3, "current_bpmn_xml": MINIMAL_BPMN})
    assert response.status_code == 400
    assert api_client.get(url).json() == []
