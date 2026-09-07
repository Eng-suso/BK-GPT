"""Il progresso mostrato al consulente e' deterministico, semantico e non ripetitivo."""

import pytest

from backend.services.agent_progress import (
    ALL_PHASES,
    DRAFTING,
    RECALLING,
    READING_SOURCES,
    ProgressNarrator,
    detail_from_tool_args,
    phase_for_node,
    phase_for_tool,
)


def test_every_phase_label_is_written_for_a_consultant():
    for phase in ALL_PHASES:
        words = phase.label.split()
        assert 1 <= len(words) <= 6, phase.label
        assert phase.label[0].isupper(), phase.label
        lowered = phase.label.lower()
        for internal in ("agent", "node", "subgraph", "router", "tool", "xml", "bpmn", "_"):
            assert internal not in lowered, phase.label


def test_phase_ids_are_unique():
    ids = [phase.id for phase in ALL_PHASES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    ("tool_name", "expected_phase"),
    [
        ("retrieve_consulting_context", "recalling"),
        ("retrieve_consulting_graph_context", "recalling"),
        ("remember_consultant_fact", "saving_memory"),
        ("manage_consultant_playbook", "saving_memory"),
        ("web_research", "researching"),
        ("list_workspace_project_sources", "reading_sources"),
        ("add_workspace_source", "reading_sources"),
        ("list_workspace_projects", "reading_workspace"),
        ("create_workspace_project", "recording"),
        ("update_workspace_process", "recording"),
        ("prepare_delegation_payload", "handing_over"),
    ],
)
def test_known_tools_map_to_a_phase(tool_name, expected_phase):
    phase = phase_for_tool(tool_name)
    assert phase is not None
    assert phase.id == expected_phase


def test_an_unregistered_tool_still_finds_a_phase_by_family():
    # Un tool nuovo non deve restare muto solo perche' nessuno l'ha registrato.
    assert phase_for_tool("search_client_playbooks") is not None
    assert phase_for_tool("update_client_scorecard").id == "recording"


def test_an_unrecognisable_node_says_nothing_rather_than_leaking_its_name():
    assert phase_for_node("consult_macro_agent") is None
    assert phase_for_node("") is None
    assert phase_for_node(None) is None


def test_a_node_with_a_known_stage_maps_to_that_stage():
    assert phase_for_node("canvas_validation_agent").id == "checking"
    assert phase_for_node("canvas_drawing_agent").id == "drawing"
    assert phase_for_node("ask_canvas_clarification").id == "asking"


def test_detail_uses_domain_words_and_refuses_identifiers_and_payloads():
    assert detail_from_tool_args({"name": "Intervista Laura"}) == "Intervista Laura"
    assert detail_from_tool_args({"query": "  tempi   di   ciclo "}) == "tempi di ciclo"
    assert detail_from_tool_args({"name": "3f2b8c1a-77aa-4b21-9e10-2f0c9d3f7c11"}) == ""
    assert detail_from_tool_args({"name": '{"rows": []}'}) == ""
    assert detail_from_tool_args({"project_id": "p-1"}) == ""
    assert detail_from_tool_args(None) == ""


def test_detail_is_trimmed_instead_of_flooding_the_line():
    detail = detail_from_tool_args({"title": "A" * 200})
    assert len(detail) <= 48
    assert detail.endswith("…")


def test_the_same_phase_is_announced_once_however_many_tools_it_takes():
    narrator = ProgressNarrator()

    assert narrator.enter_for_tool("retrieve_consulting_context", {})["phase"] == "recalling"
    assert narrator.enter_for_tool("retrieve_consulting_graph_context", {}) is None
    assert narrator.enter_for_tool("retrieve_project_context", {}) is None
    assert narrator.enter_for_tool("list_workspace_project_sources", {})["phase"] == "reading_sources"


def test_a_phase_can_come_back_later_in_the_turn():
    narrator = ProgressNarrator()

    narrator.enter(RECALLING)
    narrator.enter(READING_SOURCES)

    again = narrator.enter(RECALLING)
    assert again is not None
    assert again["phase"] == "recalling"


def test_each_update_carries_the_time_the_consultant_has_been_waiting():
    ticks = iter([0.0, 2.5, 9.0])
    narrator = ProgressNarrator(clock=lambda: next(ticks))

    first = narrator.enter(RECALLING)
    second = narrator.enter(DRAFTING)

    assert first["elapsed_ms"] == 2500
    assert second["elapsed_ms"] == 9000


def test_activity_ids_are_stable_and_unique_per_update():
    narrator = ProgressNarrator()

    first = narrator.enter(RECALLING)
    second = narrator.enter(DRAFTING)

    assert first["activity_id"] != second["activity_id"]
    assert first["activity_id"].endswith("recalling")
