"""Fedeltà dell'import sugli scenari del dataset di valutazione (B1).

Dataset fuori dal repo (``DELIR_SIM_EVAL_DIR``, la cartella con ``inputs/``):
scenari Prosimos scoperti da SIMOD su log reali e scenari sintetici con timer.
Per ognuno: import come la UI, bozza -> richiesta -> scenario compilato, poi
confronto con l'originale. Senza la variabile il test si salta.
"""

import json
import os
from pathlib import Path

import pytest

from backend.schemas.simulation import CreateSimulationRunRequest
from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
from backend.simulation.draft_request import expected_request_body
from backend.simulation.prosimos_import import import_prosimos_json
from backend.simulation.scenario_builder import build_prosimos_scenario, describe_scenario_template
from tests.simulation.eval.fidelity import differences

EVAL_DIR = os.environ.get("DELIR_SIM_EVAL_DIR")
SCENARIOS = sorted(Path(EVAL_DIR, "inputs").glob("*/*.json")) if EVAL_DIR else []

pytestmark = pytest.mark.skipif(not SCENARIOS, reason="DELIR_SIM_EVAL_DIR non impostata o senza inputs/*/*.json")


@pytest.mark.parametrize("scenario_path", SCENARIOS, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_an_imported_scenario_simulates_what_the_original_says(scenario_path):
    original = json.loads(scenario_path.read_text(encoding="utf-8"))
    source_xml = scenario_path.with_suffix(".bpmn").read_text(encoding="utf-8")
    bpmn = normalize_bpmn_for_prosimos(source_xml)
    template = describe_scenario_template(bpmn, source_bpmn_xml=source_xml)

    imported = import_prosimos_json(original, None, template)
    body = expected_request_body(imported.draft, scenario_path.stem, template)
    request = CreateSimulationRunRequest.model_validate({**body, "total_cases": 10})
    compiled = build_prosimos_scenario(bpmn_xml=bpmn, request=request).payload

    assert not {w["kind"] for w in imported.warnings} & {"notImported", "normalizedProbabilities"}
    assert differences(original, compiled) == {}
