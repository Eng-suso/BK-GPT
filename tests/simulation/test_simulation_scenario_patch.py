"""SIM-14: la patch di uno scenario sulla bozza AS-IS.

I casi sono gli stessi del frontend (``scenarioPatch.test.ts``): le due
implementazioni devono dare la stessa bozza e gli stessi conflitti.
"""

import copy
import json
from pathlib import Path

import pytest

from backend.simulation.scenario_patch import apply_scenario_patch

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "simulation" / "scenario_patch_cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_patch_gives_the_same_draft_as_the_frontend(case):
    baseline = copy.deepcopy(case["baseline"])

    draft, conflicts = apply_scenario_patch(baseline, case["patch"])

    assert draft == case["expected"]
    assert conflicts == case["conflicts"]
    # L'AS-IS resta com'era: lo scenario ne e' una copia.
    assert baseline == case["baseline"]


def test_a_set_value_is_a_copy_not_shared_with_the_patch():
    ops = [{"op": "set", "path": ["sla"], "value": {"target": 2}}]

    draft, _ = apply_scenario_patch({}, ops)
    draft["sla"]["target"] = 5

    assert ops[0]["value"] == {"target": 2}
