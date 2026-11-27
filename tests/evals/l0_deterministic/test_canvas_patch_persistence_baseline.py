"""Measure a canvas patch through the isolated test Postgres stack.

The report printed with ``pytest -s`` excludes LLM and browser time. Each
successful patch must create exactly one version and survive a fresh DB read.
"""

from __future__ import annotations

import json
import statistics
import uuid
from pathlib import Path
from time import perf_counter

import pytest

from backend import workspace_database as wd
from backend.agents.run_context import bind_turn_writes
from backend.security import reset_current_tenant_id, set_current_tenant_id
from backend.workspace_services.bpmn_canvas_edit import (
    list_bpmn_elements,
    update_bpmn_element,
    validate_bpmn_xml,
)
from scripts.benchmark_canvas_patch import _semantic_tree, _structure


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.fixture()
def bpmn_model_id():
    token = set_current_tenant_id(f"t-canvas-perf-{uuid.uuid4().hex[:8]}")
    try:
        client = wd.create_client(name="Synthetic canvas benchmark")
        project = wd.create_project(client_id=client["id"], name="Benchmark")
        process = wd.create_process(project_id=project["id"], name="Benchmark process")
        yield process["bpmn_model_id"]
    finally:
        reset_current_tenant_id(token)


@pytest.mark.parametrize(
    "fixture_name",
    ["purchase_layout.bpmn", "multibranch_layout.bpmn", "omg_issue_list.bpmn"],
)
def test_canvas_patch_persists_one_version_and_preserves_semantics(bpmn_model_id, fixture_name):
    source_xml = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    saved = wd.update_bpmn_model(bpmn_model_id, source_xml, source="canvas_benchmark_seed")
    assert saved is not None
    element = next(
        item for item in list_bpmn_elements(saved["xml"])
        if item["type"] in {"task", "userTask", "serviceTask", "manualTask"}
    )
    original_semantics = _semantic_tree(saved["xml"], element["id"])
    original_structure = _structure(saved["xml"])
    timings: list[float] = []

    with bind_turn_writes({bpmn_model_id: saved["version_id"]}):
        for index in range(3):
            before = wd.get_bpmn_model(bpmn_model_id)
            assert before is not None
            versions_before = len(wd.list_bpmn_versions(bpmn_model_id))
            patch_xml, _change = update_bpmn_element(
                before["xml"], element["id"], name=f"Benchmark rename {index}"
            )
            started = perf_counter()
            written = wd.update_bpmn_model(
                bpmn_model_id,
                patch_xml,
                change_summary="Synthetic rename benchmark",
                source="canvas_facade_update",
            )
            reloaded = wd.get_bpmn_model(bpmn_model_id)
            timings.append((perf_counter() - started) * 1000)
            assert written is not None and reloaded is not None
            assert reloaded["version_id"] == written["version_id"]
            assert len(wd.list_bpmn_versions(bpmn_model_id)) == versions_before + 1
            assert validate_bpmn_xml(reloaded["xml"])["valid"]
            assert _structure(reloaded["xml"]) == original_structure
            assert _semantic_tree(reloaded["xml"], element["id"]) == original_semantics

    print(json.dumps({
        "fixture": fixture_name,
        "patch_persist_read_ms_median": round(statistics.median(timings), 2),
        "repetitions": len(timings),
        "versions_per_patch": 1,
        "semantics_preserved": True,
    }))
