"""Il piano si confronta con le fonti, non solo il disegno con il piano.

La validazione verificava che il canvas somigliasse al piano, e il piano e'
l'output di un estrattore: un passaggio inventato arrivava al disegno con la
stessa dignita' di uno descritto da tre persone. Qui si verifica il controllo
che mancava, senza database e senza modello:

- l'evidenza dichiarata si ritrova parola per parola, o non si ritrova;
- una parafrasi fedele non e' un'invenzione, ma non e' nemmeno una citazione;
- cio' che nessuna fonte regge viene dichiarato, non cancellato;
- una fonte da cui il piano non prende niente si vede;
- il rapporto e' deterministico;
- l'esito arriva sul disegno, nodo per nodo, senza rompere il BPMN.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from backend.agents.plan_provenance import verify_plan_provenance
from backend.process_understanding import (
    ProcessActor,
    ProcessDecision,
    ProcessStep,
    ProcessUnderstanding,
)
from backend.workspace_services.bpmn_provenance_marks import (
    DELIR_NS,
    PROVENANCE_ATTRIBUTE,
    mark_provenance,
)


LAURA = {
    "id": "src-laura",
    "name": "Intervista Laura Conti",
    "content": (
        "Laura Conti, Ufficio Tecnico. Quando il magazzino segnala che manca un "
        "materiale apro una richiesta di acquisto e la mando ad Acquisti per mail. "
        "Se non ricevo risposta entro due giorni sollecito."
    ),
}
FRANCESCA = {
    "id": "src-francesca",
    "name": "Intervista Francesca Neri",
    "content": (
        "Francesca Neri, Ufficio Acquisti. Ricevo la richiesta dall'Ufficio "
        "Tecnico, verifico che ci sia l'autorizzazione del responsabile, poi creo "
        "l'ordine e lo invio al fornitore. Sopra i cinquemila euro serve sempre la "
        "firma del direttore acquisti."
    ),
}
PAOLO = {
    "id": "src-paolo",
    "name": "Intervista Paolo Marchetti",
    "content": "Paolo Marchetti, Manutenzione. Quando la linea e' ferma chiamo il fornitore.",
}


def _plan(**overrides) -> ProcessUnderstanding:
    data = {
        "title": "Ciclo passivo",
        "actors": [
            ProcessActor(id="ufficio_tecnico", label="Ufficio Tecnico", kind="team"),
        ],
        "steps": [],
        "decisions": [],
    }
    data.update(overrides)
    return ProcessUnderstanding(**data)


def _element(report, element_id: str):
    return next(item for item in report.elements if item.element_id == element_id)


def test_a_verbatim_quote_is_verified_and_cut_from_the_source():
    plan = _plan(
        steps=[
            ProcessStep(
                id="apri_richiesta",
                label="Apri richiesta di acquisto",
                source_evidence=["apro una richiesta di acquisto e la mando ad Acquisti"],
            )
        ]
    )

    report = verify_plan_provenance(plan, [LAURA, FRANCESCA])

    step = _element(report, "apri_richiesta")
    assert step.status == "verified"
    assert step.source_id == "src-laura"
    # La citazione e' quella della fonte, non quella ricopiata.
    assert step.quote in LAURA["content"]
    assert step.source_ref == "steps:apri_richiesta"


def test_a_quote_copied_without_punctuation_is_still_the_same_quote():
    plan = _plan(
        steps=[
            ProcessStep(
                id="firma",
                label="Firma del direttore",
                source_evidence=["Sopra i cinquemila euro serve sempre la firma del direttore acquisti"],
            )
        ]
    )

    report = verify_plan_provenance(plan, [FRANCESCA])

    assert _element(report, "firma").status == "verified"


def test_a_faithful_paraphrase_is_not_an_invention_but_not_a_quote_either():
    plan = _plan(
        steps=[
            ProcessStep(
                id="verifica",
                label="Verifica autorizzazione",
                source_evidence=["verifica autorizzazione responsabile prima dell'ordine"],
            )
        ]
    )

    report = verify_plan_provenance(plan, [FRANCESCA])

    step = _element(report, "verifica")
    assert step.status == "paraphrased"
    assert "autorizzazione del responsabile" in step.quote


def test_an_element_without_evidence_can_still_be_grounded_by_its_words():
    """L'estrattore ha dimenticato l'evidenza, ma il passaggio e' detto."""
    plan = _plan(
        steps=[ProcessStep(id="sollecito", label="Sollecita risposta dopo due giorni")]
    )

    report = verify_plan_provenance(plan, [LAURA])

    step = _element(report, "sollecito")
    assert step.status == "label_grounded"
    assert step.source_name == "Intervista Laura Conti"


def test_what_no_source_says_is_declared_unverified():
    """Un passaggio che nessuno ha raccontato non si cancella: si dichiara."""
    plan = _plan(
        steps=[
            ProcessStep(
                id="audit_trimestrale",
                label="Audit trimestrale dei fornitori strategici",
                source_evidence=["ogni trimestre facciamo audit sui fornitori strategici"],
            )
        ]
    )

    report = verify_plan_provenance(plan, [LAURA, FRANCESCA, PAOLO])

    step = _element(report, "audit_trimestrale")
    assert step.status == "unverified"
    assert step.quote == ""
    assert report.count("unverified") >= 1
    assert report.grounded_ratio < 1


def test_a_source_the_plan_takes_nothing_from_is_visible():
    plan = _plan(
        steps=[
            ProcessStep(
                id="apri_richiesta",
                label="Apri richiesta di acquisto",
                source_evidence=["apro una richiesta di acquisto"],
            )
        ]
    )

    report = verify_plan_provenance(plan, [LAURA, PAOLO])

    assert "Intervista Paolo Marchetti" in report.unused_sources
    assert "Intervista Laura Conti" not in report.unused_sources


def test_decisions_are_verified_on_their_question_too():
    plan = _plan(
        decisions=[
            ProcessDecision(
                id="soglia",
                label="Importo sopra soglia?",
                question="Importo sopra i cinquemila euro serve firma direttore?",
            )
        ]
    )

    report = verify_plan_provenance(plan, [FRANCESCA])

    assert _element(report, "soglia").status == "label_grounded"


def test_the_report_is_deterministic():
    plan = _plan(
        steps=[
            ProcessStep(id="apri", label="Apri richiesta di acquisto"),
            ProcessStep(id="ordine", label="Crea ordine e invialo al fornitore"),
        ]
    )

    first = verify_plan_provenance(plan, [LAURA, FRANCESCA, PAOLO])
    second = verify_plan_provenance(plan, [LAURA, FRANCESCA, PAOLO])

    assert first.model_dump() == second.model_dump()


def test_a_truncated_source_is_the_caller_problem_not_a_silent_success():
    """Senza testo, niente e' verificabile: il rapporto non inventa appigli."""
    plan = _plan(
        steps=[
            ProcessStep(
                id="apri_richiesta",
                label="Apri richiesta di acquisto",
                source_evidence=["apro una richiesta di acquisto"],
            )
        ]
    )

    report = verify_plan_provenance(plan, [{**LAURA, "content": ""}])

    assert report.sources_checked == 0
    assert _element(report, "apri_richiesta").status == "unverified"


def test_no_plan_no_report():
    report = verify_plan_provenance(None, [LAURA])

    assert report.elements == []
    assert report.summary()["total"] == 0


# --- il disegno porta l'esito ----------------------------------------------


_XML = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D">
  <bpmn:process id="P">
    <bpmn:startEvent id="Start" />
    <bpmn:userTask id="Task_apri" name="Apri richiesta">
      <bpmn:documentation>Passaggio

DeliR traceability:
{"source_refs": ["steps:apri_richiesta"]}</bpmn:documentation>
    </bpmn:userTask>
    <bpmn:userTask id="Task_recupero" name="Recupero">
      <bpmn:documentation>DeliR traceability:
{"source_refs": ["steps:recupero", "exceptions:linea_ferma"]}</bpmn:documentation>
    </bpmn:userTask>
  </bpmn:process>
</bpmn:definitions>"""


def _attr(xml: str, element_id: str) -> str | None:
    root = ET.fromstring(xml)
    node = next(item for item in root.iter() if item.attrib.get("id") == element_id)
    return node.attrib.get(PROVENANCE_ATTRIBUTE)


def test_each_traced_node_carries_its_provenance():
    marked, counts = mark_provenance(
        _XML,
        {
            "steps:apri_richiesta": "verified",
            "steps:recupero": "verified",
            "exceptions:linea_ferma": "unverified",
        },
    )

    assert _attr(marked, "Task_apri") == "verified"
    # Un nodo che rappresenta due elementi vale quanto il meno provato.
    assert _attr(marked, "Task_recupero") == "unverified"
    # Un nodo senza affermazioni da provare non riceve un esito inventato.
    assert _attr(marked, "Start") is None
    assert counts == {"verified": 1, "unverified": 1}
    assert DELIR_NS in marked


def test_marking_keeps_a_valid_bpmn():
    """L'estensione non rompe il diagramma: stessi elementi, stessi id."""
    marked, _counts = mark_provenance(_XML, {"steps:apri_richiesta": "label_grounded"})

    before = sorted(item.attrib.get("id") for item in ET.fromstring(_XML).iter() if item.attrib.get("id"))
    after = sorted(item.attrib.get("id") for item in ET.fromstring(marked).iter() if item.attrib.get("id"))
    assert before == after


def test_nothing_to_mark_returns_the_xml_untouched():
    marked, counts = mark_provenance(_XML, {})

    assert marked == _XML
    assert counts == {}
