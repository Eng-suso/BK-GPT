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
