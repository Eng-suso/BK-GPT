"""L5 through the real write path: local edits and concurrent agent writes.

`test_canvas_edit_integrity.py` checks the semantic diff on in-memory XML.
Here every edit goes through `update_bpmn_model` on the isolated Postgres
stack, so the write policy (`_canvas_xml_for_write`) and the version guard
are part of what is measured: the XML read back after the write may differ
from the XML before it only by the declared delta, and two writers starting
from the same version never both land.
"""

from __future__ import annotations

import threading
import uuid
from pathlib import Path

import pytest

from backend import workspace_database as wd
from backend.agents.run_context import BpmnVersionConflict, bind_turn_writes
from backend.bpmn.edit_integrity import assert_local_edit_integrity
from backend.security import reset_current_tenant_id, set_current_tenant_id
from backend.workspace_services.bpmn_canvas_edit import (
    add_bpmn_element,
    connect_bpmn_elements,
    delete_bpmn_element,
    list_bpmn_elements,
    optimize_bpmn_layout,
    reconnect_bpmn_flow,
    update_bpmn_element,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TASK_TYPES = {"task", "userTask", "serviceTask", "manualTask"}


@pytest.fixture()
def tenant():
    tenant_id = f"t-l5-{uuid.uuid4().hex[:8]}"
    token = set_current_tenant_id(tenant_id)
    try:
        yield tenant_id
    finally:
        reset_current_tenant_id(token)


def _seeded_model(fixture_name: str) -> tuple[str, dict]:
    client = wd.create_client(name="Synthetic L5 test")
    project = wd.create_project(client_id=client["id"], name="L5")
    process = wd.create_process(project_id=project["id"], name=f"L5 {uuid.uuid4().hex[:6]}")
    saved = wd.update_bpmn_model(
        process["bpmn_model_id"],
        (FIXTURES / fixture_name).read_text(encoding="utf-8"),
        source="canvas_benchmark_seed",
    )
    assert saved is not None
    return process["bpmn_model_id"], saved


def _ids(xml: str) -> dict[str, str]:
    elements = list_bpmn_elements(xml)
    tasks = [item["id"] for item in elements if item["type"] in TASK_TYPES]
    return {
        "task": tasks[0],
        "other_task": tasks[-1],
        "start": next(item["id"] for item in elements if item["type"] == "startEvent"),
        "end": next(item["id"] for item in elements if item["type"] == "endEvent"),
        "flow": next(item["id"] for item in elements if item["type"] == "sequenceFlow"),
    }


EDITS = {
    "update_element": lambda xml, ids: (
        *update_bpmn_element(xml, ids["task"], name="Renamed by L5"), ids["task"]),
    "add_element": lambda xml, ids: (*add_bpmn_element(xml, "task", "Added by L5"), None),
    "delete_element": lambda xml, ids: (*delete_bpmn_element(xml, ids["task"]), None),
    "connect_elements": lambda xml, ids: (*connect_bpmn_elements(xml, ids["start"], ids["end"]), None),
    "reconnect_flow": lambda xml, ids: (
        *reconnect_bpmn_flow(xml, ids["flow"], target_id=ids["end"]), ids["flow"]),
    "layout": lambda xml, ids: (optimize_bpmn_layout(xml)[0], {}, None),
}
SOURCES = {
    "update_element": "canvas_facade_update", "add_element": "canvas_facade_add",
    "delete_element": "canvas_facade_delete", "connect_elements": "canvas_facade_connect",
    "reconnect_flow": "canvas_facade_reconnect", "layout": "canvas_facade_layout",
}


@pytest.mark.parametrize("fixture_name", ["purchase_layout.bpmn", "multibranch_layout.bpmn"])
@pytest.mark.parametrize("operation", sorted(EDITS))
def test_persisted_local_edit_changes_only_its_declared_delta(tenant, fixture_name, operation):
    model_id, saved = _seeded_model(fixture_name)
    before = saved["xml"]
    after_xml, change, element_id = EDITS[operation](before, _ids(before))
    versions_before = len(wd.list_bpmn_versions(model_id))

    with bind_turn_writes({model_id: saved["version_id"]}):
        written = wd.update_bpmn_model(
            model_id, after_xml, change_summary=f"L5 {operation}", source=SOURCES[operation],
        )
    persisted = wd.get_bpmn_model(model_id)

    assert written is not None and persisted is not None
    assert len(wd.list_bpmn_versions(model_id)) == versions_before + 1
    # The diff is taken on what was read back, after the write policy ran.
    assert_local_edit_integrity(
        before_xml=before, after_xml=persisted["xml"], operation=operation,
        change=change, element_id=element_id,
    )


def test_stale_agent_turn_cannot_overwrite_a_newer_version(tenant):
    model_id, saved = _seeded_model("purchase_layout.bpmn")
    ids = _ids(saved["xml"])
    base = saved["version_id"]

    with bind_turn_writes({model_id: base}):
        first, _ = update_bpmn_element(saved["xml"], ids["task"], name="Written first")
        wd.update_bpmn_model(model_id, first, source="canvas_agent_update")
    with bind_turn_writes({model_id: base}):
        second, _ = update_bpmn_element(saved["xml"], ids["other_task"], name="Written second")
        with pytest.raises(BpmnVersionConflict):
            wd.update_bpmn_model(model_id, second, source="canvas_agent_update")

    persisted = wd.get_bpmn_model(model_id)["xml"]
    assert "Written first" in persisted and "Written second" not in persisted
    assert len(wd.list_bpmn_versions(model_id)) == 2


def test_concurrent_agent_writes_from_one_version_land_exactly_once(tenant):
    model_id, saved = _seeded_model("purchase_layout.bpmn")
    ids = _ids(saved["xml"])
    base = saved["version_id"]
    barrier = threading.Barrier(2)
    outcomes: dict[str, str] = {}

    def write(label: str, element_id: str) -> None:
        token = set_current_tenant_id(tenant)
        try:
            xml, _ = update_bpmn_element(saved["xml"], element_id, name=f"Concurrent {label}")
            with bind_turn_writes({model_id: base}):
                barrier.wait(timeout=10)
                try:
                    wd.update_bpmn_model(model_id, xml, source="canvas_agent_update")
                    outcomes[label] = "saved"
                except BpmnVersionConflict:
                    outcomes[label] = "conflict"
        finally:
            reset_current_tenant_id(token)

    threads = [threading.Thread(target=write, args=("A", ids["task"])),
               threading.Thread(target=write, args=("B", ids["other_task"]))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(outcomes.values()) == ["conflict", "saved"]
    winner = next(label for label, outcome in outcomes.items() if outcome == "saved")
    loser = "B" if winner == "A" else "A"
    persisted = wd.get_bpmn_model(model_id)["xml"]
    assert f"Concurrent {winner}" in persisted and f"Concurrent {loser}" not in persisted
    assert len(wd.list_bpmn_versions(model_id)) == 2
