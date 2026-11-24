from pathlib import Path

import pytest

from scripts.benchmark_canvas_patch import benchmark


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


@pytest.mark.parametrize(
    "name",
    ["purchase_layout.bpmn", "multibranch_layout.bpmn", "omg_issue_list.bpmn"],
)
def test_local_rename_preserves_bpmn_semantics_with_a_smaller_prompt(name):
    result = benchmark(FIXTURES / name, repeat=1)

    assert result["structure_preserved"]
    assert result["untouched_semantics_preserved"]
    assert result["scope_tokens_patch"] < result["scope_tokens_full"]
