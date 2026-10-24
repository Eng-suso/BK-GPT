"""BEF4LLM dice il vero, e il compilatore di DeliR esce sempre valido.

Prima le metriche, su modelli scritti a mano con risposte note: il gruppo di
una soglia, un join che manca, un pool senza processo, un'etichetta cambiata,
un ordine invertito. Poi l'invariante che il paper usa come cancello: un BPMN
che DeliR compila passa lo schema XSD di BPMN 2.0, sempre.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.process_understanding import ProcessUnderstanding
from tests.evals.bef4llm import (
    PRAGMATIC_THRESHOLDS,
    evaluate,
    normalize,
    optimal_assignment,
    parse,
    pragmatic_values,
    semantic_label_similarity,
    syntactic_label_similarity,
    syntactic_metrics,
    validity,
)

GOLDEN = Path(__file__).resolve().parents[2] / "golden"


def _bpmn(nodes: list[tuple[str, str, str]], flows: list[tuple[str, str]], extra: str = "", pools: str = "") -> str:
    """Un BPMN minimo: `nodes` sono (tag, id, nome), `flows` gli archi di sequenza."""
    elements = "".join(f'<bpmn:{tag} id="{node_id}" name="{name}"/>' for tag, node_id, name in nodes)
    arcs = "".join(
        f'<bpmn:sequenceFlow id="F_{source}_{target}" sourceRef="{source}" targetRef="{target}"/>'
        for source, target in flows
    )
    return (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
        'id="D" targetNamespace="https://example.test">'
        f"{pools}"
        f'<bpmn:process id="P" isExecutable="false">{elements}{arcs}{extra}</bpmn:process>'
        "</bpmn:definitions>"
    )


def _xor_diamond(join: bool = True) -> str:
    nodes = [
        ("startEvent", "s", "Start"),
        ("userTask", "a", "Ricevi ordine"),
        ("exclusiveGateway", "g", "Ordine completo?"),
        ("userTask", "b", "Approva ordine"),
        ("userTask", "c", "Respingi ordine"),
        ("endEvent", "e", "Fine"),
    ]
    if join:
        nodes.append(("exclusiveGateway", "j", ""))
        flows = [("s", "a"), ("a", "g"), ("g", "b"), ("g", "c"), ("b", "j"), ("c", "j"), ("j", "e")]
    else:
        flows = [("s", "a"), ("a", "g"), ("g", "b"), ("g", "c"), ("b", "e"), ("c", "e")]
    return _bpmn(nodes, flows)


# --- normalizzazione (equazioni 1 e 2) ----------------------------------------


def test_the_papers_own_example_lands_in_the_third_group():
    direction, thresholds = PRAGMATIC_THRESHOLDS["tnn"]
    assert normalize(45, direction, thresholds) == 0.5


@pytest.mark.parametrize(
    ("value", "expected"), [(10, 1.0), (29.9, 0.75), (50, 0.5), (60, 0.25), (81.1, 0.0), (500, 0.0)]
)
def test_less_is_better_walks_down_the_groups(value, expected):
    assert normalize(value, "desc", (29.9, 43.7, 58.1, 81.1)) == expected


def test_more_is_better_is_the_mirror():
    thresholds = (0.03, 0.37, 0.71, 1.24)
    assert normalize(0.0, "asc", thresholds) == 0.0
    assert normalize(2.0, "asc", thresholds) == 1.0
    assert normalize(0.5, "asc", thresholds) == 0.5


# --- validita' ------------------------------------------------------------------


def test_unreadable_xml_is_invalid_and_nothing_else_is_scored():
    report = evaluate("<bpmn:definitions")
    assert report.q_val == 0.0
    assert report.errors
    assert report.q_syn is None and report.q_prag is None
    assert report.q_total == 0.0


def test_an_element_bpmn_does_not_know_fails_the_schema():
    xml = _xor_diamond().replace('<bpmn:userTask id="b"', '<bpmn:wish id="b"').replace(
        '</bpmn:userTask', '</bpmn:wish'
    )
    score, errors = validity(xml)
    assert score == 0.0
    assert any("wish" in error for error in errors)


def test_a_well_formed_model_passes_the_schema():
    assert validity(_xor_diamond()) == (1.0, [])


# --- qualita' sintattica ----------------------------------------------------------


def test_a_block_structured_model_follows_every_rule():
    metrics = syntactic_metrics(parse(_xor_diamond(join=True)))
    assert set(metrics.values()) == {1.0}, metrics


def test_branches_merged_in_the_end_event_break_two_rules():
    metrics = syntactic_metrics(parse(_xor_diamond(join=False)))
    assert metrics["end_degree"] == 0.0
    assert metrics["split_has_join"] == 0.0
    assert metrics["sequence_flow_rules"] == 1.0


def test_a_join_of_another_type_is_not_a_match():
    xml = _xor_diamond(join=True).replace('<bpmn:exclusiveGateway id="j"', '<bpmn:parallelGateway id="j"')
    assert syntactic_metrics(parse(xml))["split_has_join"] == 0.0


def test_a_missing_label_and_a_second_start_are_counted():
    xml = _bpmn(
        [
            ("startEvent", "s1", "Start"),
            ("startEvent", "s2", "Altro start"),
            ("userTask", "a", ""),
            ("userTask", "b", "Chiudi"),
            ("endEvent", "e", "Fine"),
        ],
        [("s1", "a"), ("s2", "b"), ("a", "b"), ("b", "e")],
    )
    metrics = syntactic_metrics(parse(xml))
    assert metrics["tasks_labelled"] == 0.5
    assert metrics["one_start_per_process"] == 0.0
    assert metrics["task_degree"] == 0.5


def test_a_flow_out_of_an_end_event_breaks_the_connection_rules():
    xml = _bpmn(
        [("startEvent", "s", "Start"), ("userTask", "a", "Lavora"), ("endEvent", "e", "Fine")],
        [("s", "a"), ("a", "e"), ("e", "a")],
    )
    assert syntactic_metrics(parse(xml))["sequence_flow_rules"] == pytest.approx(2 / 3, abs=1e-4)


def test_a_black_box_pool_has_no_process_and_counts_against_the_rule():
    pools = (
        '<bpmn:collaboration id="C">'
        '<bpmn:participant id="Interno" processRef="P"/>'
        '<bpmn:participant id="Fornitore"/>'
        '<bpmn:messageFlow id="M1" sourceRef="a" targetRef="Fornitore"/>'
        '<bpmn:messageFlow id="M2" sourceRef="a" targetRef="Interno"/>'
        "</bpmn:collaboration>"
    )
    xml = _bpmn(
        [("startEvent", "s", "Start"), ("sendTask", "a", "Invia ordine"), ("endEvent", "e", "Fine")],
        [("s", "a"), ("a", "e")],
        pools=pools,
    )
    metrics = syntactic_metrics(parse(xml))
    assert metrics["one_process_per_pool"] == 0.5
    # verso un altro pool si', dentro il proprio pool no
    assert metrics["message_flow_rules"] == 0.5


def test_a_boundary_event_has_no_incoming_flow_and_one_outgoing():
    xml = _bpmn(
        [
            ("startEvent", "s", "Start"),
            ("userTask", "a", "Attendi risposta"),
            ("endEvent", "e", "Fine"),
            ("endEvent", "late", "Scaduto"),
        ],
        [("s", "a"), ("a", "e"), ("t", "late")],
        extra='<bpmn:boundaryEvent id="t" name="48 ore" attachedToRef="a"><bpmn:timerEventDefinition/></bpmn:boundaryEvent>',
    )
    metrics = syntactic_metrics(parse(xml))
    assert metrics["exception_degree"] == 1.0
    assert metrics["task_degree"] == 1.0


# --- qualita' pragmatica ----------------------------------------------------------


def test_raw_measures_of_a_small_diamond():
    values = pragmatic_values(parse(_xor_diamond(join=True)))
    assert values["tnn"] == 7
    assert values["tng"] == 2
    assert values["tnsf"] == 7
    assert values["diameter"] == 6  # s, a, g, b, j, e
    assert values["density"] == pytest.approx(7 / 42)
    assert values["agd"] == 3.0
    assert values["cnc"] == 1.0
    assert values["gh"] == 0.0  # un tipo solo
    assert values["cfc"] == 2  # XOR con due uscite
    assert values["token_split"] == 0
    assert values["depth"] == 1  # b e c stanno dentro lo split
    assert values["sequentiality"] == pytest.approx(1 / 7)  # solo s->a non tocca un gateway


def test_an_inclusive_split_weighs_two_to_the_n_minus_one():
    xml = _bpmn(
        [
            ("startEvent", "s", "Start"),
            ("inclusiveGateway", "g", "Quali controlli?"),
            ("userTask", "a", "Controllo A"),
            ("userTask", "b", "Controllo B"),
            ("userTask", "c", "Controllo C"),
            ("inclusiveGateway", "j", ""),
            ("endEvent", "e", "Fine"),
        ],
        [("s", "g"), ("g", "a"), ("g", "b"), ("g", "c"), ("a", "j"), ("b", "j"), ("c", "j"), ("j", "e")],
    )
    values = pragmatic_values(parse(xml))
    assert values["cfc"] == 7
    assert values["token_split"] == 2


def test_mixed_gateway_types_raise_heterogeneity():
    xml = _xor_diamond(join=True).replace(
        '<bpmn:exclusiveGateway id="j"', '<bpmn:parallelGateway id="j"'
    ).replace('</bpmn:exclusiveGateway><bpmn:endEvent', '</bpmn:parallelGateway><bpmn:endEvent')
    values = pragmatic_values(parse(xml))
    assert values["gh"] == pytest.approx(-2 * 0.5 * __import__("math").log(0.5, 3))


def test_every_inner_node_of_a_chain_is_a_cut_vertex():
    xml = _bpmn(
        [("startEvent", "s", "Start"), ("userTask", "a", "Uno"), ("userTask", "b", "Due"), ("endEvent", "e", "Fine")],
        [("s", "a"), ("a", "b"), ("b", "e")],
    )
    values = pragmatic_values(parse(xml))
    assert values["separability"] == 1.0
    # pesi tutti 1: ogni coppia ordinata raggiungibile vale 1, 6 su 12
    assert values["cc"] == pytest.approx(6 / 12)


def test_a_loop_does_not_make_the_diameter_infinite():
    xml = _bpmn(
        [
            ("startEvent", "s", "Start"),
            ("exclusiveGateway", "m", ""),
            ("userTask", "a", "Correggi"),
            ("exclusiveGateway", "g", "Corretto?"),
            ("endEvent", "e", "Fine"),
        ],
        [("s", "m"), ("m", "a"), ("a", "g"), ("g", "m"), ("g", "e")],
    )
    assert pragmatic_values(parse(xml))["diameter"] == 5


# --- qualita' semantica -----------------------------------------------------------


def test_label_similarities_behave():
    assert syntactic_label_similarity("Approva ordine", "approva ordine") == 1.0
    assert syntactic_label_similarity("abc", "abd") == pytest.approx(2 / 3)
    assert semantic_label_similarity("Approva l'ordine", "Ordini approvati") == 1.0
    assert semantic_label_similarity("Approva ordine", "Spedisci merce") == 0.0


def test_the_assignment_is_optimal_not_greedy():
    # greedy prenderebbe (0,0)=0.9 e poi (1,1)=0.1: totale 1.0; l'ottimo e' 0.8+0.8
    pairs = optimal_assignment([[0.9, 0.8], [0.8, 0.1]])
    assert sorted(pairs) == [(0, 1), (1, 0)]


def test_a_model_is_semantically_identical_to_itself():
    xml = _xor_diamond()
    assert set(evaluate(xml, reference_xml=xml).semantic.values()) == {1.0}


def test_a_missing_activity_lowers_every_semantic_measure():
    reference = _xor_diamond()
    candidate = _bpmn(
        [
            ("startEvent", "s", "Start"),
            ("userTask", "a", "Ricevi ordine"),
            ("exclusiveGateway", "g", "Ordine completo?"),
            ("userTask", "b", "Approva ordine"),
            ("exclusiveGateway", "j", ""),
            ("endEvent", "e", "Fine"),
        ],
        [("s", "a"), ("a", "g"), ("g", "b"), ("g", "j"), ("b", "j"), ("j", "e")],
    )
    semantic = evaluate(candidate, reference_xml=reference).semantic
    assert all(score < 1.0 for score in semantic.values()), semantic


def test_a_reversed_order_keeps_the_labels_and_loses_the_behaviour():
    nodes = [
        ("startEvent", "s", "Start"),
        ("userTask", "a", "Ricevi ordine"),
        ("userTask", "b", "Spedisci merce"),
        ("endEvent", "e", "Fine"),
    ]
    reference = _bpmn(nodes, [("s", "a"), ("a", "b"), ("b", "e")])
    candidate = _bpmn(nodes, [("s", "b"), ("b", "a"), ("a", "e")])
    semantic = evaluate(candidate, reference_xml=reference).semantic
    assert semantic["syntactic_label_similarity"] == 1.0
    assert semantic["semantic_label_similarity"] == 1.0
    assert semantic["dependency_graph_overlap"] < 1.0
    assert semantic["causal_footprint_overlap"] < 1.0
    assert semantic["context_similarity"] < 1.0


def test_an_invalid_reference_is_refused_not_scored():
    with pytest.raises(ValueError):
        evaluate(_xor_diamond(), reference_xml="<nope")


def test_every_score_stays_inside_zero_one():
    report = evaluate(_xor_diamond(join=False), reference_xml=_xor_diamond())
    scores = [*report.syntactic.values(), *report.pragmatic.values(), *report.semantic.values()]
    assert all(0.0 <= score <= 1.0 for score in scores)
    for aggregate in (report.q_syn, report.q_prag, report.q_sem, report.q_qual, report.q_total):
        assert aggregate is not None and 0.0 <= aggregate <= 1.0


# --- il compilatore di DeliR -------------------------------------------------------


def _golden_plans() -> list[Path]:
    return sorted(path for path in GOLDEN.glob("*/ideal_plan.json"))


@pytest.mark.parametrize("plan_path", _golden_plans(), ids=lambda path: path.parent.name)
def test_the_compiler_always_emits_schema_valid_bpmn(plan_path: Path):
    """Il cancello di BEF4LLM: senza XML valido nessun altro punteggio esiste."""
    plan = ProcessUnderstanding.model_validate(json.loads(plan_path.read_text(encoding="utf-8")))
    model = build_bpmn_semantic_model(
        process_id=f"Process_{plan_path.parent.name}", process_name=plan_path.parent.name, process=plan
    )
    report = evaluate(semantic_model_to_bpmn_xml(model))
    assert report.q_val == 1.0, report.errors[:5]
    assert report.q_syn is not None and report.q_prag is not None
