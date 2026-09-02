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
