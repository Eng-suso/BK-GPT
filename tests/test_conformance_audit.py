"""Il revisore di conformita', pezzo per pezzo, senza database e senza modello.

Il test end-to-end (`test_evidence_canvas_conformance_e2e.py`) attraversa il
loop intero sul caso Esaote. Qui si fissano le regole che quel loop usa, una per
una, perche' ognuna chiude un modo preciso in cui un disegno sbagliato passava
per giusto:

- il canvas si confronta con il piano per id, tipo, nome e collegamenti - non per
  testo, che il layout riscrive;
- un rilievo del revisore vale solo con la citazione ritrovata nella fonte;
- senza revisore il verdetto non e' mai `conformant`;
- un giudizio di qualita' non da' 7/10 a un piano senza attivita'.
"""

from __future__ import annotations

from backend.agents.conformance_audit import (
    AuditedContradiction,
    AuditedFact,
    ConformanceFinding,
    ConformanceReport,
    SourceAuditRequest,
    SourceAuditVerdict,
    _verified_source_findings,
    canvas_plan_findings,
    evaluate_conformance,
    reviewer_notes_by_source,
    signature_digest,
)
from backend.agents.process_snapshot import ProcessKnowledgeSnapshot
from backend.process_understanding import (
    ProcessUnderstanding,
    ProcessUnderstandingQualityReport,
    QualityDimensionScore,
    coherent_quality_report,
)

PLAN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="d">
  <bpmn:process id="p">
    <bpmn:startEvent id="start" name="Richiesta"/>
    <bpmn:userTask id="crea_ordine" name="Crea ordine"/>
    <bpmn:endEvent id="end" name="Ordine inviato"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="crea_ordine"/>
    <bpmn:sequenceFlow id="f2" sourceRef="crea_ordine" targetRef="end"/>
  </bpmn:process>
</bpmn:definitions>"""

SOURCE = (
    "Paolo Marchetti, Manutenzione. Quando la linea e' ferma non aspetto Acquisti: "
    "chiamo direttamente il fornitore e faccio consegnare."
)


def _request(**overrides) -> SourceAuditRequest:
    base = {
        "process_name": "Acquisti",
        "source_id": "src-paolo",
        "source_name": "Intervista Paolo",
        "source_text": SOURCE,
        "plan_elements": [{"ref": "steps:crea_ordine", "tipo": "attivita", "etichetta": "Crea ordine"}],
    }
    base.update(overrides)
    return SourceAuditRequest(**base)


# --- canvas contro piano --------------------------------------------------


def test_the_same_process_with_different_layout_is_conformant():
    laid_out = PLAN_XML.replace(
        '<bpmn:userTask id="crea_ordine" name="Crea ordine"/>',
        '<bpmn:userTask id="crea_ordine" name="Crea  ordine" xmlns:delir="urn:x" delir:provenance="verified"/>',
    )
    assert canvas_plan_findings(laid_out, PLAN_XML) == []
    assert signature_digest(laid_out) == signature_digest(PLAN_XML)


def test_a_missing_renamed_or_extra_node_is_blocking():
    missing = PLAN_XML.replace('<bpmn:userTask id="crea_ordine" name="Crea ordine"/>', "")
    renamed = PLAN_XML.replace('name="Crea ordine"', 'name="Ordine creato a mano"')
    extra = PLAN_XML.replace(
        '<bpmn:endEvent id="end"', '<bpmn:task id="inventato" name="Audit"/><bpmn:endEvent id="end"'
    )

    assert {item.code for item in canvas_plan_findings(missing, PLAN_XML)} >= {"canvas_missing_element"}
    assert [item.code for item in canvas_plan_findings(renamed, PLAN_XML)] == ["canvas_element_differs"]
    assert [item.code for item in canvas_plan_findings(extra, PLAN_XML)] == ["canvas_extra_element"]
    assert all(item.severity == "blocking" for item in canvas_plan_findings(renamed, PLAN_XML))


def test_a_rewired_flow_is_blocking():
    rewired = PLAN_XML.replace('sourceRef="start" targetRef="crea_ordine"', 'sourceRef="start" targetRef="end"')
    codes = [item.code for item in canvas_plan_findings(rewired, PLAN_XML)]
    assert codes == ["canvas_flow_differs"]


def test_an_empty_canvas_against_a_plan_is_blocking():
    assert [item.code for item in canvas_plan_findings("", PLAN_XML)] == ["canvas_empty"]


# --- le prove del revisore ------------------------------------------------


def test_a_finding_counts_only_with_a_quote_the_source_contains():
    verdict = SourceAuditVerdict(
        missing_facts=[
            AuditedFact(kind="activity", diagram_change="new_activity", statement="chiama il fornitore", quote="chiamo direttamente il fornitore"),
            AuditedFact(kind="rule", diagram_change="new_activity", statement="inventato", quote="il fornitore manda sempre la nota di credito"),
        ],
        contradicted_elements=[
            AuditedContradiction(element_change="different_order", element_ref="steps:crea_ordine", quote="non aspetto Acquisti", explanation="x"),
            AuditedContradiction(element_change="different_order", element_ref="steps:inesistente", quote="non aspetto Acquisti", explanation="x"),
        ],
    )

    outcome = _verified_source_findings(_request(), verdict, {"steps:crea_ordine"})

    assert [item.layer for item in outcome.findings] == ["source_coverage", "source_contradiction"]
    assert outcome.discarded == 2
    # La citazione riportata e' quella della fonte, non quella del revisore.
    assert outcome.findings[0].quote in SOURCE


def test_the_same_passage_reported_twice_is_one_finding():
    verdict = SourceAuditVerdict(
        missing_facts=[
            AuditedFact(kind="activity", diagram_change="new_activity", statement="a", quote="chiamo direttamente il fornitore"),
            AuditedFact(kind="exception", diagram_change="new_activity", statement="b", quote="chiamo  direttamente il fornitore"),
        ]
    )
    outcome = _verified_source_findings(_request(), verdict, set())
    assert len(outcome.findings) == 1


def test_reviewer_notes_go_to_the_source_that_said_it():
    report = ConformanceReport(
        verdict="not_conformant",
        process_id="p",
        findings=[
            ConformanceFinding(layer="source_coverage", severity="gap", code="missing_activity",
                               message="m", source_id="src-paolo", quote="chiamo direttamente il fornitore"),
            ConformanceFinding(layer="canvas_plan", severity="blocking", code="canvas_empty", message="m"),
        ],
    )
    notes = reviewer_notes_by_source(report)
    assert list(notes) == ["src-paolo"]
    assert "chiamo direttamente il fornitore" in notes["src-paolo"][0]
    assert report.needs_plan_repair


# --- il verdetto ----------------------------------------------------------


def _snapshot_without_plan_elements() -> ProcessKnowledgeSnapshot:
    return ProcessKnowledgeSnapshot(
        process_id="p",
        process_understanding=ProcessUnderstanding(title="Acquisti").model_dump(mode="json"),
    )


def test_without_a_reviewer_a_clean_state_is_incomplete_not_conformant():
    report = evaluate_conformance(
        _snapshot_without_plan_elements(),
        sources=[{"id": "s", "name": "Intervista", "content": SOURCE}],
        canvas_xml=None,
        review_brief=None,
        auditor=None,
    )
    # Nessun piano compilabile: il canvas non si puo' confrontare, e il
    # revisore non c'e'. Due motivi diversi, nessuno dei due e' "conforme".
    assert report.verdict != "conformant"
    assert report.llm_audit == "skipped"
    assert "non e' disponibile" in report.llm_audit_note


def test_a_reviewer_that_crashes_on_one_source_makes_the_audit_partial():
    calls = []

    def flaky(request: SourceAuditRequest) -> SourceAuditVerdict:
        calls.append(request.source_name)
        if request.source_name == "Rotta":
            raise RuntimeError("429")
        return SourceAuditVerdict()

    report = evaluate_conformance(
        _snapshot_without_plan_elements(),
        sources=[
            {"id": "a", "name": "Buona", "content": SOURCE},
            {"id": "b", "name": "Rotta", "content": SOURCE},
        ],
        canvas_xml=None,
        review_brief=None,
        auditor=flaky,
    )
    assert sorted(calls) == ["Buona", "Rotta"]
    assert report.llm_audit == "partial"
    assert report.verdict != "conformant"


def test_provider_imports_are_warmed_before_parallel_extraction(monkeypatch):
    """Il deadlock di import visto nella coda reale: i moduli si caricano prima del pool."""
    from backend.agents import process_synthesis
    from backend.process_understanding import ProcessUnderstandingResult

    order: list[str] = []
    monkeypatch.setattr(process_synthesis, "warm_provider_imports", lambda: order.append("warm"))

    def fake(title, source_text, *, with_quality_report=True):
        order.append("extract")
        return ProcessUnderstandingResult(status="success", process=ProcessUnderstanding(title=title))

    monkeypatch.setattr(process_synthesis, "build_process_understanding", fake)
    process_synthesis.extract_plan_from_sources(
        "Acquisti",
        [{"id": str(i), "name": f"Fonte {i}", "content": SOURCE} for i in range(3)],
    )
    assert order[0] == "warm" and order.count("extract") == 3


# --- il giudizio di qualita' ----------------------------------------------


def test_an_empty_plan_cannot_score_seven_out_of_ten():
    """Il rapporto Esaote: 10/10 alla prudenza, 2/10 alla compilabilita', 7 complessivo."""
    report = ProcessUnderstandingQualityReport(
        overall_score=7,
        dimension_scores=[
            QualityDimensionScore(dimension="actor_responsibility", score=10, blocking=True),
            QualityDimensionScore(dimension="main_path_clarity", score=10, blocking=True),
            QualityDimensionScore(dimension="bpmn_compilability", score=2, blocking=True),
            QualityDimensionScore(dimension="consultant_summary_quality", score=8, blocking=False),
        ],
        approval_recommendation="ready_to_generate",
    )

    coherent = coherent_quality_report(report, ProcessUnderstanding(title="Acquisti"))

    assert coherent.overall_score <= 2
    assert coherent.approval_recommendation != "ready_to_generate"
    assert any("Nessuna attivita" in item.message for item in coherent.blocking_issues)


def test_a_finding_about_the_order_names_steps_not_ids():
    """Rilievo sul percorso: il consulente legge i nomi dei passaggi, mai i loro id."""
    from backend.agents.conformance_audit import plan_elements_for_audit
    from backend.process_understanding import ProcessStep

    plan = ProcessUnderstanding(
        title="Acquisti",
        steps=[
            ProcessStep(id="step_ricevi_richiesta", label="Ricevi la richiesta"),
            ProcessStep(id="step_crea_ordine", label="Crea l'ordine"),
        ],
        main_success_path=["step_ricevi_richiesta", "step_crea_ordine"],
    )
    snapshot = ProcessKnowledgeSnapshot(process_id="p", process_understanding=plan.model_dump(mode="json"))
    elements = plan_elements_for_audit(snapshot)
    order = next(item for item in elements if item["ref"] == "sequence")

    verdict = SourceAuditVerdict(
        contradicted_elements=[
            AuditedContradiction(
                element_change="different_order", element_ref="sequence",
                quote="chiamo direttamente il fornitore", explanation="l'ordine e' un altro",
            )
        ]
    )
    outcome = _verified_source_findings(
        _request(plan_elements=elements), verdict, {item["ref"] for item in elements}
    )

    assert "step_" not in order["etichetta"]
    assert "step_" not in outcome.findings[0].message
    assert "Ricevi la richiesta" in outcome.findings[0].message
