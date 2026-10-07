"""API di import degli event log: upload, anteprima, mapping, template, tenant."""

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.eventlog.test_eventlog_import import ERP_CSV

BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Defs">
  <bpmn:process id="P2P" isExecutable="false">
    <bpmn:startEvent id="Start" />
    <bpmn:task id="T1" name="Ricevi richiesta" />
    <bpmn:task id="T2" name="Approvazione ordine" />
    <bpmn:task id="T3" name="Paga fornitore" />
    <bpmn:endEvent id="End" />
    <bpmn:sequenceFlow id="F0" sourceRef="Start" targetRef="T1" />
    <bpmn:sequenceFlow id="F1" sourceRef="T1" targetRef="T2" />
    <bpmn:sequenceFlow id="F2" sourceRef="T2" targetRef="T3" />
    <bpmn:sequenceFlow id="F3" sourceRef="T3" targetRef="End" />
  </bpmn:process>
</bpmn:definitions>
"""

MAPPING = {
    "case_id": ["Ordine", "Riga"],
    "activity": ["Attivita"],
    "start": "Inizio",
    "end": "Fine",
    "resource": "Utente",
    "case_attributes": [
        {"column": "Importo", "name": "importo", "type": "number"},
        {"column": "Paese", "name": "paese", "type": "category"},
    ],
    "timestamps": {"pattern": "%d/%m/%Y %H:%M"},
    "numbers": {"decimal": ",", "thousands": "."},
}

XES = b"""<?xml version="1.0" encoding="UTF-8"?>
<log xmlns="http://www.xes-standard.org/">
  <trace><string key="concept:name" value="C1"/>
    <event><string key="concept:name" value="Ricevi richiesta"/>
      <date key="time:timestamp" value="2026-01-05T09:10:00+01:00"/></event>
  </trace>
</log>
"""


@pytest.fixture(scope="module")
def client():
    from backend.app import app

    with TestClient(app) as test_client:
        yield test_client


def _tenant() -> dict[str, str]:
    return {"X-DeliR-Tenant-ID": f"elog-{uuid.uuid4().hex[:8]}"}


def _process(client: TestClient, headers: dict[str, str], *, bpmn: str | None = BPMN) -> str:
    client_id = client.post("/v1/workspace/clients", json={"name": "ERP Spa"}, headers=headers).json()["id"]
    project_id = client.post(
        "/v1/workspace/projects", json={"client_id": client_id, "name": "P2P"}, headers=headers
    ).json()["id"]
    process = client.post(
        f"/v1/workspace/projects/{project_id}/processes", json={"name": "Purchase to pay"}, headers=headers
    ).json()
    if bpmn is not None:
        saved = client.put(f"/v1/workspace/bpmn-models/{process['bpmn_model_id']}", json={"xml": bpmn}, headers=headers)
        assert saved.status_code == 200, saved.text
    return process["id"]


def _upload(client, headers, process_id, payload=ERP_CSV.encode(), name="erp.csv", **form):
    return client.post(
        f"/v1/workspace/processes/{process_id}/event-logs",
        files={"file": (name, payload, "text/csv")},
        data=form,
        headers=headers,
    )


def test_upload_recognises_the_separator_and_previews_the_columns(client):
    headers = _tenant()
    process_id = _process(client, headers)

    response = _upload(client, headers, process_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True
    assert body["status"] == "uploaded"
    assert body["delimiter"] == ";"
    assert body["format"] == "csv"
    assert body["row_count"] == 9
    assert body["columns"][:3] == ["Ordine", "Riga", "Attivita"]
    assert body["preview"]["sample_rows"][0][:3] == ["PO-1", "1", "Ricevi richiesta"]
    listed = client.get(f"/v1/workspace/processes/{process_id}/event-logs", headers=headers).json()
    assert [log["id"] for log in listed] == [body["id"]]


def test_the_same_file_uploaded_again_finds_its_log(client):
    headers = _tenant()
    process_id = _process(client, headers)
    first = _upload(client, headers, process_id).json()

    again = _upload(client, headers, process_id)

    assert again.status_code == 200
    assert again.json()["id"] == first["id"]
    assert again.json()["created"] is False


def test_a_different_separator_previews_without_changing_the_log(client):
    headers = _tenant()
    process_id = _process(client, headers)
    log_id = _upload(client, headers, process_id).json()["id"]

    preview = client.get(f"/v1/workspace/event-logs/{log_id}/preview", params={"delimiter": ","}, headers=headers)

    assert preview.status_code == 422  # con la virgola resta una sola colonna
    assert client.get(f"/v1/workspace/event-logs/{log_id}", headers=headers).json()["delimiter"] == ";"


def test_unsupported_and_unreadable_files_are_refused(client):
    headers = _tenant()
    process_id = _process(client, headers)

    assert _upload(client, headers, process_id, b"%PDF-1.4", name="log.pdf").status_code == 415
    assert _upload(client, headers, process_id, b"", name="vuoto.csv").status_code == 415
    assert _upload(client, headers, process_id, XES, name="log.xes", delimiter=";").status_code == 415


def test_mapping_returns_quality_matches_and_kpis_and_is_saved(client):
    headers = _tenant()
    process_id = _process(client, headers)
    log_id = _upload(client, headers, process_id).json()["id"]

    response = client.post(f"/v1/workspace/event-logs/{log_id}/mapping", json={"mapping": MAPPING}, headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["event_log"]["status"] == "mapped"
    assert body["quality"]["events"] == 5
    assert body["quality"]["rows_excluded"] == 3
    codes = {issue["code"] for issue in body["quality"]["issues"]}
    assert {"missing_case_id", "unreadable_timestamp", "end_before_start", "duplicate_event"} <= codes
    matches = {m["activity"]: m["element_id"] for m in body["activities"]["matches"]}
    assert matches == {"Ricevi richiesta": "T1", "Paga fornitore": "T3", "Approva ordine": None}
    assert body["activities"]["confirmed"] is False
    assert body["activities"]["bpmn_version_id"] is not None
    assert [e["element_id"] for e in body["activities"]["unobserved_elements"]] == ["T2"]
    assert body["summary"]["source"] == "real"
    assert body["summary"]["casesCompleted"] == 2

    stored = client.get(f"/v1/workspace/event-logs/{log_id}/analysis", headers=headers)
    assert stored.status_code == 200
    assert stored.json()["quality"] == body["quality"]


def test_the_consultant_confirms_the_activity_matches(client):
    headers = _tenant()
    process_id = _process(client, headers)
    log_id = _upload(client, headers, process_id).json()["id"]
    confirmed = {"Ricevi richiesta": "T1", "Approva ordine": "T2", "Paga fornitore": None}

    body = client.post(
        f"/v1/workspace/event-logs/{log_id}/mapping",
        json={"mapping": MAPPING, "activity_matches": confirmed},
        headers=headers,
    ).json()

    assert body["activities"]["confirmed"] is True
    assert {m["activity"]: m["element_id"] for m in body["activities"]["matches"]} == confirmed
    assert body["activities"]["unmatched_activities"] == ["Paga fornitore"]

    unknown = client.post(
        f"/v1/workspace/event-logs/{log_id}/mapping",
        json={"mapping": MAPPING, "activity_matches": {"Approva ordine": "T99"}},
        headers=headers,
    )
    assert unknown.status_code == 400


def test_mapping_on_missing_columns_and_unmapped_analysis_are_explicit(client):
    headers = _tenant()
    process_id = _process(client, headers)
    log_id = _upload(client, headers, process_id).json()["id"]

    assert client.get(f"/v1/workspace/event-logs/{log_id}/analysis", headers=headers).status_code == 409
    wrong = client.post(
        f"/v1/workspace/event-logs/{log_id}/mapping",
        json={"mapping": {**MAPPING, "resource": "Operatore"}},
        headers=headers,
    )
    assert wrong.status_code == 422
    assert "Operatore" in wrong.json()["error"]["message"]
    both = client.post(
        f"/v1/workspace/event-logs/{log_id}/mapping",
        json={"mapping": MAPPING, "template_id": 1},
        headers=headers,
    )
    assert both.status_code == 422


def test_a_log_without_valid_events_has_no_kpis(client):
    headers = _tenant()
    process_id = _process(client, headers)
    csv = "Ordine;Riga;Attivita;Inizio;Fine;Utente;Importo;Paese\n;1;Ricevi;ieri;oggi;anna;1;IT\n"
    log_id = _upload(client, headers, process_id, csv.encode()).json()["id"]

    body = client.post(f"/v1/workspace/event-logs/{log_id}/mapping", json={"mapping": MAPPING}, headers=headers).json()

    assert body["summary"] is None
    assert body["quality"]["events"] == 0


def test_a_process_without_bpmn_leaves_every_activity_unmatched(client):
    headers = _tenant()
    process_id = _process(client, headers, bpmn=None)
    log_id = _upload(client, headers, process_id).json()["id"]

    body = client.post(f"/v1/workspace/event-logs/{log_id}/mapping", json={"mapping": MAPPING}, headers=headers).json()

    assert body["activities"]["bpmn_version_id"] is None
    assert len(body["activities"]["unmatched_activities"]) == 3
    assert body["summary"] is not None


def test_templates_are_versioned_and_remap_with_one_click(client):
    headers = _tenant()
    process_id = _process(client, headers)
    columns = _upload(client, headers, process_id).json()["columns"]

    first = client.post(
        "/v1/workspace/event-log-templates",
        json={"name": "Export SAP", "mapping": {**MAPPING, "resource": None}, "columns": columns},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    key = first.json()["template_key"]
    second = client.post(
        "/v1/workspace/event-log-templates",
        json={"name": "Export SAP", "mapping": MAPPING, "columns": columns, "template_key": key},
        headers=headers,
    ).json()
    assert second["version"] == 2

    latest = client.get("/v1/workspace/event-log-templates", headers=headers).json()
    assert [(t["template_key"], t["version"]) for t in latest] == [(key, 2)]
    versions = client.get(f"/v1/workspace/event-log-templates/{key}/versions", headers=headers).json()
    assert [v["version"] for v in versions] == [2, 1]

    other_file = ERP_CSV.replace("PO-4", "PO-5").encode()
    log_id = _upload(client, headers, process_id, other_file, name="erp-ottobre.csv").json()["id"]
    body = client.post(
        f"/v1/workspace/event-logs/{log_id}/mapping", json={"template_id": first.json()["id"]}, headers=headers
    ).json()
    assert body["event_log"]["template"] == {"id": first.json()["id"], "template_key": key, "version": 1, "name": "Export SAP"}
    assert body["event_log"]["mapping"]["resource"] is None
    assert body["quality"]["resources"] == 0


def test_a_template_must_use_its_own_columns(client):
    headers = _tenant()
    response = client.post(
        "/v1/workspace/event-log-templates",
        json={"name": "Rotto", "mapping": MAPPING, "columns": ["Ordine"]},
        headers=headers,
    )
    assert response.status_code == 422
    unknown_key = client.post(
        "/v1/workspace/event-log-templates",
        json={"name": "X", "mapping": MAPPING, "columns": list(MAPPING_COLUMNS), "template_key": "tmpl_nessuno"},
        headers=headers,
    )
    assert unknown_key.status_code == 404


MAPPING_COLUMNS = ("Ordine", "Riga", "Attivita", "Inizio", "Fine", "Utente", "Importo", "Paese")


def test_another_tenant_sees_nothing(client):
    owner = _tenant()
    stranger = _tenant()
    process_id = _process(client, owner)
    log_id = _upload(client, owner, process_id).json()["id"]
    template = client.post(
        "/v1/workspace/event-log-templates",
        json={"name": "SAP", "mapping": MAPPING, "columns": list(MAPPING_COLUMNS)},
        headers=owner,
    ).json()

    assert _upload(client, stranger, process_id).status_code == 404
    assert client.get(f"/v1/workspace/processes/{process_id}/event-logs", headers=stranger).status_code == 404
    assert client.get(f"/v1/workspace/event-logs/{log_id}", headers=stranger).status_code == 404
    assert client.get(f"/v1/workspace/event-logs/{log_id}/preview", headers=stranger).status_code == 404
    assert client.post(
        f"/v1/workspace/event-logs/{log_id}/mapping", json={"mapping": MAPPING}, headers=stranger
    ).status_code == 404
    assert client.delete(f"/v1/workspace/event-logs/{log_id}", headers=stranger).status_code == 404
    assert client.get("/v1/workspace/event-log-templates", headers=stranger).json() == []
    assert client.get(
        f"/v1/workspace/event-log-templates/{template['template_key']}/versions", headers=stranger
    ).status_code == 404
    # Il template di un altro tenant non si applica nemmeno al proprio log.
    own_process = _process(client, stranger)
    own_log = _upload(client, stranger, own_process).json()["id"]
    assert client.post(
        f"/v1/workspace/event-logs/{own_log}/mapping", json={"template_id": template["id"]}, headers=stranger
    ).status_code == 404


def test_deleting_the_log_or_its_process_removes_it(client):
    headers = _tenant()
    process_id = _process(client, headers)
    first = _upload(client, headers, process_id).json()["id"]
    client.post(f"/v1/workspace/event-logs/{first}/mapping", json={"mapping": MAPPING}, headers=headers)

    assert client.delete(f"/v1/workspace/event-logs/{first}", headers=headers).status_code == 204
    assert client.get(f"/v1/workspace/event-logs/{first}", headers=headers).status_code == 404

    second = _upload(client, headers, process_id).json()["id"]
    deleted = client.delete(f"/v1/workspace/processes/{process_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert client.get(f"/v1/workspace/event-logs/{second}", headers=headers).status_code == 404
