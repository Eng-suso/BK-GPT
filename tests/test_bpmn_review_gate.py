from backend.bpmn import build_bpmn_semantic_model
from backend.process_understanding import ProcessActor, ProcessStep, ProcessUnderstanding
from backend.workspace_database import review_approval_blockers


def _sound_model_json() -> dict:
    process = ProcessUnderstanding(
        title="P",
        actors=[ProcessActor(id="A", label="A", kind="team")],
        steps=[ProcessStep(id="T", label="T", actor_ids=["A"])],
        sequence=["T"],
    )
    return build_bpmn_semantic_model(process_id="P", process_name="P", process=process).model_dump(mode="json")


def test_no_blockers_when_quality_ready_and_model_sound():
    assert review_approval_blockers({"approval_recommendation": "ready_to_generate"}, _sound_model_json()) == []


def test_quality_not_ready_is_a_blocker():
    blockers = review_approval_blockers({"approval_recommendation": "needs_auto_revision"}, _sound_model_json())
    assert any("ready_to_generate" in b for b in blockers)


def test_unsound_model_is_a_blocker_even_when_quality_is_ready():
    model = _sound_model_json()
    model["sequenceFlows"].append(
        {"id": "F_extra", "sourceRef": model["flowNodes"][1]["id"], "targetRef": "ghost"}
    )
    model["flowNodes"].append({"id": "ghost", "type": "task", "name": "ghost"})
    blockers = review_approval_blockers({"approval_recommendation": "ready_to_generate"}, model)
    assert any("control-flow" in b for b in blockers)


def test_missing_model_does_not_crash():
    assert review_approval_blockers(None, None) == []


def test_the_plan_reads_like_a_consultant_wrote_it():
    """The plan is what the consultant shows the client, not a debug dump.

    From real use: the brief printed "Topologia BPMN proposta", "Pool Art Proc:
    expanded" and "evento_avvio -> raccogliere_richiesta". The contracts already
    forbid the agent from talking that way; the artifact itself was doing it.
    """
    from backend.process_understanding import (
        ProcessFlowEdge,
        ProcessParticipant,
        render_process_review,
    )

    process = ProcessUnderstanding(
        title="Gestione richieste",
        scope="Processo dimostrativo con una sola pool.",
        actors=[ProcessActor(id="Ufficio", label="Ufficio richieste", kind="team")],
        steps=[
            ProcessStep(id="raccogliere_richiesta", label="Raccogliere la richiesta", actor_ids=["Ufficio"]),
            ProcessStep(id="gestire_richiesta", label="Gestire la richiesta", actor_ids=["Ufficio"]),
        ],
        sequence=["raccogliere_richiesta", "gestire_richiesta"],
        participants=[
            ProcessParticipant(
                id="Ufficio", label="Ufficio richieste", kind="organization", bpmn_container="pool"
            ),
            ProcessParticipant(
                id="Cliente", label="Cliente", kind="organization", bpmn_container="black_box"
            ),
        ],
        flow_edges=[
            ProcessFlowEdge(
                id="e1",
                source_id="raccogliere_richiesta",
                target_id="gestire_richiesta",
                label="Dopo la raccolta si procede alla gestione.",
            )
        ],
    )

    brief = render_process_review(process)

    for jargon in (
        "Topologia BPMN",
        "bpmn_container",
        "expanded",
        "black_box",
        "Pool ",
        "Lane ",
        "raccogliere_richiesta ->",
        "needs_user_clarification",
        "needs_auto_revision",
        "ready_to_generate",
    ):
        assert jargon not in brief, f"il piano non deve contenere {jargon!r}:\n{brief}"

    # I passaggi si leggono per etichetta, non per id.
    assert '"Raccogliere la richiesta"' in brief
    assert '"Gestire la richiesta"' in brief
    # Un interlocutore esterno si spiega, non si etichetta con il contenitore BPMN.
    assert "interlocutore esterno" in brief
