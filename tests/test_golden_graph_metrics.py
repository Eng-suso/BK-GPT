"""Le metriche del golden set, e il compilatore misurato con quelle metriche.

Due cose diverse in un file solo, perche' la seconda ha senso solo se la prima
e' vera:

1. **le metriche dicono il vero** - su grafi scritti a mano, con risposte note:
   un'attivita' mancante abbassa il recall, una in piu' la precision, un ordine
   invertito i flussi, un elemento vietato rende il modello disonesto;
2. **dal piano al disegno non si perde niente** - un piano che rispecchia il
   riferimento, passato dal compilatore vero, deve tornare con attivita', corsie
   e ordine interi. E' il tratto della catena che puo' essere corretto al 100%,
   e qui si verifica che lo sia.

Il tratto che non puo' esserlo - dalle interviste al piano - si misura con l'LLM
vero in `tests/evals/test_golden_set.py`, spento di default.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.bpmn import build_bpmn_semantic_model, semantic_model_to_bpmn_xml
from backend.process_understanding import (
    ProcessDecision,
    ProcessDecisionOutcome,
    ProcessPath,
    ProcessStep,
    ProcessUnderstanding,
)
from tests.evals.graph_metrics import (
    ReferenceActivity,
    ReferenceCase,
    compare,
    label_score,
    load_golden_cases,
    parse_bpmn,
    regressions,
)

GOLDEN = Path(__file__).parent / "golden"


def _case(**overrides) -> ReferenceCase:
    data = {
        "case_id": "mini",
        "status": "validated",
        "process_name": "Mini",
        "sources": [],
        "lanes": {"tecnico": ["ufficio tecnico"], "acquisti": ["acquisti"]},
        "activities": [
            ReferenceActivity(id="apri_richiesta", aliases=["apri richiesta"], lane="tecnico"),
            ReferenceActivity(id="verifica_richiesta", aliases=["verifica richiesta"], lane="acquisti"),
            ReferenceActivity(id="emetti_ordine", aliases=["emetti ordine"], lane="acquisti"),
        ],
        "gateways": {"completa": ["richiesta completa"]},
        "edges": [("apri_richiesta", "verifica_richiesta"), ("verifica_richiesta", "emetti_ordine")],
        "forbidden": [{"aliases": ["firma direttore"], "why": "inventato"}],
        "open_gaps": [],
        "root": GOLDEN,
    }
    data.update(overrides)
    return ReferenceCase(**data)


def _xml(tasks: list[tuple[str, str, str]], flows: list[tuple[str, str]], gateways=()) -> str:
    lanes: dict[str, list[str]] = {}
    for task_id, _name, lane in tasks:
        lanes.setdefault(lane, []).append(task_id)
    lane_xml = "".join(
        f'<bpmn:lane id="L{index}" name="{name}">'
        + "".join(f"<bpmn:flowNodeRef>{ref}</bpmn:flowNodeRef>" for ref in refs)
        + "</bpmn:lane>"
        for index, (name, refs) in enumerate(lanes.items())
    )
    task_xml = "".join(f'<bpmn:userTask id="{task_id}" name="{name}"/>' for task_id, name, _ in tasks)
    gateway_xml = "".join(f'<bpmn:exclusiveGateway id="{gid}" name="{name}"/>' for gid, name in gateways)
    flow_xml = "".join(
        f'<bpmn:sequenceFlow id="F{index}" sourceRef="{source}" targetRef="{target}"/>'
        for index, (source, target) in enumerate(flows)
    )
    return (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D">'
        f'<bpmn:process id="P"><bpmn:laneSet id="LS">{lane_xml}</bpmn:laneSet>'
        f'<bpmn:startEvent id="S"/>{task_xml}{gateway_xml}<bpmn:endEvent id="E"/>{flow_xml}'
        "</bpmn:process></bpmn:definitions>"
    )


PERFECT = _xml(
    [
        ("t1", "Apri la richiesta di acquisto", "Ufficio Tecnico"),
        ("t2", "Verifica la richiesta", "Acquisti"),
        ("t3", "Emetti l'ordine al fornitore", "Acquisti"),
    ],
    [("S", "t1"), ("t1", "t2"), ("t2", "g1"), ("g1", "t3"), ("t3", "E")],
    gateways=[("g1", "Richiesta completa?")],
)


# --- le metriche dicono il vero --------------------------------------------


def test_a_faithful_drawing_scores_full_marks():
    metrics = compare(parse_bpmn(PERFECT), _case())

    assert metrics.activity_precision == 1.0
    assert metrics.activity_recall == 1.0
    assert metrics.lane_accuracy == 1.0
    assert metrics.gateway_recall == 1.0
    # L'ordine passa attraverso il gateway: un punto di decisione non e' un
    # passaggio di lavoro, e "viene dopo" lo attraversa.
    assert metrics.edge_recall == 1.0
    assert metrics.edge_precision == 1.0
    assert metrics.honest


def test_a_missing_activity_lowers_recall_not_precision():
    xml = _xml(
        [("t1", "Apri richiesta", "Ufficio Tecnico"), ("t3", "Emetti ordine", "Acquisti")],
        [("S", "t1"), ("t1", "t3"), ("t3", "E")],
    )

    metrics = compare(parse_bpmn(xml), _case())

    assert metrics.activity_recall == pytest.approx(2 / 3, abs=0.001)
    assert metrics.activity_precision == 1.0
    assert metrics.missing_activities == ["verifica_richiesta"]


def test_an_invented_activity_lowers_precision_not_recall():
    xml = _xml(
        [
            ("t1", "Apri richiesta", "Ufficio Tecnico"),
            ("t2", "Verifica richiesta", "Acquisti"),
            ("t3", "Emetti ordine", "Acquisti"),
            ("t4", "Pianifica audit trimestrale", "Acquisti"),
        ],
        [("S", "t1"), ("t1", "t2"), ("t2", "t3"), ("t3", "t4"), ("t4", "E")],
    )

    metrics = compare(parse_bpmn(xml), _case())

    assert metrics.activity_recall == 1.0
    assert metrics.activity_precision == 0.75
    assert "Pianifica audit trimestrale" in metrics.extra_activities


def test_the_wrong_lane_is_counted():
    xml = _xml(
        [
            ("t1", "Apri richiesta", "Acquisti"),
            ("t2", "Verifica richiesta", "Acquisti"),
            ("t3", "Emetti ordine", "Acquisti"),
        ],
        [("S", "t1"), ("t1", "t2"), ("t2", "t3"), ("t3", "E")],
    )

    metrics = compare(parse_bpmn(xml), _case())

    assert metrics.lane_accuracy == pytest.approx(2 / 3, abs=0.001)


def test_a_reversed_order_is_caught_both_ways():
    xml = _xml(
        [
            ("t1", "Apri richiesta", "Ufficio Tecnico"),
            ("t2", "Verifica richiesta", "Acquisti"),
            ("t3", "Emetti ordine", "Acquisti"),
        ],
        [("S", "t1"), ("t1", "t3"), ("t3", "t2"), ("t2", "E")],
    )

    metrics = compare(parse_bpmn(xml), _case())

    assert metrics.edge_recall == 0.0
    assert metrics.edge_precision == 0.0


def test_a_forbidden_element_makes_the_model_dishonest():
    xml = _xml(
        [
            ("t1", "Apri richiesta", "Ufficio Tecnico"),
            ("t2", "Verifica richiesta", "Acquisti"),
            ("t9", "Raccogli firma del direttore", "Acquisti"),
            ("t3", "Emetti ordine", "Acquisti"),
        ],
        [("S", "t1"), ("t1", "t2"), ("t2", "t9"), ("t9", "t3"), ("t3", "E")],
    )

    metrics = compare(parse_bpmn(xml), _case())

    assert not metrics.honest
    assert any("direttore" in hit for hit in metrics.forbidden_hits)


def test_one_produced_activity_cannot_satisfy_two_reference_activities():
    """Un'etichetta vaga non conta due volte."""
    xml = _xml(
        [("t1", "Richiesta: apri e verifica", "Acquisti")],
        [("S", "t1"), ("t1", "E")],
    )

    metrics = compare(parse_bpmn(xml), _case())

    assert len(metrics.matches) <= 1


def test_labels_match_across_inflection():
    assert label_score("Verifico la richiesta", ["verifica richiesta"]) == 1.0
    assert label_score("Emissione ordine", ["verifica richiesta"]) == 0.0


def test_a_regression_is_named_and_honesty_has_no_tolerance():
    baseline = {"case_id": "mini", "activity_recall": 0.9, "edge_recall": 0.8, "honest": True}

    assert regressions({**baseline, "activity_recall": 0.88}, baseline) == []
    worse = regressions({**baseline, "activity_recall": 0.7}, baseline)
    assert worse and "activity_recall" in worse[0]
    dishonest = regressions(
        {**baseline, "honest": False, "forbidden_hits": ["inventato: «Firma direttore»"]},
        baseline,
    )
    assert dishonest and "onesto" in dishonest[0]


# --- il golden set e' leggibile ----------------------------------------------


def test_every_golden_case_loads_and_has_its_sources():
    cases = load_golden_cases(GOLDEN)

    assert cases, "il golden set non puo' essere vuoto"
    for case in cases:
        assert case.activities
        for source in case.source_texts():
            assert source["content"].strip(), f"{case.case_id}: fonte vuota {source['name']}"
        declared_lanes = set(case.lanes)
        for activity in case.activities:
            assert not activity.lane or activity.lane in declared_lanes, (
                f"{case.case_id}: {activity.id} in una corsia non dichiarata"
            )


def test_a_reference_edge_on_an_undeclared_activity_is_refused(tmp_path):
    folder = tmp_path / "rotto"
    (folder / "sources").mkdir(parents=True)
    (folder / "expected.json").write_text(
        '{"case_id": "rotto", "process_name": "x", "sources": [], '
        '"activities": [{"id": "a", "aliases": ["a"]}], "edges": [["a", "b"]]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non dichiarata"):
        ReferenceCase.load(folder)


# --- dal piano al disegno non si perde niente --------------------------------


def _ideal_plan(case: ReferenceCase) -> ProcessUnderstanding:
    """Il piano che un estrattore perfetto produrrebbe dalle fonti del caso.

    Scritto a mano accanto al riferimento, nella rappresentazione che il
    contratto dell'estrattore chiede: percorso principale, decisioni con i loro
    rami, percorsi alternativi. Non e' un'estrazione: e' il piano giusto. Se il
    compilatore lo disegna perdendo un'attivita', un ramo o un ordine, il difetto
    e' nel compilatore - l'unico tratto della catena che deve essere esatto.
    """
    return ProcessUnderstanding.model_validate(
        json.loads((case.root / "ideal_plan.json").read_text(encoding="utf-8"))
    )


def _compiler_cases() -> list:
    return [
        pytest.param(
            case,
            id=case.case_id,
            marks=[
                pytest.mark.xfail(
                    strict=True,
                    reason="limite noto del compilatore: " + "; ".join(case.compiler_known_gaps),
                )
            ]
            if case.compiler_known_gaps
            else [],
        )
        for case in load_golden_cases(GOLDEN)
    ]


@pytest.mark.parametrize("case", _compiler_cases())
def test_the_compiler_loses_nothing_between_plan_and_drawing(case: ReferenceCase):
    plan = _ideal_plan(case)
    model = build_bpmn_semantic_model(
        process_id=f"Process_{case.case_id}", process_name=case.process_name, process=plan
    )

    metrics = compare(parse_bpmn(semantic_model_to_bpmn_xml(model)), case)

    report = metrics.as_dict()
    assert metrics.activity_recall == 1.0, report
    assert metrics.activity_precision == 1.0, report
    assert metrics.lane_accuracy == 1.0, report
    assert metrics.gateway_recall == 1.0, report
    assert metrics.edge_recall == 1.0, report
    # Il compilatore non deve nemmeno aggiungere ordini che il piano non dice:
    # un arco inventato fra due passaggi e' un AS-IS diverso da quello descritto.
    assert metrics.edge_precision == 1.0, report
    assert metrics.honest, report


def test_a_decision_keeps_every_branch_it_names():
    """Una scelta a tre vie non perde un ramo.

    Il compilatore prendeva un solo percorso alternativo per decisione: il
    secondo ramo spariva, e la compilazione si dichiarava lossless lo stesso.
    """
    plan = ProcessUnderstanding(
        title="Tre vie",
        steps=[
            ProcessStep(id="verifica", label="Verifica richiesta"),
            ProcessStep(id="integra", label="Richiedi integrazione"),
            ProcessStep(id="autorizza", label="Richiedi autorizzazione"),
            ProcessStep(id="ordina", label="Emetti ordine"),
        ],
        main_success_path=["verifica", "ordina"],
        decisions=[
            ProcessDecision(
                id="esito",
                label="Esito verifica?",
                outcome_details=[
                    ProcessDecisionOutcome(id="o1", label="Incompleta", target_path_id="p_integra"),
                    ProcessDecisionOutcome(id="o2", label="Serve autorizzazione", target_path_id="p_autorizza"),
                    ProcessDecisionOutcome(id="o3", label="Procedi", target_ref="ordina", is_default=True),
                ],
            )
        ],
        alternative_paths=[
            ProcessPath(id="p_integra", label="Incompleta", sequence=["integra"], rejoins_at="verifica"),
            ProcessPath(id="p_autorizza", label="Autorizzazione", sequence=["autorizza"], rejoins_at="ordina"),
        ],
        flow_edges=[
            {"id": "e1", "source_id": "verifica", "target_id": "esito", "label": "verificata"},
        ],
    )

    model = build_bpmn_semantic_model(process_id="P", process_name="Tre vie", process=plan)
    names = {node.name for node in model.flowNodes}

    assert {"Richiedi integrazione", "Richiedi autorizzazione"} <= names
    assert not any("senza alternative path" in warning for warning in model.model_warnings)


def test_an_order_nobody_declared_is_not_drawn_in_silence():
    """Senza percorso principale l'ordine e' dedotto: la compilazione lo dice."""
    plan = ProcessUnderstanding(
        title="Senza percorso",
        steps=[
            ProcessStep(id="a", label="Primo passaggio"),
            ProcessStep(id="b", label="Secondo passaggio"),
        ],
    )

    model = build_bpmn_semantic_model(process_id="P", process_name="Senza percorso", process=plan)

    assert any("Percorso principale non dichiarato" in warning for warning in model.model_warnings)


def test_every_golden_case_has_an_ideal_plan():
    for case in load_golden_cases(GOLDEN):
        assert (case.root / "ideal_plan.json").exists(), (
            f"{case.case_id}: manca il piano ideale, senza il quale il compilatore non si misura"
        )
