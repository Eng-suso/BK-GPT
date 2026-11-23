"""Import di scenari Prosimos: parita' con il pannello e tolleranza (B1).

I casi stanno in ``tests/fixtures/simulation/prosimos_import_cases.json`` e
valgono anche per ``prosimosJson.ts``. Si rigenerano con
``uv run python scripts/generate_prosimos_import_cases.py`` dopo un cambio
voluto: il test del frontend dice allora se il pannello segue.
"""

import json
from pathlib import Path

import pytest

from backend.schemas.simulation import ScenarioTemplateResponse
from backend.simulation.prosimos_import import ProsimosImportError, import_prosimos_json

FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "simulation" / "prosimos_import_cases.json").read_text(encoding="utf-8")
)
TEMPLATE = ScenarioTemplateResponse.model_validate(FIXTURE["template"])


@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["name"])
def test_the_server_imports_like_the_panel(case):
    if "error" in case:
        with pytest.raises(ProsimosImportError) as exc:
            import_prosimos_json(case["source"], case["current"], TEMPLATE, case["mapping"])
        assert str(exc.value) == case["error"]
        return
    result = import_prosimos_json(case["source"], case["current"], TEMPLATE, case["mapping"])
    assert result.draft == case["expected"]["draft"]
    assert result.warnings == case["expected"]["warnings"]


def test_every_tolerance_rule_has_a_case():
    kinds = {w["kind"] for case in FIXTURE["cases"] for w in case.get("expected", {}).get("warnings", [])}
    assert kinds == {"ignoredField", "ignoredGateway", "notImported", "normalizedProbabilities"}


def _simod_case() -> dict:
    return next(c for c in FIXTURE["cases"] if c["name"].startswith("scenario SIMOD"))


def test_simod_metadata_is_ignored_silently():
    targets = {w["target"] for w in _simod_case()["expected"]["warnings"]}
    assert not targets & {"process_model", "model_type", "granule_size"}


def test_microseconds_become_milliseconds():
    always = next(c for c in _simod_case()["expected"]["draft"]["calendars"] if c["id"] == "always")
    assert always["periods"][0]["end"] == "23:59:59.999"


def test_a_template_is_required():
    with pytest.raises(ProsimosImportError, match="BPMN"):
        import_prosimos_json({}, None, None)
