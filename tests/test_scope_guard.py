"""G3 — enforcement runtime dello scope di progetto.

Il project_id dei tool project/process e' un argomento deciso dall'LLM. Dentro
un agent run vincolato deve combaciare con lo scope autorizzato del thread.
"""

from __future__ import annotations

import pytest

from backend.agents.scope_guard import (
    ScopeViolation,
    active_scope,
    assert_project_in_scope,
    bind_active_scope,
)
from backend.schemas.chat import (
    ConsultantChatScope,
    ProcessChatScope,
    ProjectChatScope,
)


def test_no_bound_scope_is_noop():
    # worker / test / cutover: nessun run agent -> il guard non blocca nulla
    assert active_scope() is None
    assert_project_in_scope("proj-qualsiasi")
    assert_project_in_scope(None)


def test_project_scope_matches_and_rejects():
    with bind_active_scope(ProjectChatScope(type="project", project_id="proj-1")):
        assert_project_in_scope("proj-1")  # ok
        with pytest.raises(ScopeViolation):
            assert_project_in_scope("proj-2")


def test_process_scope_uses_project_id():
    with bind_active_scope(
        ProcessChatScope(type="process", project_id="p9", process_id="pr1")
    ):
        assert_project_in_scope("p9")
        with pytest.raises(ScopeViolation):
            assert_project_in_scope("altro")


def test_consultant_scope_forbids_any_project():
    with bind_active_scope(ConsultantChatScope(type="consultant")):
        assert_project_in_scope(None)  # ok: nessun progetto
        with pytest.raises(ScopeViolation):
            assert_project_in_scope("proj-1")


def test_context_var_is_reset_after_block():
    with bind_active_scope(ProjectChatScope(type="project", project_id="x")):
        assert active_scope() is not None
    assert active_scope() is None


def test_nested_bind_restores_outer():
    outer = ProjectChatScope(type="project", project_id="outer")
    inner = ProjectChatScope(type="project", project_id="inner")
    with bind_active_scope(outer):
        with bind_active_scope(inner):
            assert_project_in_scope("inner")
        assert_project_in_scope("outer")


# --- i tool di scrittura appena bindati agli scope -------------------------
#
# Bindare `update_workspace_project` e `update_workspace_process` ha dato agli
# agenti la scrittura sul record. Il `project_id` / `process_id` resta pero' un
# argomento scelto dal modello, quindi un'injection in un documento caricato
# potrebbe puntarlo a un altro progetto dello stesso tenant: il filtro tenant
# del database non se ne accorgerebbe. I due tool passano dal guard prima di
# scrivere.


def test_update_workspace_project_refuses_a_project_outside_the_scope():
    from backend.toolsets.workspace import update_workspace_project

    with bind_active_scope(ProjectChatScope(type="project", project_id="proj-1")):
        with pytest.raises(ScopeViolation):
            update_workspace_project.invoke(
                {"project_id": "proj-di-un-altro-cliente", "objective": "irrilevante"}
            )


def test_update_workspace_process_refuses_a_process_of_another_project(monkeypatch):
    """Il processo non porta lo scope con se': si risale al progetto che lo possiede."""
    from backend.toolsets import workspace as workspace_tools

    monkeypatch.setattr(
        workspace_tools.workspace_database,
        "get_process",
        lambda process_id: {"id": process_id, "project_id": "proj-2", "name": "Acquisti"},
    )

    def _must_not_run(**kwargs):
        raise AssertionError("update_process non deve essere raggiunta fuori scope")

    monkeypatch.setattr(workspace_tools.workspace_database, "update_process", _must_not_run)

    with bind_active_scope(ProjectChatScope(type="project", project_id="proj-1")):
        with pytest.raises(ScopeViolation):
            workspace_tools.update_workspace_process.invoke(
                {"process_id": "pr-99", "status": "Validato"}
            )


def test_update_workspace_process_allows_a_process_of_the_active_project(monkeypatch):
    from backend.toolsets import workspace as workspace_tools

    monkeypatch.setattr(
        workspace_tools.workspace_database,
        "get_process",
        lambda process_id: {"id": process_id, "project_id": "proj-1", "name": "Acquisti"},
    )
    monkeypatch.setattr(
        workspace_tools.workspace_database,
        "update_process",
        lambda **kwargs: {
            "id": kwargs["process_id"],
            "project_id": "proj-1",
            "bpmn_model_id": "m-1",
            "name": "Acquisti",
            "stage": "AS-IS",
            "status": "Validato",
            "owner": "Da assegnare",
            "readiness": 40,
        },
    )

    with bind_active_scope(ProjectChatScope(type="project", project_id="proj-1")):
        result = workspace_tools.update_workspace_process.invoke(
            {"process_id": "pr-1", "status": "Validato"}
        )

    assert "Validato" in result
