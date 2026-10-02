"""Chiedi approvazione: una scrittura sul workspace parte solo dopo il si' del consulente."""

from __future__ import annotations

import json
import uuid

import pytest

from backend.agents.chat_mode import bind_active_mode
from backend.agents.run_context import bind_active_thread
from backend.security import reset_current_tenant_id, set_current_tenant_id
from backend.settings import settings

pytestmark = pytest.mark.skipif(
    not settings.workspace_database_url, reason="serve WORKSPACE_DATABASE_URL"
)


@pytest.fixture()
def tenant():
    token = set_current_tenant_id(f"approval-{uuid.uuid4().hex[:10]}")
    try:
        yield
    finally:
        reset_current_tenant_id(token)


def _result(raw: str) -> dict:
    return json.loads(raw[raw.index("{"):])


def _client_names() -> set[str]:
    from backend import workspace_database

    return {client["name"] for client in workspace_database.list_clients()}


def test_a_proposed_setup_is_created_only_after_confirmation(tenant):
    from backend.toolsets.workspace import confirm_workspace_write, create_initial_workspace_setup

    thread = f"thread-{uuid.uuid4().hex[:8]}"
    with bind_active_mode("plan"), bind_active_thread(thread):
        proposed = _result(
            create_initial_workspace_setup.invoke(
                {
                    "client_name": "Barilla S.p.A.",
                    "project_name": "Ottimizzazione processi HR",
                    "reason": "Il consulente ha chiesto il progetto HR per Barilla.",
                }
            )
        )
        assert proposed["status"] == "awaiting_confirmation"
        assert "Barilla S.p.A." in proposed["summary"]
        assert "Barilla S.p.A." not in _client_names()

        confirmed = confirm_workspace_write.invoke({"operation": "confirm"})
        assert "Barilla S.p.A." in _client_names()
        assert "Ottimizzazione processi HR" in confirmed

        # Una seconda conferma non riesegue la stessa scrittura.
        again = _result(confirm_workspace_write.invoke({"operation": "confirm"}))
        assert again["status"] in {"not_found", "noop"}


def test_a_cancelled_proposal_creates_nothing(tenant):
    from backend.toolsets.workspace import confirm_workspace_write, manage_client_record

    thread = f"thread-{uuid.uuid4().hex[:8]}"
    with bind_active_mode("plan"), bind_active_thread(thread):
        proposed = _result(manage_client_record.invoke({"operation": "create", "name": "Esaote"}))
        assert proposed["status"] == "awaiting_confirmation"
        cancelled = _result(confirm_workspace_write.invoke({"operation": "cancel"}))
        assert cancelled["status"] == "cancelled"
    assert "Esaote" not in _client_names()


def test_manual_refuses_and_auto_writes(tenant):
    from backend.toolsets.workspace import manage_client_record

    with bind_active_mode("conversation"):
        refused = _result(manage_client_record.invoke({"operation": "create", "name": "Manuale Srl"}))
    assert refused["status"] == "blocked"
    assert "Manuale" in refused["summary"]
    assert "Manuale Srl" not in _client_names()

    with bind_active_mode("agent"):
        created = _result(manage_client_record.invoke({"operation": "create", "name": "Auto Srl"}))
    assert created["status"] == "created"
    assert "Auto Srl" in _client_names()


def test_two_proposals_in_one_turn_are_both_approved_by_one_yes(tenant):
    from backend.toolsets.workspace import confirm_workspace_write, manage_client_record

    thread = f"thread-{uuid.uuid4().hex[:8]}"
    with bind_active_mode("plan"), bind_active_thread(thread):
        manage_client_record.invoke({"operation": "create", "name": "Cliente Uno"})
        second = _result(manage_client_record.invoke({"operation": "create", "name": "Cliente Due"}))
        assert "Cliente Uno" in second["summary"] and "Cliente Due" in second["summary"]
        confirm_workspace_write.invoke({"operation": "confirm"})
    assert {"Cliente Uno", "Cliente Due"} <= _client_names()


def test_a_yes_in_manual_keeps_the_proposal_for_later(tenant):
    from backend.toolsets.workspace import confirm_workspace_write, manage_client_record

    thread = f"thread-{uuid.uuid4().hex[:8]}"
    with bind_active_thread(thread):
        with bind_active_mode("plan"):
            manage_client_record.invoke({"operation": "create", "name": "Rimandato Srl"})
        with bind_active_mode("conversation"):
            refused = _result(confirm_workspace_write.invoke({"operation": "confirm"}))
        assert refused["status"] == "blocked"
        assert "Rimandato Srl" not in _client_names()
        with bind_active_mode("agent"):
            confirm_workspace_write.invoke({"operation": "confirm"})
    assert "Rimandato Srl" in _client_names()


def test_a_workspace_proposal_does_not_replace_another_pending_confirmation(tenant):
    from backend.memory import pending_actions
    from backend.toolsets.workspace import manage_client_record

    thread = f"thread-{uuid.uuid4().hex[:8]}"
    pending_actions.propose(
        consultant_id=settings.default_consultant_id,
        thread_id=thread,
        action="forget_memory",
        params={"targets": []},
        preview="dimenticare una preferenza",
    )
    with bind_active_mode("plan"), bind_active_thread(thread):
        blocked = _result(manage_client_record.invoke({"operation": "create", "name": "Concorrente Srl"}))
    assert blocked["status"] == "blocked"
    still_open = pending_actions.open_action(consultant_id=settings.default_consultant_id, thread_id=thread)
    assert still_open["action"] == "forget_memory"


def test_a_write_that_breaks_after_the_yes_is_reported_and_the_others_still_happen(tenant, monkeypatch):
    from backend.memory import pending_actions
    from backend.toolsets import workspace as workspace_tools

    thread = f"thread-{uuid.uuid4().hex[:8]}"
    with bind_active_mode("plan"), bind_active_thread(thread):
        workspace_tools.manage_client_record.invoke({"operation": "create", "name": "Rotto Srl"})
        workspace_tools.manage_client_record.invoke({"operation": "create", "name": "Sano Srl"})

        real = workspace_tools._GATED_WRITE_TOOLS["manage_client_record"]

        class _BreaksOnFirst:
            calls = 0

            def invoke(self, arguments):
                _BreaksOnFirst.calls += 1
                if _BreaksOnFirst.calls == 1:
                    raise RuntimeError("database giu'")
                return real.invoke(arguments)

        monkeypatch.setitem(workspace_tools._GATED_WRITE_TOOLS, "manage_client_record", _BreaksOnFirst())
        outcome = workspace_tools.confirm_workspace_write.invoke({"operation": "confirm"})

    assert "Non eseguita" in outcome
    assert "Rotto Srl" not in _client_names()
    assert "Sano Srl" in _client_names()
    # la proposta e' consumata: un secondo si' non la riesegue
    assert pending_actions.open_action(
        consultant_id=settings.default_consultant_id, thread_id=thread
    ) is None
