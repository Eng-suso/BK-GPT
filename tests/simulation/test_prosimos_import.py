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
from backend.simulation.ir.from_prosimos import (
    ProsimosImportError,
    import_prosimos,
    prosimos_exponential_mean,
)
from tests.simulation.simod_fuzzy import simod_fuzzy

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


def _copy(name: str, folder: str = "synthetic") -> tuple[dict, str]:
    source, bpmn = _pair(INPUTS / folder / f"{name}.json")
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


def _fuzzy(name: str, granule: int = 60) -> tuple[dict, str]:
    """Lo scenario ``name`` con i calendari delle risorse resi probabilistici, nel
    formato FUZZY che SIMOD scrive e Prosimos 2.1 legge (``parse_fuzzy_calendar``).

    ``granule`` deve cadere sugli orari dei calendari, come nei file di SIMOD."""
    folder, scenario = name.split("/")
    source, bpmn = _copy(scenario, folder)
    source["model_type"] = "FUZZY"
    source["granule_size"] = {"value": granule, "time_unit": "MINUTES"}
    for k, calendar in enumerate(source["resource_calendars"]):
        for j, period in enumerate(calendar["time_periods"]):
            period["probability"] = round(0.5 + 0.1 * ((k + j) % 5), 6)
            if period["endTime"].startswith("23:59:59"):
                period["endTime"] = "00:00:00"  # la mezzanotte, come la scrive SIMOD
        calendar["workload_ratio"] = [
            {**period, "probability": round(0.9 - 0.1 * ((k + j) % 3), 6)}
            for j, period in enumerate(calendar["time_periods"])
        ]
    return source, bpmn


def _probabilistic(periods: list[dict]) -> list[tuple]:
    return sorted(
        (
            p["from"],
            p["to"],
            p["beginTime"],
            p["endTime"],
            float(p.get("probability", 0.0)),
        )
        for p in periods
    )


@pytest.mark.parametrize(
    "load",
    [
        # Scoperto da SIMOD 5.2.1 sul log del dataset (vedi ATTRIBUTION.md).
        simod_fuzzy,
        lambda: _fuzzy("real-life/AcademicCredentials", granule=15),
        lambda: _fuzzy("synthetic/Loan_Application_3_timers", granule=1),
        lambda: simod_fuzzy(until_midnight=True),
    ],
    ids=["simod-discovered", "AcademicCredentials", "Loan_Application_3_timers", "simod-until-midnight"],
)
def test_fuzzy_calendars_round_trip_with_their_probabilities(load) -> None:
    source, bpmn = load()
    result = import_prosimos(source, bpmn)
    assert result.model.availability == "probabilistic"
    assert result.model.granule_minutes == source["granule_size"]["value"]
    compiled = compile_for_prosimos(result.model)

    assert compiled["model_type"] == "FUZZY"
    assert compiled["granule_size"] == source["granule_size"]
    assert isinstance(compiled["granule_size"]["value"], int)
    used = {
        r["calendar"] for p in source["resource_profiles"] for r in p["resource_list"]
    }
    def by_id(calendars: list[dict]) -> dict:
        return {
            c["id"]: (
                _probabilistic(c["time_periods"]),
                _probabilistic(c["workload_ratio"]),
            )
            for c in calendars
        }

    expected = by_id([c for c in source["resource_calendars"] if c["id"] in used])
    assert by_id(compiled["resource_calendars"]) == expected
    # Gli arrivi restano su un calendario fisso: Prosimos lo legge cosi'.
    assert all("probability" not in p for p in compiled["arrival_time_calendar"])
    assert any(n.topic == "probabilistic_calendars" for n in result.notes)


def test_a_fuzzy_granule_in_seconds_becomes_whole_minutes() -> None:
    source, bpmn = _fuzzy("synthetic/Insurance_Claims")
    source["granule_size"] = {"value": 120, "time_unit": "seconds"}
    assert import_prosimos(source, bpmn).model.granule_minutes == 2


@pytest.mark.parametrize(
    "granule",
    [{"value": 30, "time_unit": "seconds"}, {"value": 7, "time_unit": "MINUTES"}],
    ids=["below-a-minute", "does-not-divide-the-day"],
)
def test_a_fuzzy_granule_prosimos_cannot_slice_is_refused_with_the_reason(
    granule,
) -> None:
    # Prosimos divide la giornata in 1440 // granule fasce: con 7 minuti l'ultima
    # fascia (23:55-23:59) cadrebbe fuori dalla tabella.
    source, bpmn = _fuzzy("synthetic/Insurance_Claims")
    source["granule_size"] = granule
    with pytest.raises(ProsimosImportError, match="fasce uguali di minuti interi"):
        import_prosimos(source, bpmn)


@pytest.mark.parametrize(
    "begin, end",
    [("09:30:00", "11:00:00"), ("09:00:00", "23:59:00")],
    ids=["begin-inside-a-slot", "end-inside-a-slot"],
)
def test_a_fuzzy_slot_off_the_granule_is_refused_with_the_reason(begin, end) -> None:
    # Prosimos arrotonda gli orari alla fascia: 09:30 a fasce di 60 minuti diventerebbe
    # 09:00 e la disponibilita' cambierebbe senza dirlo.
    source, bpmn = _fuzzy("synthetic/Insurance_Claims")
    period = source["resource_calendars"][0]["time_periods"][0]
    period.update(beginTime=begin, endTime=end)
    with pytest.raises(ProsimosImportError, match="fasce di 60 minuti"):
        import_prosimos(source, bpmn)


def test_an_empty_workload_ratio_means_only_availability_counts() -> None:
    # Prosimos legge una lista vuota come carico 0 in ogni fascia: vale la disponibilita'.
    source, bpmn = _fuzzy("synthetic/Insurance_Claims")
    for calendar in source["resource_calendars"]:
        calendar["workload_ratio"] = []
    compiled = compile_for_prosimos(import_prosimos(source, bpmn).model)
    assert all(c["workload_ratio"] == [] for c in compiled["resource_calendars"])


def test_the_fuzzy_note_counts_only_the_calendars_resources_use() -> None:
    source, bpmn = _fuzzy("synthetic/Insurance_Claims")
    spare = json.loads(json.dumps(source["resource_calendars"][0]))
    spare["id"] = "spare"
    source["resource_calendars"].append(spare)
    used = {
        r["calendar"] for p in source["resource_profiles"] for r in p["resource_list"]
    }
    notes = import_prosimos(source, bpmn).notes
    (note,) = [n for n in notes if n.topic == "probabilistic_calendars"]
    word = "calendario" if len(used) == 1 else "calendari"
    assert f"per {len(used)} {word}," in note.message


def test_a_patch_keeps_probabilistic_availability_and_waits() -> None:
    from backend.simulation.ir.patch import ModelPatch, apply_patch

    source, bpmn = _fuzzy("synthetic/Insurance_Claims_1_timer")
    model = import_prosimos(source, bpmn).model
    patched = apply_patch(model, ModelPatch(activities=(model.activities[0],)))
    assert patched.availability == "probabilistic"
    assert patched.granule_minutes == model.granule_minutes
    assert patched.waits == model.waits


@pytest.mark.parametrize(
    "change, reason",
    [
        (lambda m: {"granule_minutes": 7}, "fasce uguali"),
        (
            lambda m: {
                "availability": "fixed",
                "granule_minutes": None,
                "calendars": tuple(
                    c.model_copy(
                        update={
                            "periods": tuple(
                                p.model_copy(update={"probability": None})
                                for p in c.periods
                            ),
                            "workload": tuple(
                                p.model_copy(update={"probability": None})
                                for p in c.workload
                            ),
                        }
                    )
                    for c in m.calendars
                ),
            },
            "disponibilita' fissa",
        ),
    ],
    ids=["granule-7", "fixed-with-workload"],
)
def test_the_ir_refuses_what_prosimos_cannot_run(change, reason) -> None:
    from backend.simulation.ir.model import SimulationModel

    source, bpmn = _fuzzy("synthetic/Insurance_Claims")
    model = import_prosimos(source, bpmn).model
    data = {**dict(model), **change(model)}
    with pytest.raises(ValueError, match=reason):
        SimulationModel(**data)


@pytest.mark.parametrize("section", ["arrival-band", "duration-window"])
def test_only_calendars_carry_a_probability(section) -> None:
    # Le probabilita' valgono per le persone: su arrivi e durate nessuno le applicherebbe.
    from backend.simulation.ir.model import SimulationModel

    source, bpmn = _fuzzy("synthetic/Insurance_Claims")
    model = import_prosimos(source, bpmn).model
    window = {"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "09:00:00", "end": "17:00:00", "probability": 0.5}
    data = model.model_dump()
    if section == "arrival-band":
        data["arrival"]["bands"] = [{**window, "mean_seconds": 600}]
    else:
        data["activities"][0]["duration_windows"] = [{**window, "factor": 1.3}]
    with pytest.raises(ValueError, match="probability"):
        SimulationModel.model_validate(data)


@pytest.mark.parametrize(
    "change, reason",
    [
        (lambda s: s.update(model_type="PROBABILISTIC"), "sconosciuto"),
        (lambda s: s.pop("granule_size"), "granule_size"),
        (lambda s: s["resource_calendars"][0].pop("workload_ratio"), "workload_ratio"),
        # Prosimos leggerebbe 0, cioe' mai disponibile: meglio dirlo che indovinare.
        (
            lambda s: s["resource_calendars"][0]["time_periods"][0].pop("probability"),
            "senza probabilità",
        ),
    ],
    ids=["unknown-type", "no-granule", "no-workload", "no-probability"],
)
def test_a_fuzzy_scenario_missing_a_piece_is_refused_with_the_reason(
    change, reason
) -> None:
    source, bpmn = _fuzzy("synthetic/Insurance_Claims")
    change(source)
    with pytest.raises(ProsimosImportError, match=reason):
        import_prosimos(source, bpmn)


def test_a_crisp_scenario_cannot_carry_workload_ratios() -> None:
    source, bpmn = _copy("Insurance_Claims")
    source["resource_calendars"][0]["workload_ratio"] = [
        {**source["resource_calendars"][0]["time_periods"][0], "probability": 0.5}
    ]
    with pytest.raises(ProsimosImportError, match="calendari fissi"):
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


# --------------------------------------------------------------------------- #
# IMP-01: arrivi che il motore rende piu' fitti
# --------------------------------------------------------------------------- #

TRUNCATED_ARRIVALS = {
    "Procure_to_Pay",
    "Procure_to_Pay_1_timer",
    "Procure_to_Pay_3_timers",
    "Procure_to_Pay_5_timers",
}
# Parole che il consulente non deve dover decodificare nel testo dell'avviso.
JARGON = ("expon", "esponenzial", "distribuzion", "prosimos", "troncat", "scale", "loc=")


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_only_procure_to_pay_warns_that_cases_arrive_faster(path: Path) -> None:
    source, bpmn = _pair(path)
    result = import_prosimos(source, bpmn)
    warnings = [note for note in result.notes if note.topic == "arrivals_faster"]

    if path.stem not in TRUNCATED_ARRIVALS:
        assert warnings == []
        return
    assert len(warnings) == 1
    note = warnings[0]
    assert note.kind == "warning"
    # Cosa dice il file, cosa succede davvero, quanto cambia e cosa fare.
    assert note.message == (
        "Il file indica in media un nuovo caso ogni 30 minuti, con intervalli fra "
        "5 secondi e 1 ora. La simulazione scarta gli intervalli più lunghi di 1 ora "
        "e li sostituisce con altri più brevi: in media arriva un caso ogni 21 minuti, "
        "circa il 45% di casi in più nello stesso tempo. Per correggere il file: se i "
        "casi arrivano con regolarità, usa un intervallo fisso di 30 minuti; se variano "
        "molto, porta il massimo ad almeno 2,5 ore."
    )
    assert not [word for word in JARGON if word in note.message.lower()]
    # Lo scenario resta com'era: l'avviso non tocca gli arrivi che il motore riceve.
    compiled = compile_for_prosimos(result.model)
    assert compiled["arrival_time_distribution"] == source["arrival_time_distribution"]


def test_the_produced_mean_is_the_one_prosimos_samples() -> None:
    # Media campionata con pix_framework 0.15 (200.000 valori, runner dello stack):
    # 1241,75 s per expon [1805, 5, 3600]; 17,00 s per expon [17, 16, 3600].
    assert prosimos_exponential_mean(1805, 5, 3600) == pytest.approx(1241.75, rel=0.01)
    assert prosimos_exponential_mean(17, 16, 3600) == pytest.approx(17.0, rel=1e-6)


@pytest.mark.parametrize(
    ("maximum", "warns"),
    [(3600, True), (5 * 1805, False), (100_000, False)],
    ids=["max-twice-the-mean", "max-five-times-the-mean", "max-far"],
)
def test_the_advice_on_the_maximum_removes_the_warning(maximum, warns) -> None:
    source, bpmn = _pair(INPUTS / "synthetic" / "Procure_to_Pay.json")
    source["arrival_time_distribution"]["distribution_params"][2]["value"] = maximum
    notes = import_prosimos(source, bpmn).notes
    assert any(note.topic == "arrivals_faster" for note in notes) is warns


def test_fixed_arrivals_never_warn() -> None:
    source, bpmn = _pair(INPUTS / "synthetic" / "Procure_to_Pay.json")
    source["arrival_time_distribution"] = {
        "distribution_name": "fix",
        "distribution_params": [{"value": 1805}],
    }
    assert not [
        n for n in import_prosimos(source, bpmn).notes if n.topic == "arrivals_faster"
    ]
