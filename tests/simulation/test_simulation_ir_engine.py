"""L'IR compilato gira davvero su Prosimos 2.x, e le capacita' hanno effetto.

Serve Prosimos nell'interprete (Python 3.11-3.12): nella CI del backend si
salta e lo esegue il job ``prosimos-runner``. In locale, nell'ambiente del
runner (``ops/prosimos/runner/requirements-test.txt``) e senza ``.env``:

    pytest --noconftest tests/simulation/test_simulation_ir_engine.py
"""

import json
import random
import sys
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("prosimos")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ops" / "prosimos" / "spike"))

import contract_spike  # noqa: E402

from backend.simulation.ir import compile_for_prosimos  # noqa: E402
from backend.simulation.ir.model import (  # noqa: E402
    Activity,
    Arrival,
    Assignment,
    AttributeUpdate,
    Branch,
    Calendar,
    CalendarPeriod,
    CaseAttribute,
    Condition,
    DiscreteOption,
    Exponential,
    Gateway,
    LogNormal,
    Normal,
    PriorityRule,
    Resource,
    ResourcePool,
    Rule,
    SimulationModel,
    Uniform,
)


def _when(attribute, operator, value) -> Condition:
    return Condition(any_of=((Rule(attribute=attribute, operator=operator, value=value),),))


def _model(*, busy: bool = False) -> SimulationModel:
    office = Calendar(id="office", name="Ufficio", periods=(
        CalendarPeriod(from_day="MONDAY", to_day="FRIDAY", begin="09:00:00", end="17:00:00"),))
    approvals = Calendar(id="appr", name="Approvazioni", periods=(
        CalendarPeriod(from_day="MONDAY", to_day="THURSDAY", begin="10:00:00", end="14:00:00"),))
    return SimulationModel(
        arrival=Arrival(
            interarrival=Exponential(mean=400 if busy else 1800, minimum=0, maximum=18000),
            calendar_id="office",
        ),
        calendars=(office, approvals),
        pools=(ResourcePool(id="p", name="Ufficio", resources=(
            Resource(id="ops", name="Operatore", cost_per_hour=30, amount=1 if busy else 2, calendar_id="office"),
            Resource(id="appr", name="Approvatore", cost_per_hour=60, amount=1, calendar_id="appr"),
        )),),
        activities=(
            Activity(element_id="T_receive", assignments=(
                Assignment(resource_id="ops", duration=Normal(mean=600, std=120, minimum=120, maximum=1200)),)),
            Activity(element_id="T_approve", assignments=(
                Assignment(resource_id="appr", duration=Uniform(minimum=600, maximum=2400)),)),
            Activity(element_id="T_pay", assignments=(
                Assignment(resource_id="ops", duration=Normal(mean=900, std=180, minimum=300, maximum=1800)),)),
        ),
        gateways=(Gateway(element_id="G_split", branches=(
            Branch(flow_id="F_high", probability=0.5, condition=_when("importo", ">", 5000)),
            Branch(flow_id="F_low", probability=0.5, condition=_when("importo", "<=", 5000)),
        )),),
        case_attributes=(
            CaseAttribute(name="tipo", options=(DiscreteOption(value="premium", probability=0.2),
                                                DiscreteOption(value="standard", probability=0.8))),
            CaseAttribute(name="importo", distribution=Uniform(minimum=100, maximum=12000)),
        ),
        attribute_updates=(AttributeUpdate(element_id="T_receive", name="rischio", expression="importo / 1000"),),
        priority_rules=(
            PriorityRule(level=1, condition=_when("tipo", "=", "premium")),
            PriorityRule(level=2, condition=_when("tipo", "=", "standard")),
        ),
    )


def _run(model: SimulationModel, seed: int = 5, *, payload: dict | None = None, bpmn: str | None = None,
         cases: int = 200) -> list[dict]:
    import numpy
    from prosimos.simulation_engine import run_simulation

    random.seed(seed)
    numpy.random.seed(seed)
    with tempfile.TemporaryDirectory() as tmp:
        scenario, log = Path(tmp) / "s.json", Path(tmp) / "log.csv"
        scenario.write_text(json.dumps(payload if payload is not None else compile_for_prosimos(model)))
        bpmn_path = contract_spike.BPMN_PATH
        if bpmn is not None:
            bpmn_path = Path(tmp) / "model.bpmn"
            bpmn_path.write_text(bpmn, encoding="utf-8")
        run_simulation(str(bpmn_path), str(scenario), cases, None, str(log), contract_spike.START)
        return contract_spike.parse_log(log.read_text())


def test_conditional_routing_from_the_ir_is_applied():
    assert contract_spike.check_branch_rules(_run(_model())) is None


def test_attribute_updates_from_the_ir_reach_the_log():
    assert contract_spike.check_event_attributes(_run(_model())) is None


def test_resource_calendars_from_the_ir_are_respected():
    assert contract_spike.check_calendars(_run(_model())) is None


def test_priority_rules_from_the_ir_serve_premium_first():
    assert contract_spike.check_prioritisation(_run(_model(busy=True))) is None


def test_a_run_from_the_v2_contract_keeps_calendars_lognormal_and_rules_on_the_engine():
    # SIM-37, criterio d'uscita: lo scenario esce dal builder della richiesta v2
    # (verifica sul BPMN compresa), non da `compile_for_prosimos` chiamato a mano.
    from backend.simulation.scenario_builder import build_prosimos_scenario_from_model

    base = _model()
    approve = Activity(element_id="T_approve", assignments=(
        Assignment(resource_id="appr", duration=LogNormal(mean=1500, variance=250000, minimum=300, maximum=6000)),))
    model = base.model_copy(update={"activities": (base.activities[0], approve, base.activities[2])})
    scenario = build_prosimos_scenario_from_model(
        bpmn_xml=contract_spike.BPMN_PATH.read_text(encoding="utf-8"), model=model)

    durations = {t["task_id"]: t["resources"][0]["distribution_name"] for t in scenario.payload["task_resource_distribution"]}
    assert durations["T_approve"] == "lognorm"
    rows = _run(model, payload=scenario.payload)
    assert contract_spike.check_branch_rules(rows) is None
    assert contract_spike.check_calendars(rows) is None


def test_a_task_with_other_resources_is_shared_on_the_engine():
    # A2-2: l'approvazione la fanno l'approvatore e, quando lui e' occupato o fuori
    # orario, un senior con la sua durata. Sul motore lavorano entrambi.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.scenario_builder import build_prosimos_scenario

    request = CreateSimulationRunRequest(
        arrival_interval_seconds=400,
        resources=[
            {"id": "ops", "name": "Operatore", "cost_per_hour": 30, "amount": 2},
            {"id": "appr", "name": "Approvatore", "cost_per_hour": 60, "amount": 1},
            {"id": "senior", "name": "Senior", "cost_per_hour": 90, "amount": 1},
        ],
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600, "resource_id": "ops"},
            {"element_id": "T_approve", "mean_seconds": 1800, "resource_id": "appr",
             "other_assignments": [{"resource_id": "senior", "mean_seconds": 900, "distribution": "fixed"}]},
            {"element_id": "T_pay", "mean_seconds": 600, "resource_id": "ops"},
        ],
    )
    scenario = build_prosimos_scenario(bpmn_xml=contract_spike.BPMN_PATH.read_text(encoding="utf-8"), request=request)

    rows = [row for row in _run(_model(), payload=scenario.payload) if row["activity"] == "Approva"]
    by_resource: dict[str, list[float]] = {}
    for row in rows:
        by_resource.setdefault(row["resource"].rsplit("_", 1)[0], []).append(row["end"] - row["start"])
    assert set(by_resource) == {"Approvatore", "Senior"}, by_resource.keys()
    # Ognuno con la sua durata: il senior e' fisso a 15 minuti di lavoro. Un'approvazione
    # iniziata a fine turno riprende il mattino dopo (calendario standard, 16 ore di
    # pausa notturna), quindi il tempo trascorso e' 15 minuti piu' le notti di mezzo.
    night = 16 * 3600
    assert all(round(seconds - 900) % night == 0 for seconds in by_resource["Senior"]), by_resource["Senior"]
    assert min(by_resource["Senior"]) == 900


def test_cases_arrive_only_inside_the_arrival_calendar():
    # A2-3: il consulente fa arrivare i casi solo la mattina dei giorni feriali.
    from datetime import datetime

    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.scenario_builder import build_prosimos_scenario

    request = CreateSimulationRunRequest(
        tasks=[{"element_id": t, "mean_seconds": 600} for t in ("T_receive", "T_approve", "T_pay")],
        calendars=[{"id": "mornings", "name": "Mattine", "periods": [
            {"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "09:00", "end": "12:00"}]}],
        arrival={"mean_seconds": 1200, "distribution": "fixed", "calendar_id": "mornings"},
    )
    scenario = build_prosimos_scenario(bpmn_xml=contract_spike.BPMN_PATH.read_text(encoding="utf-8"), request=request)

    first: dict[str, datetime] = {}
    for row in _run(_model(), payload=scenario.payload):
        enabled = datetime.fromisoformat(row["enable_time"].replace(" ", "T"))
        if row["case_id"] not in first or enabled < first[row["case_id"]]:
            first[row["case_id"]] = enabled
    assert len(first) == 200
    outside = [t for t in first.values() if t.weekday() > 4 or not 9 <= t.hour < 12]
    assert outside == [], outside[:5]


def test_a_duration_that_depends_on_a_case_category_is_applied_by_the_engine():
    # SIM-32: Approva dura 10 minuti per i premium, 25 per gli standard. Il motore
    # non lo sa fare: lo scenario lo compila in varianti dietro una decisione per regola.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
    from backend.simulation.scenario_builder import build_prosimos_scenario

    request = CreateSimulationRunRequest(
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600, "distribution": "fixed"},
            {"element_id": "T_approve", "mean_seconds": 1200, "distribution": "fixed",
             "duration_by": {"attribute": "tipo", "variants": [
                 {"value": "premium", "mean_seconds": 600, "distribution": "fixed"},
                 {"value": "standard", "mean_seconds": 1500, "distribution": "fixed"}]}},
            {"element_id": "T_pay", "mean_seconds": 600, "distribution": "fixed"},
        ],
        model_patch={
            "case_attributes": [
                {"name": "tipo", "options": [{"value": "premium", "probability": 0.3}, {"value": "standard", "probability": 0.7}]},
                {"name": "importo", "distribution": {"kind": "uniform", "minimum": 100, "maximum": 12000}},
            ],
            "gateways": [{"element_id": "G_split", "branches": [
                {"flow_id": "F_high", "probability": 0.5, "condition": _amount_rule(">")},
                {"flow_id": "F_low", "probability": 0.5, "condition": _amount_rule("<=")},
            ]}],
        },
    )
    bpmn = normalize_bpmn_for_prosimos(contract_spike.BPMN_PATH.read_text(encoding="utf-8"))
    scenario = build_prosimos_scenario(bpmn_xml=bpmn, request=request)
    assert scenario.bpmn_xml is not None

    rows = _run(_model(), payload=scenario.payload, bpmn=scenario.bpmn_xml)
    worked: dict[str, set[float]] = {}
    for row in rows:
        if row["activity"] == "Approva":
            worked.setdefault(row.get("tipo", ""), set()).add(round(row["end"] - row["start"]) % (16 * 3600))
    assert worked.get("premium") == {600}, worked
    assert worked.get("standard") == {1500}, worked
    # Una sola attività nel log: le varianti hanno il nome dell'originale.
    assert {row["activity"] for row in rows} == {"Ricevi", "Approva", "Paga"}


def _amount_rule(operator: str) -> dict:
    return {"any_of": [[{"attribute": "importo", "operator": operator, "value": 5000}]]}


def test_a_v1_run_with_a_model_patch_routes_by_the_consultant_rules():
    # A2-1: il pannello manda la richiesta v1 e, in `model_patch`, attributi e
    # rami per regola; sul motore i casi sopra soglia passano dall'approvazione.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.scenario_builder import build_prosimos_scenario

    request = CreateSimulationRunRequest(
        tasks=[{"element_id": t, "mean_seconds": 600} for t in ("T_receive", "T_approve", "T_pay")],
        model_patch={
            "case_attributes": [{"name": "importo", "distribution": {"kind": "uniform", "minimum": 100, "maximum": 12000}}],
            "gateways": [{"element_id": "G_split", "branches": [
                {"flow_id": "F_high", "probability": 0.5, "condition": _amount_rule(">")},
                {"flow_id": "F_low", "probability": 0.5, "condition": _amount_rule("<=")},
            ]}],
        },
    )
    scenario = build_prosimos_scenario(bpmn_xml=contract_spike.BPMN_PATH.read_text(encoding="utf-8"), request=request)

    assert contract_spike.check_branch_rules(_run(_model(), payload=scenario.payload)) is None


def _flow_rule_rows(**approve) -> list[dict]:
    # SIM-35: salto e rilavorazione su Approva, compilati come decisioni per regola.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
    from backend.simulation.scenario_builder import build_prosimos_scenario

    request = CreateSimulationRunRequest(
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600, "distribution": "fixed"},
            {"element_id": "T_approve", "mean_seconds": 1200, "distribution": "fixed", **approve},
            {"element_id": "T_pay", "mean_seconds": 600, "distribution": "fixed"},
        ],
        model_patch={
            "case_attributes": [
                {"name": "importo", "distribution": {"kind": "uniform", "minimum": 100, "maximum": 12000}},
            ],
            # Tutti i casi passano da Approva: il salto e il ritorno si leggono da soli.
            "gateways": [{"element_id": "G_split", "branches": [
                {"flow_id": "F_high", "probability": 1.0}, {"flow_id": "F_low", "probability": 0.0}]}],
        },
    )
    bpmn = normalize_bpmn_for_prosimos(contract_spike.BPMN_PATH.read_text(encoding="utf-8"))
    scenario = build_prosimos_scenario(bpmn_xml=bpmn, request=request)
    return _run(_model(), payload=scenario.payload, bpmn=scenario.bpmn_xml)


def _executions(rows: list[dict], activity: str) -> dict[str, int]:
    counts = {row["case_id"]: 0 for row in rows}
    for row in rows:
        if row["activity"] == activity:
            counts[row["case_id"]] += 1
    return counts


def test_a_skipped_activity_is_left_out_by_its_share_of_cases():
    rows = _flow_rule_rows(skip={"probability": 0.3})
    approvals = _executions(rows, "Approva")
    skipped = sum(1 for n in approvals.values() if n == 0) / len(approvals)
    assert 0.2 < skipped < 0.4, skipped
    # Chi salta prosegue: ogni caso arriva a Paga.
    assert set(_executions(rows, "Paga").values()) == {1}


def test_a_conditional_skip_leaves_out_only_the_matching_cases():
    small = {"any_of": [[{"attribute": "importo", "operator": "<", "value": 4000}]]}
    rows = _flow_rule_rows(skip={"probability": 1, "condition": small})
    approvals = _executions(rows, "Approva")
    amounts = {row["case_id"]: float(row["importo"]) for row in rows}
    assert all((approvals[case] == 0) == (amounts[case] < 4000) for case in approvals)


def test_a_rework_repeats_the_activity_by_its_share_up_to_the_limit():
    rows = _flow_rule_rows(rework={"back_to": "T_receive", "probability": 0.6, "max_repeats": 2})
    approvals = _executions(rows, "Approva")
    # Al più due ritorni: tre esecuzioni per caso, mai quattro.
    assert set(approvals.values()) <= {1, 2, 3}
    shares = {n: sum(1 for v in approvals.values() if v == n) / len(approvals) for n in (1, 2, 3)}
    # 0.4 / 0.6*0.4 / 0.6^2 con 200 casi.
    assert 0.3 < shares[1] < 0.5 and 0.15 < shares[2] < 0.33 and 0.26 < shares[3] < 0.46, shares
    # Si torna a Ricevi: lo rifà ogni ritorno.
    assert _executions(rows, "Ricevi") == approvals


def test_a_timer_escalation_sends_the_cases_that_outlast_it_down_the_escalation_path():
    # SIM-35: Approva dura fra 10 e 40 minuti, il timer scade a 30: un terzo dei
    # casi passa da Sollecita, e per loro Approva si ferma a 30 minuti esatti.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
    from backend.simulation.scenario_builder import build_prosimos_scenario

    source = contract_spike.BPMN_PATH.read_text(encoding="utf-8").replace(
        '<exclusiveGateway id="G_join"/>',
        '<boundaryEvent id="B_late" attachedToRef="T_approve"><timerEventDefinition><timeDuration>PT30M</timeDuration>'
        '</timerEventDefinition></boundaryEvent><task id="T_remind" name="Sollecita"/><exclusiveGateway id="G_join"/>',
    ).replace(
        '<sequenceFlow id="F_back" sourceRef="T_approve" targetRef="G_join"/>',
        '<sequenceFlow id="F_back" sourceRef="T_approve" targetRef="G_join"/>'
        '<sequenceFlow id="F_late" sourceRef="B_late" targetRef="T_remind"/>'
        '<sequenceFlow id="F_reminded" sourceRef="T_remind" targetRef="G_join"/>',
    )
    request = CreateSimulationRunRequest(
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600, "distribution": "fixed"},
            {"element_id": "T_approve", "mean_seconds": 1500, "distribution": "uniform", "min_seconds": 600, "max_seconds": 2400},
            {"element_id": "T_remind", "mean_seconds": 300, "distribution": "fixed"},
            {"element_id": "T_pay", "mean_seconds": 600, "distribution": "fixed"},
        ],
        gateways=[{"element_id": "G_split", "branches": [{"flow_id": "F_high", "probability": 1.0}, {"flow_id": "F_low", "probability": 0.0}]}],
    )
    scenario = build_prosimos_scenario(bpmn_xml=normalize_bpmn_for_prosimos(source), request=request)
    rows = _run(_model(), payload=scenario.payload, bpmn=scenario.bpmn_xml)

    reminded = {row["case_id"] for row in rows if row["activity"] == "Sollecita"}
    cases = {row["case_id"] for row in rows}
    assert 0.2 < len(reminded) / len(cases) < 0.47, len(reminded) / len(cases)
    worked = {row["case_id"]: round(row["end"] - row["start"]) % (16 * 3600) for row in rows if row["activity"] == "Approva"}
    assert {worked[case] for case in reminded} == {1800}
    assert all(600 <= worked[case] <= 1800 for case in cases - reminded)
    # Ogni caso arriva in fondo, dal ramo normale o dall'escalation.
    assert set(_executions(rows, "Paga").values()) == {1}


def test_a_non_interrupting_timer_starts_its_branch_without_stopping_the_activity():
    # SIM-11g: Approva dura fra 10 e 40 minuti; dopo 30 minuti, se e' ancora in
    # corso, parte anche Sollecita. Approva non si ferma, e Sollecita parte 30
    # minuti dopo che il caso e' arrivato ad Approva.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
    from backend.simulation.scenario_builder import build_prosimos_scenario

    source = contract_spike.BPMN_PATH.read_text(encoding="utf-8").replace(
        '<exclusiveGateway id="G_join"/>',
        '<boundaryEvent id="B_late" attachedToRef="T_approve" cancelActivity="false"><timerEventDefinition>'
        '<timeDuration>PT30M</timeDuration></timerEventDefinition></boundaryEvent>'
        '<task id="T_remind" name="Sollecita"/><endEvent id="E_reminded"/><exclusiveGateway id="G_join"/>',
    ).replace(
        '<sequenceFlow id="F_back" sourceRef="T_approve" targetRef="G_join"/>',
        '<sequenceFlow id="F_back" sourceRef="T_approve" targetRef="G_join"/>'
        '<sequenceFlow id="F_late" sourceRef="B_late" targetRef="T_remind"/>'
        '<sequenceFlow id="F_reminded" sourceRef="T_remind" targetRef="E_reminded"/>',
    )
    request = CreateSimulationRunRequest(
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600, "distribution": "fixed", "resource_id": "r"},
            {"element_id": "T_approve", "mean_seconds": 1500, "distribution": "uniform", "min_seconds": 600,
             "max_seconds": 2400, "resource_id": "r"},
            {"element_id": "T_remind", "mean_seconds": 60, "distribution": "fixed", "resource_id": "r"},
            {"element_id": "T_pay", "mean_seconds": 600, "distribution": "fixed", "resource_id": "r"},
        ],
        resources=[{"id": "r", "name": "Ufficio", "amount": 20, "cost_per_hour": 30}],
        gateways=[{"element_id": "G_split", "branches": [{"flow_id": "F_high", "probability": 1.0}, {"flow_id": "F_low", "probability": 0.0}]}],
    )
    scenario = build_prosimos_scenario(bpmn_xml=normalize_bpmn_for_prosimos(source), request=request)
    rows = _run(_model(), payload=scenario.payload, bpmn=scenario.bpmn_xml)

    cases: dict[str, dict[str, dict]] = {}
    for row in rows:
        cases.setdefault(row["case_id"], {})[row["activity"]] = row
    reminded = [case for case in cases.values() if "Sollecita" in case]
    assert 0.2 < len(reminded) / len(cases) < 0.47, len(reminded) / len(cases)
    for case in reminded:
        assert case["Sollecita"]["enable"] - case["Approva"]["enable"] == 1800
    # Approva non e' interrotta: dura fino a 40 minuti, e ogni caso paga una volta.
    worked = [round(case["Approva"]["end"] - case["Approva"]["start"]) % (16 * 3600) for case in cases.values()]
    assert max(worked) > 1800 and all(600 <= w <= 2400 for w in worked)
    assert set(_executions(rows, "Paga").values()) == {1}


def test_arrival_bands_from_the_panel_shape_the_arrivals_through_the_runner(tmp_path, monkeypatch):
    # SIM-08: picco la mattina (un caso ogni 5 minuti), calma il pomeriggio (ogni 30).
    # Prosimos 2.1 non lo sa fare: gli arrivi li genera il runner DeliR.
    from datetime import UTC, datetime

    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
    from backend.simulation.scenario_builder import build_prosimos_scenario

    sys.path.insert(0, str(ROOT / "ops" / "prosimos" / "runner"))
    import runner

    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    request = CreateSimulationRunRequest(
        tasks=[{"element_id": t, "mean_seconds": 60, "distribution": "fixed"} for t in ("T_receive", "T_approve", "T_pay")],
        arrival={"mean_seconds": 900, "bands": [
            {"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "09:00", "end": "12:00", "mean_seconds": 300},
            {"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "14:00", "end": "17:00", "mean_seconds": 1800},
        ]},
    )
    bpmn = normalize_bpmn_for_prosimos(contract_spike.BPMN_PATH.read_text(encoding="utf-8"))
    scenario = build_prosimos_scenario(bpmn_xml=bpmn, request=request)
    body = runner.simulate(bpmn.encode(), json.dumps(scenario.payload).encode(), 400, contract_spike.START, 21)

    assert body["ArrivalBands"] == 2
    rows = contract_spike.parse_log((tmp_path / body["LogsFilename"]).read_text(encoding="utf-8"))
    arrivals: dict[str, float] = {}
    for row in rows:
        arrivals[row["case_id"]] = min(arrivals.get(row["case_id"], row["enable"]), row["enable"])
    hours = [datetime.fromtimestamp(t, UTC).hour for t in arrivals.values()]
    morning = sum(1 for h in hours if 9 <= h < 12)
    afternoon = sum(1 for h in hours if 14 <= h < 17)
    assert morning + afternoon == len(hours), "un caso e' arrivato fuori dalle fasce"
    assert 4.5 < morning / afternoon < 8, (morning, afternoon)


def test_a_duration_by_arrival_band_follows_the_band_each_case_arrived_in(tmp_path, monkeypatch):
    # SIM-33: chi arriva la mattina viene approvato in 5 minuti, chi arriva il
    # pomeriggio in 25. La fascia la scrive il runner nell'attributo del caso.
    from datetime import UTC, datetime

    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
    from backend.simulation.scenario_builder import build_prosimos_scenario

    sys.path.insert(0, str(ROOT / "ops" / "prosimos" / "runner"))
    import runner

    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    request = CreateSimulationRunRequest(
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 60, "distribution": "fixed"},
            {"element_id": "T_approve", "mean_seconds": 600, "distribution": "fixed", "duration_by": {"attribute": "fascia", "variants": [
                {"value": "Fascia 1", "mean_seconds": 300, "distribution": "fixed"},
                {"value": "Fascia 2", "mean_seconds": 1500, "distribution": "fixed"},
            ]}},
            {"element_id": "T_pay", "mean_seconds": 60, "distribution": "fixed"},
        ],
        arrival={"mean_seconds": 900, "band_attribute": "fascia", "bands": [
            {"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "09:00", "end": "12:00", "mean_seconds": 1200},
            {"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "13:00", "end": "16:00", "mean_seconds": 1200},
        ]},
        model_patch={"case_attributes": [{"name": "fascia", "options": [
            {"value": "Fascia 1", "probability": 0.5}, {"value": "Fascia 2", "probability": 0.5}]}]},
    )
    bpmn = normalize_bpmn_for_prosimos(contract_spike.BPMN_PATH.read_text(encoding="utf-8"))
    scenario = build_prosimos_scenario(bpmn_xml=bpmn, request=request)
    body = runner.simulate((scenario.bpmn_xml or bpmn).encode(), json.dumps(scenario.payload).encode(), 120,
                           contract_spike.START, 13)

    rows = contract_spike.parse_log((tmp_path / body["LogsFilename"]).read_text(encoding="utf-8"))
    arrived: dict[str, float] = {}
    for row in rows:
        arrived[row["case_id"]] = min(arrived.get(row["case_id"], row["enable"]), row["enable"])
    night = 16 * 3600
    seen = {"morning": 0, "afternoon": 0}
    for row in rows:
        if "Approva" not in row["activity"]:
            continue
        morning = datetime.fromtimestamp(arrived[row["case_id"]], UTC).hour < 12
        expected = 300 if morning else 1500
        # Un'approvazione a cavallo della sera riprende il mattino dopo: si toglie la notte.
        assert round(row["end"] - row["start"] - expected) % night == 0, (morning, row["end"] - row["start"])
        seen["morning" if morning else "afternoon"] += 1
    assert seen["morning"] > 10 and seen["afternoon"] > 10, seen


def test_a_duration_window_slows_the_activities_that_start_in_it(tmp_path, monkeypatch):
    # SIM-33b: un'approvazione iniziata dalle 13 alle 17 dura il doppio, anche
    # nella copia per categoria (premium 5 minuti, gli altri 10). Prosimos 2.1
    # non lo sa fare: lo applica il runner DeliR.
    from datetime import UTC, datetime

    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
    from backend.simulation.scenario_builder import build_prosimos_scenario

    sys.path.insert(0, str(ROOT / "ops" / "prosimos" / "runner"))
    import runner

    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    afternoon = {"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "13:00", "end": "17:00", "factor": 2}
    request = CreateSimulationRunRequest(
        arrival_interval_seconds=900,
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 60, "distribution": "fixed"},
            {"element_id": "T_approve", "mean_seconds": 600, "distribution": "fixed", "duration_windows": [afternoon],
             "duration_by": {"attribute": "tipo", "variants": [{"value": "premium", "mean_seconds": 300, "distribution": "fixed"}]}},
            {"element_id": "T_pay", "mean_seconds": 60, "distribution": "fixed"},
        ],
        model_patch={"case_attributes": [{"name": "tipo", "options": [
            {"value": "premium", "probability": 0.5}, {"value": "standard", "probability": 0.5}]}]},
    )
    bpmn = normalize_bpmn_for_prosimos(contract_spike.BPMN_PATH.read_text(encoding="utf-8"))
    scenario = build_prosimos_scenario(bpmn_xml=bpmn, request=request)
    body = runner.simulate((scenario.bpmn_xml or bpmn).encode(), json.dumps(scenario.payload).encode(), 150,
                           contract_spike.START, 17)

    assert body["DurationWindows"] == 2  # l'attivita' e la sua copia per "premium"
    rows = contract_spike.parse_log((tmp_path / body["LogsFilename"]).read_text(encoding="utf-8"))
    night = 16 * 3600
    seen = {"morning": 0, "afternoon": 0}
    for row in rows:
        if "Approva" not in row["activity"]:
            continue
        start = datetime.fromtimestamp(row["start"], UTC)
        late = 13 <= start.hour < 17
        expected = (300 if row["tipo"] == "premium" else 600) * (2 if late else 1)
        # Un'approvazione a cavallo della sera riprende il mattino dopo: si toglie la notte.
        assert round(row["end"] - row["start"] - expected) % night == 0, (start, row["tipo"], row["end"] - row["start"])
        seen["afternoon" if late else "morning"] += 1
    assert seen["morning"] > 10 and seen["afternoon"] > 10, seen


def test_a_timer_in_the_flow_makes_the_case_wait_on_the_engine(tmp_path, monkeypatch):
    # SIM-11c: "Attendi 2 ore" fra le due attivita'. Prima il timer spariva e
    # il secondo passo partiva subito; ora parte due ore dopo, anche fuori orario.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
    from backend.simulation.scenario_builder import build_prosimos_scenario

    sys.path.insert(0, str(ROOT / "ops" / "prosimos" / "runner"))
    import runner

    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    source = contract_spike.BPMN_PATH.read_text(encoding="utf-8")
    flow = next(line for line in source.splitlines() if 'sourceRef="T_approve"' in line)
    target = flow.split('targetRef="')[1].split('"')[0]
    bpmn = normalize_bpmn_for_prosimos(source.replace(flow, flow.replace(f'targetRef="{target}"', 'targetRef="W"') + (
        '<intermediateCatchEvent id="W" name="Attendi 2 ore"><timerEventDefinition><timeDuration>PT2H</timeDuration>'
        f'</timerEventDefinition></intermediateCatchEvent><sequenceFlow id="F_wait" sourceRef="W" targetRef="{target}"/>'
    )))
    request = CreateSimulationRunRequest(
        tasks=[{"element_id": t, "mean_seconds": 60, "distribution": "fixed", "resource_id": "r"} for t in ("T_receive", "T_approve", "T_pay")],
        resources=[{"id": "r", "name": "Ufficio", "amount": 5, "cost_per_hour": 30}],
    )
    scenario = build_prosimos_scenario(bpmn_xml=bpmn, request=request)
    body = runner.simulate(bpmn.encode(), json.dumps(scenario.payload).encode(), 40, contract_spike.START, 7)

    rows = contract_spike.parse_log((tmp_path / body["LogsFilename"]).read_text(encoding="utf-8"))
    cases: dict[str, dict[str, dict]] = {}
    for row in rows:
        cases.setdefault(row["case_id"], {})[row["activity"]] = row
    waited = [case for case in cases.values() if "Approva" in case and "Paga" in case]
    assert len(waited) > 5
    for case in waited:
        gap = case["Paga"]["enable"] - case["Approva"]["end"]
        assert gap == 7200, gap


def test_a_subprocess_runs_step_by_step_on_the_engine(tmp_path, monkeypatch):
    # SIM-11e: "Istruttoria" contiene Verifica e poi Approva o Rifiuta. Prima era
    # un'unica attivita'; ora il log ha i passi interni con le loro durate.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
    from backend.simulation.scenario_builder import build_prosimos_scenario
    sys.path.insert(0, str(ROOT / "ops" / "prosimos" / "runner"))
    import runner

    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    bpmn = normalize_bpmn_for_prosimos("""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D"><bpmn:process id="P" isExecutable="false">
  <bpmn:startEvent id="S" /><bpmn:task id="A" name="Ricevi" />
  <bpmn:subProcess id="SP" name="Istruttoria">
    <bpmn:startEvent id="SP_s" /><bpmn:task id="SP_check" name="Verifica" /><bpmn:exclusiveGateway id="SP_g" />
    <bpmn:task id="SP_ok" name="Approva" /><bpmn:task id="SP_ko" name="Rifiuta" /><bpmn:exclusiveGateway id="SP_j" /><bpmn:endEvent id="SP_e" />
    <bpmn:sequenceFlow id="SP_f1" sourceRef="SP_s" targetRef="SP_check" /><bpmn:sequenceFlow id="SP_f2" sourceRef="SP_check" targetRef="SP_g" />
    <bpmn:sequenceFlow id="SP_ok_f" sourceRef="SP_g" targetRef="SP_ok" /><bpmn:sequenceFlow id="SP_ko_f" sourceRef="SP_g" targetRef="SP_ko" />
    <bpmn:sequenceFlow id="SP_f3" sourceRef="SP_ok" targetRef="SP_j" /><bpmn:sequenceFlow id="SP_f4" sourceRef="SP_ko" targetRef="SP_j" />
    <bpmn:sequenceFlow id="SP_f5" sourceRef="SP_j" targetRef="SP_e" />
  </bpmn:subProcess>
  <bpmn:task id="B" name="Comunica" /><bpmn:endEvent id="E" />
  <bpmn:sequenceFlow id="f1" sourceRef="S" targetRef="A" /><bpmn:sequenceFlow id="f2" sourceRef="A" targetRef="SP" />
  <bpmn:sequenceFlow id="f3" sourceRef="SP" targetRef="B" /><bpmn:sequenceFlow id="f4" sourceRef="B" targetRef="E" />
</bpmn:process></bpmn:definitions>""")
    seconds = {"A": 60, "SP_check": 300, "SP_ok": 600, "SP_ko": 900, "B": 60}
    request = CreateSimulationRunRequest(
        resources=[{"id": "r", "name": "Ufficio", "amount": 10, "cost_per_hour": 30}],
        tasks=[{"element_id": t, "mean_seconds": s, "distribution": "fixed", "resource_id": "r"} for t, s in seconds.items()],
        gateways=[{"element_id": "SP_g", "branches": [{"flow_id": "SP_ok_f", "probability": 0.7}, {"flow_id": "SP_ko_f", "probability": 0.3}]}],
    )
    scenario = build_prosimos_scenario(bpmn_xml=bpmn, request=request)
    body = runner.simulate(bpmn.encode(), json.dumps(scenario.payload).encode(), 60, contract_spike.START, 3)

    rows = contract_spike.parse_log((tmp_path / body["LogsFilename"]).read_text(encoding="utf-8"))
    names = {"Ricevi": 60, "Verifica": 300, "Approva": 600, "Rifiuta": 900, "Comunica": 60}
    assert {row["activity"] for row in rows} == set(names)
    night = 16 * 3600
    for row in rows:
        assert round(row["end"] - row["start"] - names[row["activity"]]) % night == 0, row["activity"]
    approved = sum(row["activity"] == "Approva" for row in rows)
    rejected = sum(row["activity"] == "Rifiuta" for row in rows)
    assert approved > rejected > 0


@pytest.mark.parametrize("sequential", [True, False])
def test_a_multi_instance_activity_runs_its_instances_on_the_engine(tmp_path, monkeypatch, sequential):
    # SIM-11f: "firma ognuno dei 3 documenti". In sequenza le firme si
    # susseguono; in parallelo partono insieme su tre persone diverse.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
    from backend.simulation.scenario_builder import build_prosimos_scenario

    sys.path.insert(0, str(ROOT / "ops" / "prosimos" / "runner"))
    import runner

    monkeypatch.setattr(runner, "DATA_DIR", tmp_path)
    loop = f'<bpmn:multiInstanceLoopCharacteristics isSequential="{str(sequential).lower()}"><bpmn:loopCardinality>3</bpmn:loopCardinality></bpmn:multiInstanceLoopCharacteristics>'
    bpmn = normalize_bpmn_for_prosimos(f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D"><bpmn:process id="P" isExecutable="false">
  <bpmn:startEvent id="S" /><bpmn:userTask id="SIGN" name="Firma">{loop}</bpmn:userTask><bpmn:endEvent id="E" />
  <bpmn:sequenceFlow id="f1" sourceRef="S" targetRef="SIGN" /><bpmn:sequenceFlow id="f2" sourceRef="SIGN" targetRef="E" />
</bpmn:process></bpmn:definitions>""")
    # Arrivi ogni due ore esatte: i casi non si contendono le persone, conta solo il parallelismo.
    request = CreateSimulationRunRequest(
        arrival={"mean_seconds": 7200, "distribution": "fixed"},
        resources=[{"id": "r", "name": "Ufficio", "amount": 5, "cost_per_hour": 30}],
        tasks=[{"element_id": "SIGN", "mean_seconds": 600, "distribution": "fixed", "resource_id": "r"}],
    )
    scenario = build_prosimos_scenario(bpmn_xml=bpmn, request=request)
    body = runner.simulate(scenario.bpmn_xml.encode(), json.dumps(scenario.payload).encode(), 20, contract_spike.START, 5)

    rows = contract_spike.parse_log((tmp_path / body["LogsFilename"]).read_text(encoding="utf-8"))
    by_case: dict[str, list[dict]] = {}
    for row in rows:
        assert row["activity"] == "Firma"
        by_case.setdefault(row["case_id"], []).append(row)
    assert len(by_case) == 20 and all(len(signs) == 3 for signs in by_case.values())
    for signs in by_case.values():
        signs.sort(key=lambda r: r["start"])
        if sequential:
            assert all(b["start"] >= a["end"] for a, b in zip(signs, signs[1:], strict=False))
        else:
            assert signs[0]["start"] == signs[2]["start"] and len({r["resource"] for r in signs}) == 3


def test_a_morning_shift_adds_staff_only_in_the_morning():
    # SIM-30: un operatore tutto il giorno, tre in piu' dalle 9 alle 12. Con
    # molti arrivi, il turno lavora solo la mattina e riduce l'attesa.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
    from backend.simulation.scenario_builder import build_prosimos_scenario

    mornings = {"id": "mornings", "name": "Mattine", "periods": [{"from_day": "MONDAY", "to_day": "FRIDAY", "begin": "09:00", "end": "12:00"}]}

    def run(shifts: list[dict]) -> list[dict]:
        request = CreateSimulationRunRequest(
            calendars=[mornings],
            arrival={"mean_seconds": 300, "distribution": "expon"},
            resources=[{"id": "ops", "name": "Operatore", "cost_per_hour": 30, "amount": 1, "shifts": shifts}],
            tasks=[{"element_id": t, "mean_seconds": 600, "distribution": "fixed", "resource_id": "ops"}
                   for t in ("T_receive", "T_approve", "T_pay")],
        )
        bpmn = normalize_bpmn_for_prosimos(contract_spike.BPMN_PATH.read_text(encoding="utf-8"))
        scenario = build_prosimos_scenario(bpmn_xml=bpmn, request=request)
        return _run(_model(), payload=scenario.payload, bpmn=scenario.bpmn_xml)

    from datetime import UTC, datetime

    staffed = run([{"amount": 3, "calendar_id": "mornings"}])
    shift_rows = [row for row in staffed if row["resource"].startswith("Operatore · turno 2")]
    assert shift_rows, "il turno non ha lavorato"
    for row in shift_rows:
        start = datetime.fromtimestamp(row["start"], UTC)
        assert start.weekday() < 5 and 9 <= start.hour < 12, row

    def waiting(rows: list[dict]) -> float:
        return sum(row["start"] - row["enable"] for row in rows) / len(rows)

    assert waiting(staffed) < waiting(run([]))


def test_a_duration_by_amount_thresholds_is_applied_by_the_engine():
    # SIM-32b: Approva dura 5 minuti fino a 1.000 €, 15 fino a 5.000, 25 oltre.
    from backend.schemas.simulation import CreateSimulationRunRequest
    from backend.simulation.bpmn_normalizer import normalize_bpmn_for_prosimos
    from backend.simulation.scenario_builder import build_prosimos_scenario

    # Una risorsa sempre disponibile: la durata nel log e' quella simulata, senza notti di mezzo.
    always = {"id": "always", "name": "Sempre", "periods": [{"from_day": "MONDAY", "to_day": "SUNDAY", "begin": "00:00", "end": "23:59:59"}]}
    request = CreateSimulationRunRequest(
        calendars=[always],
        resources=[{"id": "ops", "name": "Operatore", "cost_per_hour": 30, "amount": 50, "calendar_id": "always"}],
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600, "distribution": "fixed", "resource_id": "ops"},
            {"element_id": "T_approve", "mean_seconds": 1500, "distribution": "fixed", "resource_id": "ops",
             "duration_by": {"attribute": "importo", "variants": [
                 {"up_to": 1000, "mean_seconds": 300, "distribution": "fixed"},
                 {"up_to": 5000, "mean_seconds": 900, "distribution": "fixed"}]}},
            {"element_id": "T_pay", "mean_seconds": 600, "distribution": "fixed", "resource_id": "ops"},
        ],
        model_patch={"case_attributes": [{"name": "importo", "distribution": {"kind": "uniform", "minimum": 100, "maximum": 12000}}]},
        gateways=[{"element_id": "G_split", "branches": [{"flow_id": "F_high", "probability": 1.0}, {"flow_id": "F_low", "probability": 0.0}]}],
    )
    bpmn = normalize_bpmn_for_prosimos(contract_spike.BPMN_PATH.read_text(encoding="utf-8"))
    scenario = build_prosimos_scenario(bpmn_xml=bpmn, request=request)
    rows = _run(_model(), payload=scenario.payload, bpmn=scenario.bpmn_xml)

    seen = {"low": set(), "mid": set(), "high": set()}
    for row in rows:
        if row["activity"] != "Approva":
            continue
        amount = float(row["importo"])
        band = "low" if amount < 1000 else "mid" if amount < 5000 else "high"
        seen[band].add(round(row["end"] - row["start"]))
    assert seen == {"low": {300}, "mid": {900}, "high": {1500}}, seen


def test_the_cases_estimated_for_a_period_cover_it_on_the_engine():
    # SIM-03: due settimane, arrivi ogni 30 minuti lun-ven 9-17. La stima deve
    # far arrivare casi oltre la fine del periodo, senza sprecarne troppi.
    from backend.simulation.horizon import horizon_cases, horizon_end

    model = _model()
    cases = horizon_cases(model, contract_spike.START, 14)
    for seed in (1, 2, 3):
        rows = _run(model, seed, cases=cases)
        arrivals: dict[str, float] = {}
        for row in rows:
            arrivals[row["case_id"]] = min(arrivals.get(row["case_id"], row["enable"]), row["enable"])
        end = horizon_end(contract_spike.START, 14)
        inside = sum(1 for at in arrivals.values() if at < end)
        assert max(arrivals.values()) >= end, "gli arrivi non coprono il periodo"
        # 10 giorni x 8 ore / 30 minuti = 160 arrivi attesi nel periodo.
        assert 130 < inside < 200, inside



def test_sensitivity_variants_move_the_cycle_time_on_the_engine():
    # SIM-25: con lo stesso seed, l'approvazione a +20% allunga l'attraversamento
    # rispetto a -20%, e arrivi piu' fitti (-20% fra due arrivi) lo allungano anch'essi.
    from backend.schemas.simulation import CreateSimulationRunRequest, SensitivityFactor
    from backend.simulation.scenario_builder import build_prosimos_scenario
    from backend.simulation.sensitivity import perturb

    base = CreateSimulationRunRequest(
        arrival_interval_seconds=900,
        resources=[{"id": "ops", "name": "Operatore", "cost_per_hour": 30, "amount": 2},
                   {"id": "appr", "name": "Approvatore", "cost_per_hour": 60, "amount": 1}],
        tasks=[
            {"element_id": "T_receive", "mean_seconds": 600, "resource_id": "ops"},
            {"element_id": "T_approve", "mean_seconds": 1500, "resource_id": "appr"},
            {"element_id": "T_pay", "mean_seconds": 600, "resource_id": "ops"},
        ],
    )
    bpmn = contract_spike.BPMN_PATH.read_text(encoding="utf-8")

    def cycle(request) -> float:
        rows = _run(_model(), seed=11, payload=build_prosimos_scenario(bpmn_xml=bpmn, request=request).payload)
        cases: dict[str, list[float]] = {}
        for row in rows:
            span = cases.setdefault(row["case_id"], [row["start"], row["end"]])
            span[0], span[1] = min(span[0], row["start"]), max(span[1], row["end"])
        return sum(end - start for start, end in cases.values()) / len(cases)

    approve = SensitivityFactor(kind="duration", element_id="T_approve", label="Approva")
    arrivals = SensitivityFactor(kind="arrival")
    assert cycle(perturb(base, approve, "high", 0.2)) > cycle(perturb(base, approve, "low", 0.2))
    assert cycle(perturb(base, arrivals, "low", 0.2)) > cycle(perturb(base, arrivals, "high", 0.2))
