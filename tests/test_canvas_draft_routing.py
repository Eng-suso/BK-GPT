"""Quando il canvas disegna con un comando e quando serve ancora un agente.

Il rischio di un percorso veloce e' che si prenda anche il lavoro che non gli
appartiene: una modifica parziale rigenerata da capo cancella il lavoro intorno,
e un'anteprima in attesa sostituita da una rigenerazione butta via cio' che
l'utente stava per applicare. Qui si verifica il confine, che e' la parte che
non si vede.
"""

from __future__ import annotations

import pytest

from backend.graphs.canvas_edit.graph import (
    draft_command_applies,
    generate_canvas_draft,
    selected_canvas_route,
)
from backend.workspace_services.bpmn_draft import BpmnDraftResult


PLANNED_SNAPSHOT = {
    "bpmn_semantic_model": {"flowNodes": [{"id": "Task_1"}]},
    "sources": [{"id": "s1"}],
}


def _state(**overrides) -> dict:
    base = {
        "canvas_route": "construction",
        "canvas_construction_kind": "full_from_plan",
        "process_id": "p1",
        "process_snapshot": PLANNED_SNAPSHOT,
    }
    base.update(overrides)
    return base


def test_full_generation_from_the_plan_runs_as_a_command():
    assert draft_command_applies(_state()) is True
    assert selected_canvas_route(_state()) == "draft_command"


def test_a_partial_change_still_needs_the_agent():
    """Rigenerare tutto per cambiare un pezzo cancella il lavoro intorno."""
    state = _state(canvas_construction_kind="partial_change")

    assert draft_command_applies(state) is False
    assert selected_canvas_route(state) == "construction"


def test_a_description_written_by_the_user_still_needs_the_agent():
    state = _state(canvas_construction_kind="from_user_description")

    assert draft_command_applies(state) is False


def test_a_pending_preview_is_applied_not_regenerated():
    state = _state(canvas_preview_xml="<definitions/>")

    assert draft_command_applies(state) is False


def test_emptying_the_canvas_is_not_a_draft():
    state = _state(canvas_expected_outcome="empty_canvas")

    assert draft_command_applies(state) is False


def test_other_routes_are_untouched():
    for route in ("direct", "patch_edit", "layout", "validation", "clarification"):
        assert selected_canvas_route(_state(canvas_route=route)) == route


def test_a_process_without_knowledge_does_not_reach_the_command():
    """Senza piano ne' fonti non c'e' niente da compilare: decide l'agente."""
    state = _state(process_snapshot={})

    assert draft_command_applies(state) is False


def test_the_node_reports_a_technical_failure_as_technical(monkeypatch):
    """Un guasto non si racconta come una lacuna di evidenza, e non aspetta l'utente."""
    from backend.workspace_services import bpmn_draft

    monkeypatch.setattr(
        bpmn_draft,
        "generate_verified_bpmn_draft",
        lambda *args, **kwargs: BpmnDraftResult(
            status="failed",
            process_id="p1",
            bpmn_model_id="b1",
            reason="Il canvas non e' stato salvato.",
            issues=["OperationalError: connection timeout"],
            metrics={"total_ms": 12, "llm_calls": 0},
        ),
    )

    result = generate_canvas_draft(_state())

    assert result["canvas_run_status"] == "failed"
    assert "connection timeout" in result["messages"][0].content
    assert result["canvas_draft_metrics"]["llm_calls"] == 0


def test_the_node_hands_back_the_drawing_and_the_open_points(monkeypatch):
    from backend.workspace_services import bpmn_draft

    monkeypatch.setattr(
        bpmn_draft,
        "generate_verified_bpmn_draft",
        lambda *args, **kwargs: BpmnDraftResult(
            status="drafted",
            process_id="p1",
            bpmn_model_id="b1",
            snapshot_label="V4",
            xml="<definitions/>",
            pending_verification=["Chi regolarizza l'ordine urgente?"],
            reason="Bozza costruita sul piano V4 del processo.",
            metrics={"total_ms": 340, "llm_calls": 0},
        ),
    )

    result = generate_canvas_draft(_state())

    assert result["canvas_run_status"] == "done"
    assert result["saved_bpmn_xml"] == "<definitions/>"
    assert "V4" in result["messages"][0].content
    assert "ordine urgente" in result["messages"][0].content
    assert result["validation_report"]["warnings"] == ["Chi regolarizza l'ordine urgente?"]


def test_a_canvas_without_a_process_is_refused_explicitly():
    result = generate_canvas_draft(_state(process_id=None))

    assert result["canvas_run_status"] == "failed"
    assert "processo" in result["messages"][0].content


@pytest.mark.parametrize("kind", [None, "full_from_plan"])
def test_a_missing_kind_defaults_to_the_command(kind):
    """Un router che non dichiara il tipo non deve far ripartire la catena lenta."""
    assert draft_command_applies(_state(canvas_construction_kind=kind)) is True
