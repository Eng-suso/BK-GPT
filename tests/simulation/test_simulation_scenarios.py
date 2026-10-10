"""SIM-14: il workspace degli scenari AS-IS | A | B | C, via API."""

from tests.simulation.test_simulation_ir_contract import MINIMAL_BPMN

TENANT_A = {"X-DeliR-Tenant-ID": "sim-scenarios-a"}
TENANT_B = {"X-DeliR-Tenant-ID": "sim-scenarios-b"}

AS_IS = {
    "scenarioName": "Baseline AS-IS",
    "totalCases": 100,
    "resources": [{"id": "approver", "name": "Approvatore", "amount": 2, "costPerHour": 40}],
    "tasks": {"Task_1": {"meanMinutes": 30, "resourceId": "approver"}},
}
PLUS_ONE_APPROVER = [{"op": "set", "path": ["resources", {"id": "approver"}, "amount"], "value": 3}]


def _url(model_id: str, suffix: str = "") -> str:
    return f"/v1/workspace/bpmn-models/{model_id}/simulation-scenarios{suffix}"


def _with_baseline(api_client, model_id: str, headers=None) -> dict:
    response = api_client.put(_url(model_id, "/baseline"), json={"name": "AS-IS", "draft": AS_IS}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_new_process_has_an_empty_workspace(api_client, new_bpmn_model):
    model_id = new_bpmn_model()

    workspace = api_client.get(_url(model_id)).json()

    assert workspace == {"bpmn_model_id": model_id, "seed": None, "baseline": None, "alternatives": []}


def test_the_as_is_gets_a_shared_seed_and_a_revision(api_client, new_bpmn_model):
    model_id = new_bpmn_model()

    workspace = _with_baseline(api_client, model_id)

    assert isinstance(workspace["seed"], int)
    baseline = workspace["baseline"]
    assert (baseline["kind"], baseline["label"], baseline["revision"]) == ("baseline", "AS-IS", 1)
    assert baseline["draft"] == AS_IS
    assert api_client.get(_url(model_id)).json() == workspace


def test_the_as_is_changes_only_from_the_revision_it_was_read_at(api_client, new_bpmn_model):
    model_id = new_bpmn_model()
    seed = _with_baseline(api_client, model_id)["seed"]
    edited = {**AS_IS, "totalCases": 200}

    updated = api_client.put(_url(model_id, "/baseline"), json={"name": "AS-IS", "draft": edited, "revision": 1})
    stale = api_client.put(_url(model_id, "/baseline"), json={"name": "AS-IS", "draft": AS_IS, "revision": 1})
    recreate = api_client.put(_url(model_id, "/baseline"), json={"name": "AS-IS", "draft": AS_IS})

    assert updated.status_code == 200, updated.text
    assert updated.json()["baseline"]["revision"] == 2
    assert updated.json()["baseline"]["draft"]["totalCases"] == 200
    # Il seed comune resta, se non lo si cambia apposta.
    assert updated.json()["seed"] == seed
    assert stale.status_code == 409
    assert recreate.status_code == 409


def test_a_new_seed_is_kept_and_bumps_the_revision(api_client, new_bpmn_model):
    model_id = new_bpmn_model()
    _with_baseline(api_client, model_id)

    response = api_client.put(_url(model_id, "/baseline"), json={"name": "AS-IS", "draft": AS_IS, "seed": 1234, "revision": 1})

    assert response.json()["seed"] == 1234
    assert response.json()["baseline"]["revision"] == 2


def test_an_alternative_needs_the_as_is_first(api_client, new_bpmn_model):
    response = api_client.post(_url(new_bpmn_model()), json={"name": "+1 approvatore"})

    assert response.status_code == 400
    assert "AS-IS" in response.text


def test_an_alternative_is_the_as_is_with_its_patch(api_client, new_bpmn_model):
    model_id = new_bpmn_model()
    _with_baseline(api_client, model_id)

    workspace = api_client.post(_url(model_id), json={"name": "+1 approvatore", "patch": PLUS_ONE_APPROVER}).json()

    [alternative] = workspace["alternatives"]
    assert (alternative["label"], alternative["name"], alternative["revision"]) == ("A", "+1 approvatore", 1)
    assert alternative["patch"] == PLUS_ONE_APPROVER
    assert alternative["draft"]["resources"][0]["amount"] == 3
    assert alternative["draft"]["tasks"] == AS_IS["tasks"]
    assert alternative["conflicts"] == []


def test_what_the_alternative_does_not_touch_follows_the_as_is(api_client, new_bpmn_model):
    model_id = new_bpmn_model()
    _with_baseline(api_client, model_id)
    api_client.post(_url(model_id), json={"name": "+1 approvatore", "patch": PLUS_ONE_APPROVER})
    edited = {**AS_IS, "tasks": {"Task_1": {"meanMinutes": 45, "resourceId": "approver"}}}

    workspace = api_client.put(_url(model_id, "/baseline"), json={"name": "AS-IS", "draft": edited, "revision": 1}).json()

    alternative = workspace["alternatives"][0]
    assert alternative["draft"]["tasks"]["Task_1"]["meanMinutes"] == 45
    assert alternative["draft"]["resources"][0]["amount"] == 3


def test_a_change_on_something_the_as_is_dropped_is_a_conflict(api_client, new_bpmn_model):
    model_id = new_bpmn_model()
    _with_baseline(api_client, model_id)
    patch = [{"op": "set", "path": ["tasks", "Task_1", "meanMinutes"], "value": 10}]
    api_client.post(_url(model_id), json={"name": "Più veloce", "patch": patch})

    workspace = api_client.put(
        _url(model_id, "/baseline"), json={"name": "AS-IS", "draft": {**AS_IS, "tasks": {}}, "revision": 1}
    ).json()

    assert workspace["alternatives"][0]["conflicts"] == [0]
    assert workspace["alternatives"][0]["draft"]["tasks"] == {}


def test_an_alternative_changes_only_from_its_revision(api_client, new_bpmn_model):
    model_id = new_bpmn_model()
    _with_baseline(api_client, model_id)
    scenario_id = api_client.post(_url(model_id), json={"name": "B"}).json()["alternatives"][0]["id"]

    renamed = api_client.patch(_url(model_id, f"/{scenario_id}"), json={"name": "+1 approvatore", "revision": 1})
    patched = api_client.patch(_url(model_id, f"/{scenario_id}"), json={"patch": PLUS_ONE_APPROVER, "revision": 2})
    stale = api_client.patch(_url(model_id, f"/{scenario_id}"), json={"name": "Altro", "revision": 1})

    assert renamed.json()["alternatives"][0]["name"] == "+1 approvatore"
    after = patched.json()["alternatives"][0]
    assert (after["name"], after["revision"]) == ("+1 approvatore", 3)
    assert after["draft"]["resources"][0]["amount"] == 3
    assert stale.status_code == 409


def test_letters_are_reused_and_capped_at_five(api_client, new_bpmn_model):
    model_id = new_bpmn_model()
    _with_baseline(api_client, model_id)
    for name in ("uno", "due", "tre", "quattro", "cinque"):
        assert api_client.post(_url(model_id), json={"name": name}).status_code == 200

    sixth = api_client.post(_url(model_id), json={"name": "sei"})
    workspace = api_client.get(_url(model_id)).json()
    second = next(item for item in workspace["alternatives"] if item["label"] == "B")
    after_delete = api_client.delete(_url(model_id, f"/{second['id']}")).json()
    again = api_client.post(_url(model_id), json={"name": "sei"}).json()

    assert sixth.status_code == 400
    assert [item["label"] for item in workspace["alternatives"]] == ["A", "B", "C", "D", "E"]
    assert [item["label"] for item in after_delete["alternatives"]] == ["A", "C", "D", "E"]
    assert next(item for item in again["alternatives"] if item["label"] == "B")["name"] == "sei"


def test_the_as_is_cannot_be_deleted_and_unknown_scenarios_are_404(api_client, new_bpmn_model):
    model_id = new_bpmn_model()
    baseline_id = _with_baseline(api_client, model_id)["baseline"]["id"]

    assert api_client.delete(_url(model_id, f"/{baseline_id}")).status_code == 400
    assert api_client.delete(_url(model_id, "/999999")).status_code == 404
    assert api_client.patch(_url(model_id, f"/{baseline_id}"), json={"name": "x", "revision": 1}).status_code == 404


def test_a_malformed_patch_is_rejected(api_client, new_bpmn_model):
    model_id = new_bpmn_model()
    _with_baseline(api_client, model_id)

    order_without_ids = api_client.post(_url(model_id), json={"name": "x", "patch": [{"op": "order", "path": ["resources"]}]})
    remove_with_value = api_client.post(_url(model_id), json={"name": "x", "patch": [{"op": "remove", "path": ["a"], "value": 1}]})
    empty_path = api_client.post(_url(model_id), json={"name": "x", "patch": [{"op": "set", "path": [], "value": 1}]})

    assert {order_without_ids.status_code, remove_with_value.status_code, empty_path.status_code} == {422}


def test_unknown_process_is_404(api_client):
    assert api_client.get(_url("bpmn-che-non-esiste")).status_code == 404


def test_another_tenant_sees_neither_the_workspace_nor_its_scenarios(api_client, new_bpmn_model):
    model_id = new_bpmn_model(TENANT_A)
    workspace = _with_baseline(api_client, model_id, TENANT_A)
    api_client.post(_url(model_id), json={"name": "A"}, headers=TENANT_A)

    assert api_client.get(_url(model_id), headers=TENANT_B).status_code == 404
    assert api_client.delete(_url(model_id, f"/{workspace['baseline']['id']}"), headers=TENANT_B).status_code == 404
    other_model = new_bpmn_model(TENANT_B)
    assert api_client.get(_url(other_model), headers=TENANT_B).json()["baseline"] is None


def _run(api_client, model_id: str, ref: dict, **extra):
    return api_client.post(
        f"/v1/workspace/bpmn-models/{model_id}/simulation-runs",
        json={"total_cases": 5, "current_bpmn_xml": MINIMAL_BPMN, "workspace_scenario": ref, **extra},
    )


def test_a_run_remembers_the_scenario_and_revisions_it_simulated(api_client, new_bpmn_model, fake_engine):
    model_id = new_bpmn_model()
    workspace = _with_baseline(api_client, model_id)
    scenario = api_client.post(_url(model_id), json={"name": "A"}).json()["alternatives"][0]
    ref = {"id": scenario["id"], "revision": 1, "baseline_revision": 1}

    single = _run(api_client, model_id, ref)
    group = _run(api_client, model_id, {**ref, "id": workspace["baseline"]["id"]}, replications=2, seed=workspace["seed"])

    assert single.status_code == 200, single.text
    assert single.json()["request"]["workspace_scenario"] == ref
    assert group.status_code == 200, group.text
    runs = api_client.get(f"/v1/workspace/bpmn-models/{model_id}/simulation-runs").json()
    members = [run for run in runs if run["request"].get("replication_group") == group.json()["request"]["replication_group"]]
    assert len(members) == 2
    assert {run["request"]["workspace_scenario"]["id"] for run in members} == {workspace["baseline"]["id"]}
    # Il seed comune del workspace: le ripetizioni partono da li'.
    assert sorted(run["request"]["seed"] for run in members) == [workspace["seed"], workspace["seed"] + 1]


def test_a_run_cannot_cite_a_scenario_of_another_process_or_a_future_revision(api_client, new_bpmn_model, fake_engine):
    model_id = new_bpmn_model()
    other_id = new_bpmn_model()
    baseline_id = _with_baseline(api_client, model_id)["baseline"]["id"]
    _with_baseline(api_client, other_id)

    foreign = _run(api_client, other_id, {"id": baseline_id, "revision": 1, "baseline_revision": 1})
    future = _run(api_client, model_id, {"id": baseline_id, "revision": 2, "baseline_revision": 1})
    missing = _run(api_client, model_id, {"id": 999999, "revision": 1, "baseline_revision": 1})

    assert foreign.status_code == 400
    assert future.status_code == 400
    assert missing.status_code == 400
