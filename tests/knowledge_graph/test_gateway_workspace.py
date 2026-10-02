"""Gateway INV-9: `workspace_read` — snapshot operativo scoped (no I/O esterno)."""

from __future__ import annotations

import pytest

from backend import workspace_database
from backend.memory import gateway

_PROJECT = {"id": "project-1", "name": "Mappatura"}
_PROCESSES = [
    {"id": "proc-1", "project_id": "project-1", "name": "Acquisti"},
    {"id": "proc-2", "project_id": "project-1", "name": "Budget"},
]
_SOURCES = [
    {"id": "src-1", "project_id": "project-1", "process_id": "proc-1", "name": "Intervista CFO"},
    {"id": "src-2", "project_id": "project-1", "process_id": None, "name": "Kickoff deck"},
]
_DECISIONS = [
    {"id": "dec-1", "project_id": "project-1", "process_id": "proc-2", "title": "Soglia budget"},
]


@pytest.fixture(autouse=True)
def _wire(monkeypatch):
    monkeypatch.setattr(
        workspace_database, "get_project",
        lambda pid: _PROJECT if pid == "project-1" else None,
    )
    monkeypatch.setattr(workspace_database, "list_project_processes", lambda pid: list(_PROCESSES))
    monkeypatch.setattr(workspace_database, "list_project_sources", lambda pid: list(_SOURCES))
    monkeypatch.setattr(workspace_database, "list_project_decisions", lambda pid: list(_DECISIONS))


def test_unknown_project_is_not_found():
    result = gateway.workspace_read(project_id="ghost")
    assert result == {"status": "not_found", "project": None}


def test_full_snapshot_without_process_filter():
    result = gateway.workspace_read(project_id="project-1")
    assert result["status"] == "ok"
    assert result["project"] == _PROJECT
    assert {p["id"] for p in result["processes"]} == {"proc-1", "proc-2"}
    assert {s["id"] for s in result["sources"]} == {"src-1", "src-2"}
    assert {d["id"] for d in result["decisions"]} == {"dec-1"}


def test_process_filter_scopes_processes_and_linked_rows():
    result = gateway.workspace_read(project_id="project-1", process_ids=["proc-1"])
    assert [p["id"] for p in result["processes"]] == ["proc-1"]
    # src-1 (proc-1) + src-2 (project-level, process_id None) restano; dec-1 (proc-2) esce
    assert {s["id"] for s in result["sources"]} == {"src-1", "src-2"}
    assert result["decisions"] == []


def test_include_limits_sections():
    result = gateway.workspace_read(project_id="project-1", include=("processes",))
    assert "processes" in result
    assert "sources" not in result
    assert "decisions" not in result
