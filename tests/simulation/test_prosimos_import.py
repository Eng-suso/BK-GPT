"""B1a: uno scenario Prosimos (anche prodotto da SIMOD) entra nell'IR senza perdere nulla.

Meta del piano (docs/vpt/PLAN.md): i 19 scenari del dataset Extraneous Activity
Delays si importano e, ricompilati, ritrovano gli stessi parametri. Ogni cosa che
l'IR non porta deve comparire nel report d'import, mai sparire in silenzio.
Nessuna rete, nessun database: girano con ``--noconftest``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from backend.simulation.ir.compile import compile_for_prosimos
from backend.simulation.ir.from_prosimos import ProsimosImportError, import_prosimos

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "datasets" / "extraneous-delays" / "inputs"
SCENARIOS = sorted(INPUTS.glob("*/*.json"))


def _pair(path: Path) -> tuple[dict, str]:
    return json.loads(path.read_text(encoding="utf-8")), path.with_suffix(
        ".bpmn"
    ).read_text(encoding="utf-8")


def _close(a: float, b: float) -> bool:
    return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)


def _params(entry: dict) -> tuple[str, list[float]]:
    return entry["distribution_name"], [
        float(p["value"]) for p in entry["distribution_params"]
    ]


def _same_distribution(a: dict, b: dict) -> bool:
    name_a, values_a = _params(a)
    name_b, values_b = _params(b)
    names = {"fix": "fix", "fixed": "fix"}
    return (
        names.get(name_a, name_a) == names.get(name_b, name_b)
        and len(values_a) == len(values_b)
        and all(_close(x, y) for x, y in zip(values_a, values_b, strict=True))
    )


def _periods(periods: list[dict]) -> list[tuple]:
    return sorted((p["from"], p["to"], p["beginTime"], p["endTime"]) for p in periods)


def test_the_dataset_has_the_nineteen_scenarios_of_the_plan() -> None:
    assert len(SCENARIOS) == 19


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_a_scenario_round_trips_through_the_ir(path: Path) -> None:
    source, bpmn = _pair(path)
    result = import_prosimos(source, bpmn)
    compiled = compile_for_prosimos(result.model)

    # Durate: ogni coppia attivita'-risorsa con la stessa distribuzione.
    expected = {
        (task["task_id"], resource["resource_id"]): resource
        for task in source["task_resource_distribution"]
        for resource in task["resources"]
    }
    got = {
        (task["task_id"], resource["resource_id"]): resource
        for task in compiled["task_resource_distribution"]
        for resource in task["resources"]
    }
    assert got.keys() == expected.keys()
    assert [
        key for key in expected if not _same_distribution(expected[key], got[key])
    ] == []

    # Arrivi: distribuzione e calendario.
    assert _same_distribution(
        source["arrival_time_distribution"], compiled["arrival_time_distribution"]
    )
    assert _periods(compiled["arrival_time_calendar"]) == _periods(
        source["arrival_time_calendar"]
    )

    # Risorse: organico, costo, calendario; e i calendari che le risorse usano.
    def resources(payload: dict) -> dict:
        return {
            r["id"]: (int(r["amount"]), float(r["cost_per_hour"]), r["calendar"])
            for p in payload["resource_profiles"]
            for r in p["resource_list"]
        }

    assert resources(compiled) == resources(source)
    used = {
        r["calendar"] for p in source["resource_profiles"] for r in p["resource_list"]
    }
    source_calendars = {
        c["id"]: _periods(c["time_periods"])
        for c in source["resource_calendars"]
        if c["id"] in used
    }
    compiled_calendars = {
        c["id"]: _periods(c["time_periods"]) for c in compiled["resource_calendars"]
    }
    assert compiled_calendars == source_calendars

    # Decisioni: le stesse probabilita' su ogni ramo che il JSON dichiara.
    def branching(payload: dict) -> dict:
        return {
            (g["gateway_id"], p["path_id"]): float(p["value"])
            for g in payload["gateway_branching_probabilities"]
            for p in g["probabilities"]
        }

    compiled_branches = branching(compiled)
    for (gateway, flow), value in branching(source).items():
        if (gateway, flow) in compiled_branches:
            assert _close(compiled_branches[(gateway, flow)], value), (gateway, flow)
        else:
            # Solo una porta d'unione (un ramo, probabilita' 1) puo' mancare, e il report lo dice.
            assert _close(value, 1.0), (gateway, flow)
            assert any(note.element_id == gateway for note in result.notes), gateway

    # Attese: la stessa durata per ogni evento.
    source_events = {e["event_id"]: e for e in source.get("event_distribution", [])}
    compiled_events = {e["event_id"]: e for e in compiled.get("event_distribution", [])}
    assert compiled_events.keys() == source_events.keys()
    assert [
        key
        for key in source_events
        if not _same_distribution(source_events[key], compiled_events[key])
    ] == []


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_nothing_is_lost_without_a_note(path: Path) -> None:
    source, bpmn = _pair(path)
    result = import_prosimos(source, bpmn)
    # I 19 scenari si importano cosi' come sono: nessuna probabilita' riscritta, nessun ramo inventato.
    assert [note for note in result.notes if note.kind == "approximated"] == []
    used = {
        r["calendar"] for p in source["resource_profiles"] for r in p["resource_list"]
    }
    for calendar in source["resource_calendars"]:
        if calendar["id"] not in used:
            assert any(note.element_id == calendar["id"] for note in result.notes)


def test_simod_metadata_is_kept_in_the_report() -> None:
    source, bpmn = _pair(INPUTS / "real-life" / "AcademicCredentials.json")
    result = import_prosimos(source, bpmn)
    assert result.simod == {
        "process_model": source["process_model"],
        "model_type": source["model_type"],
        "granule_size": source["granule_size"],
    }


def test_instant_activities_are_imported_and_declared() -> None:
    source, bpmn = _pair(INPUTS / "real-life" / "AcademicCredentials.json")
    result = import_prosimos(source, bpmn)
    assert any(note.topic == "instant_activity" for note in result.notes)


def test_an_unknown_section_with_content_blocks_the_import() -> None:
    source, bpmn = _pair(INPUTS / "synthetic" / "Insurance_Claims.json")
    source = {**source, "something_new": [{"x": 1}]}
    with pytest.raises(ProsimosImportError, match="something_new"):
        import_prosimos(source, bpmn)


def test_batching_is_refused_with_a_reason() -> None:
    source, bpmn = _pair(INPUTS / "synthetic" / "Insurance_Claims.json")
    source = {**source, "batch_processing": [{"task_id": "x", "type": "Sequential"}]}
    with pytest.raises(ProsimosImportError, match="batch"):
        import_prosimos(source, bpmn)


def test_a_task_missing_from_the_bpmn_is_refused() -> None:
    source, bpmn = _pair(INPUTS / "synthetic" / "Insurance_Claims.json")
    source = json.loads(json.dumps(source))
    source["task_resource_distribution"][0]["task_id"] = "not-in-the-model"
    with pytest.raises(ProsimosImportError, match="not-in-the-model"):
        import_prosimos(source, bpmn)


def _diverging(source: dict, bpmn: str) -> tuple[dict, list[str]]:
    """Una decisione con almeno due rami in uscita nel BPMN, e i suoi rami."""
    from backend.simulation.ir.from_prosimos import _read_bpmn

    outgoing = _read_bpmn(bpmn).outgoing
    entry = next(
        g
        for g in source["gateway_branching_probabilities"]
        if len(outgoing.get(g["gateway_id"], [])) >= 2
    )
    return entry, outgoing[entry["gateway_id"]]


def test_rounded_probabilities_are_rescaled_and_declared() -> None:
    source, bpmn = _pair(INPUTS / "synthetic" / "Loan_Application.json")
    source = json.loads(json.dumps(source))
    entry, flows = _diverging(source, bpmn)
    # Somma 1,0004: un arrotondamento, non un errore.
    entry["probabilities"] = [
        {
            "path_id": flow,
            "value": "0.6002" if i == 0 else str(0.4002 / (len(flows) - 1)),
        }
        for i, flow in enumerate(flows)
    ]
    result = import_prosimos(source, bpmn)
    gateway = next(
        g for g in result.model.gateways if g.element_id == entry["gateway_id"]
    )
    assert math.isclose(sum(b.probability for b in gateway.branches), 1.0)
    assert any(
        n.topic == "rounded_probabilities" and n.element_id == entry["gateway_id"]
        for n in result.notes
    )


def test_a_branch_without_probability_gets_zero_and_a_note() -> None:
    source, bpmn = _pair(INPUTS / "synthetic" / "Loan_Application.json")
    source = json.loads(json.dumps(source))
    entry, flows = _diverging(source, bpmn)
    entry["probabilities"] = [{"path_id": flows[0], "value": "1"}]
    result = import_prosimos(source, bpmn)
    gateway = next(
        g for g in result.model.gateways if g.element_id == entry["gateway_id"]
    )
    assert {b.flow_id: b.probability for b in gateway.branches}[flows[1]] == 0
    assert any(
        n.topic == "missing_branch" and n.element_id == entry["gateway_id"]
        for n in result.notes
    )


def test_probabilities_far_from_one_are_refused() -> None:
    source, bpmn = _pair(INPUTS / "synthetic" / "Loan_Application.json")
    source = json.loads(json.dumps(source))
    entry, flows = _diverging(source, bpmn)
    entry["probabilities"] = [{"path_id": flow, "value": "0.3"} for flow in flows]
    with pytest.raises(ProsimosImportError, match="sommano"):
        import_prosimos(source, bpmn)


def _copy(name: str) -> tuple[dict, str]:
    source, bpmn = _pair(INPUTS / "synthetic" / f"{name}.json")
    return json.loads(json.dumps(source)), bpmn


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.update(arrival_time_calendar=[]),
        lambda s: s["resource_profiles"][0]["resource_list"][0].update(amount="due"),
        lambda s: s["task_resource_distribution"][0]["resources"][0].update(
            distribution_params="x"
        ),
        lambda s: s.update(
            case_attributes=[
                {"name": "t", "type": "discrete", "values": [{"value": 1}]}
            ]
        ),
        lambda s: s.update(
            prioritisation_rules=[{"priority_level": 1, "rules": [["bad"]]}]
        ),
        lambda s: s.update(resource_calendars="nope"),
    ],
    ids=[
        "empty-arrival-calendar",
        "amount-text",
        "params-text",
        "option-without-key",
        "rule-not-object",
        "calendars-text",
    ],
)
def test_a_malformed_scenario_always_gives_a_reason(change) -> None:
    source, bpmn = _copy("Insurance_Claims")
    change(source)
    with pytest.raises(ProsimosImportError):
        import_prosimos(source, bpmn)


def test_probabilities_outside_zero_and_one_are_refused() -> None:
    source, bpmn = _copy("Loan_Application")
    entry, flows = _diverging(source, bpmn)
    entry["probabilities"] = [
        {"path_id": flows[0], "value": "1.2"},
        {"path_id": flows[1], "value": "-0.2"},
    ]
    entry["probabilities"] += [{"path_id": flow, "value": "0"} for flow in flows[2:]]
    with pytest.raises(ProsimosImportError, match="fra 0 e 1"):
        import_prosimos(source, bpmn)


def test_arrivals_cannot_be_instant() -> None:
    source, bpmn = _copy("Insurance_Claims")
    source["arrival_time_distribution"] = {
        "distribution_name": "fix",
        "distribution_params": [{"value": 0}],
    }
    with pytest.raises(ProsimosImportError, match="intervallo zero"):
        import_prosimos(source, bpmn)


def test_fuzzy_calendars_are_refused_not_flattened() -> None:
    source, bpmn = _pair(INPUTS / "real-life" / "AcademicCredentials.json")
    source = {**source, "model_type": "FUZZY"}
    with pytest.raises(ProsimosImportError, match="FUZZY"):
        import_prosimos(source, bpmn)


def test_a_calendar_period_with_probabilities_is_refused() -> None:
    source, bpmn = _copy("Insurance_Claims")
    source["resource_calendars"][0]["time_periods"][0]["probability"] = 0.3
    with pytest.raises(ProsimosImportError, match="probability"):
        import_prosimos(source, bpmn)


def test_a_fractional_staff_is_refused() -> None:
    source, bpmn = _copy("Insurance_Claims")
    source["resource_profiles"][0]["resource_list"][0]["amount"] = 2.7
    with pytest.raises(ProsimosImportError, match="intero"):
        import_prosimos(source, bpmn)


def test_a_wait_must_be_an_event_that_the_case_waits_for() -> None:
    source, bpmn = _copy("Insurance_Claims_1_timer")
    source["event_distribution"][0]["event_id"] = source["task_resource_distribution"][
        0
    ]["task_id"]
    with pytest.raises(ProsimosImportError, match="non è nel BPMN"):
        import_prosimos(source, bpmn)


def test_case_attributes_and_priorities_survive_the_round_trip() -> None:
    source, bpmn = _copy("Insurance_Claims")
    source["case_attributes"] = [
        {
            "name": "code",
            "type": "discrete",
            "values": [
                {"key": "007", "value": 0.3333},
                {"key": "100", "value": 0.6666},
            ],
        },
        {
            "name": "amount",
            "type": "continuous",
            "values": {
                "distribution_name": "norm",
                "distribution_params": [
                    {"value": 500},
                    {"value": 50},
                    {"value": 100},
                    {"value": 900},
                ],
            },
        },
    ]
    source["prioritisation_rules"] = [
        {
            "priority_level": 1,
            "rules": [[{"attribute": "code", "comparison": "=", "value": "007"}]],
        },
        {
            "priority_level": 2,
            "rules": [[{"attribute": "amount", "comparison": ">", "value": 700}]],
        },
    ]
    result = import_prosimos(source, bpmn)
    compiled = compile_for_prosimos(result.model)
    assert compiled["prioritisation_rules"][0]["rules"] == [
        [{"attribute": "code", "comparison": "=", "value": "007"}]
    ]
    assert compiled["prioritisation_rules"][1]["rules"] == [
        [{"attribute": "amount", "comparison": ">", "value": "700"}]
    ]
    code = next(a for a in compiled["case_attributes"] if a["name"] == "code")
    assert [v["key"] for v in code["values"]] == ["007", "100"]
    assert math.isclose(sum(v["value"] for v in code["values"]), 1.0)
    assert any(
        n.topic == "rounded_probabilities" and n.element_id == "code"
        for n in result.notes
    )
    amount = next(a for a in compiled["case_attributes"] if a["name"] == "amount")
    assert _same_distribution(amount["values"], source["case_attributes"][1]["values"])


def test_one_missing_branch_reads_in_the_singular() -> None:
    source, bpmn = _copy("Loan_Application")
    entry, flows = _diverging(source, bpmn)
    entry["probabilities"] = [
        {"path_id": flow, "value": "1" if i == 0 else "0"}
        for i, flow in enumerate(flows[:-1])
    ]
    result = import_prosimos(source, bpmn)
    note = next(n for n in result.notes if n.topic == "missing_branch")
    assert note.message.startswith("1 percorso ")
