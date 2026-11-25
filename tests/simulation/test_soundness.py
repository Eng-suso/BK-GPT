"""VAL-01: all'import un processo in cui qualche caso non finirebbe si rifiuta.

Meta (PLAN.md): nessun deadlock ne' livelock, fine raggiungibile da ogni stato,
uscita da ogni ciclo con probabilita' > 0 e numero atteso di ripetizioni finito;
lo scenario SIMOD di AcademicCredentials con il ciclo a uscita 0 (G3) e'
rifiutato; i 19 scenari di ``datasets/extraneous-delays/inputs`` e gli scenari
SIMOD validi di G3 passano; il messaggio e' in linguaggio di business.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from backend.simulation.ir.from_prosimos import UnsoundProcessError, import_prosimos
from backend.simulation.ir.model import (
    Activity,
    Arrival,
    Assignment,
    Branch,
    Calendar,
    CaseAttribute,
    CalendarPeriod,
    Condition,
    Fixed,
    Gateway,
    Resource,
    ResourcePool,
    Rule,
    SimulationModel,
)
from backend.simulation.ir.soundness import MAX_TOKENS_PER_FLOW, check_soundness

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "datasets" / "extraneous-delays" / "inputs"
G3 = ROOT / "tests" / "simulation" / "benchmark" / "g3" / "discovered"
SCENARIOS = sorted(path.with_suffix("") for path in INPUTS.rglob("*.json") if path.with_suffix(".bpmn").exists())
# G3: SIMOD lascia su AcademicCredentials un ciclo con uscita 0 (fissi e FUZZY);
# le diagnosi "-loopfix" lo riaprono alla frequenza del train.
G3_DEAD_LOOP = {"AcademicCredentials_diff", "AcademicCredentials_fuzz"}
G3_SCENARIOS = sorted(path.name for path in G3.iterdir() if path.is_dir())
DEAD_LOOP_GATEWAY = "node_59fc62b1-3b4e-4c11-ba7b-1cab3392cdaa"
# Cio' che il consulente non deve leggere nel percorso ordinario.
JARGON = re.compile(r"node[_-]|sid-|gateway|token|gettoni|deadlock|livelock|BPMN|JSON|Prosimos", re.IGNORECASE)


def _g3(name: str) -> tuple[dict, str]:
    log = name.rsplit("_", 1)[0]
    folder = G3 / name
    scenario = json.loads((folder / f"{log}.json").read_text(encoding="utf-8"))
    return scenario, (folder / f"{log}.bpmn").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# La meta sui dati
# --------------------------------------------------------------------------- #


def test_the_dataset_has_the_nineteen_scenarios_and_the_g3_ones() -> None:
    assert len(SCENARIOS) == 19
    assert G3_DEAD_LOOP < set(G3_SCENARIOS)
    assert len(G3_SCENARIOS) == 10


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda path: path.name)
def test_every_dataset_scenario_can_always_finish(path: Path) -> None:
    scenario = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    bpmn = path.with_suffix(".bpmn").read_text(encoding="utf-8")
    model = import_prosimos(scenario, bpmn).model

    report = check_soundness(model, bpmn)

    assert report.ok and report.complete
    assert report.expected_executions, "con probabilita' note le ripetizioni attese si calcolano"
    assert all(math.isfinite(value) and value > 0 for value in report.expected_executions.values())


@pytest.mark.parametrize("name", sorted(set(G3_SCENARIOS) - G3_DEAD_LOOP))
def test_the_valid_g3_simod_scenarios_pass(name: str) -> None:
    scenario, bpmn = _g3(name)

    result = import_prosimos(scenario, bpmn)

    report = check_soundness(result.model, bpmn)
    assert report.ok and report.complete
    assert report.expected_executions is not None
    assert all(math.isfinite(value) for value in report.expected_executions.values())


@pytest.mark.parametrize("name", sorted(G3_DEAD_LOOP))
def test_the_g3_dead_loop_on_academic_credentials_is_refused(name: str) -> None:
    scenario, bpmn = _g3(name)

    with pytest.raises(UnsoundProcessError) as refused:
        import_prosimos(scenario, bpmn)

    (problem,) = refused.value.problems
    assert problem.kind == "livelock"
    assert problem.element_ids == (DEAD_LOOP_GATEWAY,)
    assert "«Avanzar recepcion documentos»" in problem.message
    assert "probabilità 0" in problem.message
    assert "probabilità maggiore di zero" in problem.action
    assert DEAD_LOOP_GATEWAY in refused.value.detail


@pytest.mark.parametrize("name", sorted(G3_DEAD_LOOP))
def test_the_consultant_reads_no_jargon(name: str) -> None:
    scenario, bpmn = _g3(name)

    with pytest.raises(UnsoundProcessError) as refused:
        import_prosimos(scenario, bpmn)

    assert not JARGON.search(refused.value.message), refused.value.message


def test_the_loop_reopened_at_the_train_frequency_repeats_a_finite_number_of_times() -> None:
    scenario, bpmn = _g3("AcademicCredentials_diff-loopfix")
    model = import_prosimos(scenario, bpmn).model

    report = check_soundness(model, bpmn)

    assert report.ok
    assert report.expected_executions is not None
    assert max(report.expected_executions.values()) < 2


# --------------------------------------------------------------------------- #
# Processi piccoli con la risposta nota
# --------------------------------------------------------------------------- #

_TAGS = {"S": "startEvent", "E": "endEvent", "T": "endEvent"}


def _bpmn(nodes: dict[str, str], flows: list[tuple[str, str, str]], *, names: dict[str, str] | None = None) -> str:
    """Un BPMN con ``nodes`` (id -> tag) e ``flows`` (id, da, a)."""
    names = names or {}
    body = []
    for node, tag in nodes.items():
        name = f' name="{names[node]}"' if node in names else ""
        inner = "<terminateEventDefinition/>" if node == "T" else ""
        body.append(f'<{tag} id="{node}"{name}>{inner}</{tag}>')
    body += [f'<sequenceFlow id="{fid}" sourceRef="{src}" targetRef="{dst}"/>' for fid, src, dst in flows]
    return (
        '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"><process id="p">'
        + "".join(body)
        + "</process></definitions>"
    )


OFFICE = Calendar(id="office", name="Ufficio", periods=(
    CalendarPeriod(from_day="MONDAY", to_day="FRIDAY", begin="09:00:00", end="17:00:00"),
))


def _model(
    activities: list[str], gateways: tuple[Gateway, ...] = (), attributes: tuple[CaseAttribute, ...] = ()
) -> SimulationModel:
    return SimulationModel(
        arrival=Arrival(interarrival=Fixed(value=600), calendar_id="office"),
        calendars=(OFFICE,),
        pools=(ResourcePool(id="p", name="Ufficio", resources=(
            Resource(id="ops", name="Operatore", cost_per_hour=30, amount=1, calendar_id="office"),
        )),),
        activities=tuple(
            Activity(element_id=a, assignments=(Assignment(resource_id="ops", duration=Fixed(value=60)),))
            for a in activities
        ),
        gateways=gateways,
        case_attributes=attributes,
    )


def _choice(gateway: str, **probabilities: float) -> Gateway:
    return Gateway(
        element_id=gateway,
        branches=tuple(Branch(flow_id=flow, probability=p) for flow, p in probabilities.items()),
    )


# S -> M (unione) -> A -> G: torna a M (f_back) o va alla fine (f_exit)
LOOP_NODES = {"S": "startEvent", "M": "exclusiveGateway", "A": "task", "G": "exclusiveGateway", "E": "endEvent"}
LOOP_FLOWS = [("f1", "S", "M"), ("f2", "M", "A"), ("f3", "A", "G"), ("f_back", "G", "M"), ("f_exit", "G", "E")]
LOOP_BPMN = _bpmn(LOOP_NODES, LOOP_FLOWS, names={"A": "Verifica documenti"})


def test_a_loop_with_an_exit_repeats_the_geometric_number_of_times() -> None:
    report = check_soundness(_model(["A"], (_choice("G", f_back=0.75, f_exit=0.25),)), LOOP_BPMN)

    assert report.ok
    assert report.expected_executions == {"A": pytest.approx(4.0)}


def test_a_loop_whose_exit_has_probability_zero_is_a_livelock_named_by_the_activity() -> None:
    report = check_soundness(_model(["A"], (_choice("G", f_back=1.0, f_exit=0.0),)), LOOP_BPMN)

    (problem,) = report.problems
    assert problem.kind == "livelock"
    assert problem.element_ids == ("G",)
    assert "«Verifica documenti»" in problem.message
    assert "f_exit" in problem.detail
    assert report.expected_executions is None


def test_a_loop_without_any_exit_in_the_drawing_is_a_livelock() -> None:
    nodes = {"S": "startEvent", "M": "exclusiveGateway", "A": "task", "B": "task", "E": "endEvent"}
    flows = [("f1", "S", "M"), ("f2", "M", "A"), ("f3", "A", "B"), ("f4", "B", "M")]
    report = check_soundness(_model(["A", "B"]), _bpmn(nodes, flows, names={"A": "Controllo", "B": "Ricontrollo"}))

    (problem,) = report.problems
    assert problem.kind == "livelock"
    assert "«Controllo»" in problem.message


def test_a_parallel_join_after_an_exclusive_choice_is_a_deadlock() -> None:
    nodes = {"S": "startEvent", "X": "exclusiveGateway", "A": "task", "B": "task", "J": "parallelGateway",
             "C": "task", "E": "endEvent"}
    flows = [("f1", "S", "X"), ("fa", "X", "A"), ("fb", "X", "B"), ("f2", "A", "J"), ("f3", "B", "J"),
             ("f4", "J", "C"), ("f5", "C", "E")]
    bpmn = _bpmn(nodes, flows, names={"A": "Approva", "B": "Rifiuta", "C": "Archivia"})

    report = check_soundness(_model(["A", "B", "C"], (_choice("X", fa=0.5, fb=0.5),)), bpmn)

    (problem,) = report.problems
    assert problem.kind == "deadlock"
    assert problem.element_ids == ("J",)
    assert "aspetta che arrivino tutti i percorsi" in problem.message


def test_a_parallel_split_and_join_is_sound() -> None:
    nodes = {"S": "startEvent", "P": "parallelGateway", "A": "task", "B": "task", "J": "parallelGateway",
             "E": "endEvent"}
    flows = [("f1", "S", "P"), ("fa", "P", "A"), ("fb", "P", "B"), ("f2", "A", "J"), ("f3", "B", "J"),
             ("f4", "J", "E")]

    report = check_soundness(_model(["A", "B"]), _bpmn(nodes, flows))

    assert report.ok
    assert report.expected_executions == {"A": pytest.approx(1.0), "B": pytest.approx(1.0)}


def test_parallel_paths_that_restart_without_joining_multiply_the_work() -> None:
    # S -> M -> P (parallela): un ramo aspetta in J, l'altro decide se ripartire da M.
    nodes = {"S": "startEvent", "M": "exclusiveGateway", "P": "parallelGateway", "A": "task",
             "G": "exclusiveGateway", "J": "parallelGateway", "E": "endEvent"}
    flows = [("f1", "S", "M"), ("f2", "M", "P"), ("fw", "P", "J"), ("fa", "P", "A"), ("f3", "A", "G"),
             ("f_back", "G", "M"), ("f_join", "G", "J"), ("f4", "J", "E")]
    bpmn = _bpmn(nodes, flows, names={"A": "Lavora"})

    report = check_soundness(_model(["A"], (_choice("G", f_back=0.5, f_join=0.5),)), bpmn)

    assert "unbounded" in {problem.kind for problem in report.problems}
    unbounded = next(p for p in report.problems if p.kind == "unbounded")
    assert "fw" in unbounded.element_ids
    assert str(MAX_TOKENS_PER_FLOW) in unbounded.detail


def test_a_process_without_a_start_is_refused() -> None:
    report = check_soundness(_model(["A"]), _bpmn({"A": "task", "E": "endEvent"}, [("f1", "A", "E")]))

    assert [problem.kind for problem in report.problems] == ["no_start"]


def test_a_terminate_end_closes_the_parallel_work_still_open() -> None:
    nodes = {"S": "startEvent", "P": "parallelGateway", "A": "task", "B": "task", "T": "endEvent", "W": "task"}
    flows = [("f1", "S", "P"), ("fa", "P", "A"), ("fb", "P", "B"), ("f2", "A", "T"), ("f3", "B", "W")]
    # W non ha uscita: il suo percorso finisce li'. T chiude tutto quello che e' ancora aperto.
    report = check_soundness(_model(["A", "B", "W"]), _bpmn(nodes, flows))

    assert report.ok


def test_a_decision_by_rule_may_take_every_branch_and_has_no_expected_count() -> None:
    rule = Condition(any_of=((Rule(attribute="importo", operator=">", value=1000),),))
    other = Condition(any_of=((Rule(attribute="importo", operator="<=", value=1000),),))
    gateway = Gateway(element_id="G", branches=(
        Branch(flow_id="f_back", probability=1.0, condition=rule),
        Branch(flow_id="f_exit", probability=0.0, condition=other),
    ))

    amount = CaseAttribute(name="importo", distribution=Fixed(value=500))

    report = check_soundness(_model(["A"], (gateway,), (amount,)), LOOP_BPMN)

    assert report.ok
    assert report.expected_executions is None


def test_an_inclusive_split_and_join_is_sound() -> None:
    nodes = {"S": "startEvent", "O": "inclusiveGateway", "A": "task", "B": "task", "J": "inclusiveGateway",
             "E": "endEvent"}
    flows = [("f1", "S", "O"), ("fa", "O", "A"), ("fb", "O", "B"), ("f2", "A", "J"), ("f3", "B", "J"),
             ("f4", "J", "E")]

    report = check_soundness(_model(["A", "B"], (_choice("O", fa=0.6, fb=0.4),)), _bpmn(nodes, flows))

    assert report.ok
    assert report.expected_executions is None  # Prosimos non documenta come combina i rami


def test_the_import_keeps_the_old_message_text_for_existing_callers() -> None:
    """``str()`` dell'errore resta il motivo leggibile, come per ogni ProsimosImportError."""
    scenario, bpmn = _g3("AcademicCredentials_diff")

    with pytest.raises(UnsoundProcessError) as refused:
        import_prosimos(scenario, bpmn)

    assert str(refused.value).startswith("I casi che arrivano a «Avanzar recepcion documentos»")
    assert "Cosa fare:" in str(refused.value)
