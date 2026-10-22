"""La richiesta di run di una bozza del workspace, come la costruisce il pannello.

I casi sono gli stessi di ``frontend/.../draftRequest.test.ts``: il corpo
atteso lo scrive la traduzione TypeScript, qui lo deve ritrovare quella Python.
"""

import json
from pathlib import Path

import pytest

from backend.schemas.simulation import ScenarioTemplateResponse
from backend.simulation.draft_request import DraftTranslationError, expected_request_body

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "simulation" / "draft_request_cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_the_backend_builds_the_same_request_as_the_panel(case):
    template = ScenarioTemplateResponse.model_validate(case["template"])

    body = expected_request_body(case["draft"], case["scenarioName"], template)

    assert body == case["expected"]


def test_the_stored_draft_is_not_modified():
    case = CASES[1]
    stored = json.loads(json.dumps(case["draft"]))

    expected_request_body(stored, case["scenarioName"], ScenarioTemplateResponse.model_validate(case["template"]))

    assert stored == case["draft"]


def test_a_distribution_the_panel_does_not_know_cannot_be_verified():
    template = ScenarioTemplateResponse.model_validate({"tasks": [{"element_id": "T1", "name": "Verifica", "type": "task"}], "gateways": []})
    draft = {"tasks": {"T1": {"meanMinutes": 5, "distribution": "weibull", "resourceId": ""}}}

    with pytest.raises(DraftTranslationError):
        expected_request_body(draft, "AS-IS", template)
