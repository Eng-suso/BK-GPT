"""Le traiettorie attese si reggono sul prodotto, non su un'opinione.

Tre cose che si possono verificare senza modello:

1. la regola citata sta ancora, alla lettera, nel file che la impone: se il
   prompt cambia, la traiettoria va riletta;
2. ogni tool nominato esiste fra quelli che gli agenti hanno davvero: un nome
   sbagliato renderebbe una regola "vietato" sempre rispettata;
3. ogni valore ammesso per un argomento e' uno che il tool dichiara: un
   `operation="provenence"` scritto male non verrebbe mai chiamato, e la regola
   "deve chiamare" fallirebbe per un refuso.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.evals.trajectory_metrics import load_trajectories

ROOT = Path(__file__).resolve().parents[3]
TRAJECTORIES = load_trajectories(ROOT / "tests" / "evals" / "l3_trajectory" / "trajectories.json")
_SPACES = re.compile(r"\s+")


def _flat(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def _agent_tools() -> dict:
    from backend.graphs.canvas_edit.tools import canvas_macro_tools, construction_tools, patch_edit_tools
    from backend.graphs.process.subgraphs.discovery.tools import discovery_tools
    from backend.graphs.process.subgraphs.evidence.tools import evidence_tools
    from backend.graphs.process.subgraphs.modeling.tools import modeling_tools
    from backend.graphs.process.tools import process_tools

    lists = (process_tools, discovery_tools, evidence_tools, modeling_tools)
    canvas = (canvas_macro_tools, patch_edit_tools, construction_tools)
    return {item.name: item for group in (*lists, *canvas) for item in group}


TOOLS = _agent_tools()


@pytest.mark.parametrize("expected", TRAJECTORIES, ids=lambda item: item.id)
def test_the_rule_is_still_written_in_the_product(expected):
    source = (ROOT / expected.rule_source).read_text(encoding="utf-8")

    assert _flat(expected.rule) in _flat(source), (
        f"{expected.id}: la regola non e' piu' in {expected.rule_source}, la traiettoria va riletta"
    )


@pytest.mark.parametrize("expected", TRAJECTORIES, ids=lambda item: item.id)
def test_every_named_tool_exists_and_every_allowed_value_is_declared(expected):
    for rule in [*expected.must_call, *expected.must_not_call]:
        assert rule.tool in TOOLS, f"{expected.id}: nessun agente ha il tool {rule.tool}"
        schema = TOOLS[rule.tool].args_schema.model_json_schema()
        for name, allowed in rule.args.items():
            description = schema["properties"][name].get("description", "")
            for value in allowed:
                assert value in description, f"{expected.id}: {rule.tool} non dichiara {name}={value}"


def test_every_trajectory_has_something_to_check():
    for expected in TRAJECTORIES:
        assert expected.must_call or expected.must_not_call, expected.id
        assert expected.max_tool_calls > 0, expected.id
