"""Il piano fuso per fonte diventa un piano solo: ordine dedotto, doppioni uniti.

Sul processo reale di acquisto materiali indiretti (piano V2, tre interviste) il
percorso principale cominciava dalla fattura - la prima intervista in ordine
alfabetico era quella dell'Amministrazione - e lo stesso passaggio raccontato da
due voci restava due passaggi: 37 attivita' dove il processo ne ha una
quindicina.

Qui si verifica il rimedio, con un estrattore e un consolidatore finti: niente
modello, perche' si verifica cio' che il runtime garantisce, non la bravura
dell'LLM.

1. il percorso parte dall'inizio che i legami dimostrano, non dalla fonte letta
   per prima, e due ricostruzioni sulle stesse fonti danno lo stesso piano;
2. lo stesso passaggio raccontato da due voci diventa un elemento solo, con le
   citazioni di entrambe e nessun riferimento rotto;
3. un gruppo proposto senza appigli si scarta e si conta;
4. cio' che nessun legame ordina resta in coda, dichiarato.
"""

from __future__ import annotations

import json

import pytest

from backend.agents.plan_consolidation import (
    ORDER_FINDING_ID,
    PlanUnificationVerdict,
    SameElementGroup,
)
from backend.agents.plan_provenance import verify_plan_provenance
from backend.agents.process_plan import merge_process_understanding
from backend.agents.process_synthesis import extract_plan_from_sources
from backend.process_understanding import (
    BpmnLaneCandidate,
    BpmnParticipantTopology,
    BpmnPoolCandidate,
    ProcessActor,
    ProcessBoundaries,
    ProcessDecision,
    ProcessDecisionOutcome,
    ProcessEvent,
    ProcessExceptionPath,
    ProcessFlowEdge,
    ProcessStep,
    ProcessUnderstanding,
    ProcessUnderstandingResult,
    process_understanding_diagnostics,
)


def _source(name: str, content: str) -> dict:
    return {
        "id": name.lower().replace(" ", "-"),
        "name": name,
        "type": "Intervista",
        "participants": [],
        "summary": "",
        "content": content,
        "has_content": True,
    }


def _edges(*pairs: tuple[str, str]) -> list[ProcessFlowEdge]:
    return [
        ProcessFlowEdge(id=f"e_{source}_{target}", source_id=source, target_id=target, label="poi")
        for source, target in pairs
    ]


def _install(monkeypatch, plans: dict[str, ProcessUnderstanding]) -> None:
    """L'estrattore finto: a ogni fonte il suo piano parziale, riconosciuto dal testo."""

    def _fake(title: str, source_text: str, *, with_quality_report: bool = True):
        for marker, plan in plans.items():
            if marker in source_text:
                return ProcessUnderstandingResult(status="success", process=plan.model_copy(deep=True))
        raise AssertionError("fonte inattesa")

    monkeypatch.setattr("backend.agents.process_synthesis.build_process_understanding", _fake)


def _fixed_unifier(verdict: PlanUnificationVerdict, seen: list | None = None):
    def _unify(request):
        if seen is not None:
            seen.append(request)
        return verdict

    return _unify


# --- 1. ordine ---------------------------------------------------------------


def _two_voices_from_both_ends() -> dict[str, ProcessUnderstanding]:
    """L'Amministrazione racconta la fine, il reparto racconta l'inizio."""
    administration = ProcessUnderstanding(
        title="Acquisti",
        actors=[ProcessActor(id="amministrazione", label="Amministrazione", kind="team")],
        events=[ProcessEvent(id="ev_fattura", label="Fattura ricevuta", type="start")],
        steps=[
            ProcessStep(id="ricevere_fattura", label="Ricevere la fattura", actor_ids=["amministrazione"]),
            ProcessStep(id="abbinare_ordine", label="Abbinare la fattura all'ordine", actor_ids=["amministrazione"]),
        ],
        main_success_path=["ricevere_fattura", "abbinare_ordine"],
        flow_edges=_edges(("ev_fattura", "ricevere_fattura"), ("ricevere_fattura", "abbinare_ordine")),
        boundaries=ProcessBoundaries(start_event="Fattura ricevuta", success_end="Fattura registrata"),
    )
    department = ProcessUnderstanding(
        title="Acquisti",
        actors=[
            ProcessActor(id="reparto", label="Reparto", kind="team"),
            ProcessActor(id="acquisti", label="Acquisti", kind="team"),
        ],
        events=[ProcessEvent(id="ev_esigenza", label="Esigenza del reparto", type="start")],
        steps=[
            ProcessStep(id="rilevare_fabbisogno", label="Rilevare il fabbisogno", actor_ids=["reparto"]),
            ProcessStep(id="inviare_richiesta", label="Inviare la richiesta", actor_ids=["reparto"]),
            ProcessStep(id="emettere_ordine", label="Emettere l'ordine", actor_ids=["acquisti"]),
            ProcessStep(id="ricevere_fattura", label="Ricevere la fattura", actor_ids=["amministrazione"]),
        ],
        main_success_path=["rilevare_fabbisogno", "inviare_richiesta", "emettere_ordine", "ricevere_fattura"],
        flow_edges=_edges(
            ("ev_esigenza", "rilevare_fabbisogno"),
            ("rilevare_fabbisogno", "inviare_richiesta"),
            ("inviare_richiesta", "emettere_ordine"),
            ("emettere_ordine", "ricevere_fattura"),
        ),
        boundaries=ProcessBoundaries(start_event="Esigenza del reparto", success_end="Ordine emesso"),
    )
    return {"AMMINISTRAZIONE": administration, "REPARTO": department}


ADMIN = _source("Intervista Amministrazione", "AMMINISTRAZIONE: riceviamo la fattura.")
DEPARTMENT = _source("Intervista Reparto", "REPARTO: rileviamo il fabbisogno.")


def test_the_path_starts_from_the_trigger_not_from_the_first_source_read(monkeypatch):
    """L'Amministrazione si legge per prima, e il processo non comincia dalla fattura."""
    _install(monkeypatch, _two_voices_from_both_ends())

    result = extract_plan_from_sources("Acquisti", [ADMIN, DEPARTMENT])

    assert result.process.main_success_path == [
        "rilevare_fabbisogno",
        "inviare_richiesta",
        "emettere_ordine",
        "ricevere_fattura",
        "abbinare_ordine",
    ]
    assert result.consolidation.start_id == "ev_esigenza"
    assert result.consolidation.unordered == []
    # Il disegno prende il nome dell'evento iniziale dai confini: devono essere
    # quelli della voce che racconta l'inizio, e la fine quella di chi racconta
    # la fine - non i confini dell'ultima voce letta.
    assert result.process.boundaries.start_event == "Esigenza del reparto"
    assert result.process.boundaries.success_end == "Fattura registrata"
    assert not any(item.id == ORDER_FINDING_ID for item in result.process.consultant_findings)


def test_the_order_does_not_depend_on_the_reading_order(monkeypatch):
    """Fonti lette al contrario, stesso percorso: l'ordine e' dedotto, non ereditato."""
    _install(monkeypatch, _two_voices_from_both_ends())

    forward = extract_plan_from_sources("Acquisti", [ADMIN, DEPARTMENT])
    backward = extract_plan_from_sources("Acquisti", [DEPARTMENT, ADMIN])

    assert forward.process.main_success_path == backward.process.main_success_path
    assert forward.process.boundaries.start_event == backward.process.boundaries.start_event


def test_a_rework_loop_does_not_break_the_order(monkeypatch):
    """Un ciclo di rilavorazione e' un legame vero, non un motivo per rinunciare all'ordine."""
    plan = ProcessUnderstanding(
        title="Acquisti",
        actors=[ProcessActor(id="acquisti", label="Acquisti", kind="team")],
        events=[ProcessEvent(id="ev_start", label="Richiesta arrivata", type="start")],
        steps=[
            ProcessStep(id="verificare", label="Verificare la richiesta", actor_ids=["acquisti"]),
            ProcessStep(id="integrare", label="Richiedere integrazione", actor_ids=["acquisti"]),
            ProcessStep(id="ricostruire", label="Ricostruire la richiesta", actor_ids=["acquisti"]),
            ProcessStep(id="ordinare", label="Emettere l'ordine", actor_ids=["acquisti"]),
        ],
        # L'ordine dichiarato e' sbagliato di proposito: l'estrattore accoda.
        main_success_path=["ordinare", "integrare", "ricostruire", "verificare"],
        flow_edges=_edges(
            ("ev_start", "ricostruire"),
            ("ricostruire", "verificare"),
            ("verificare", "integrare"),
            ("integrare", "ricostruire"),
            ("verificare", "ordinare"),
        ),
    )
    _install(monkeypatch, {"UNICA": plan})

    result = extract_plan_from_sources("Acquisti", [_source("Intervista", "UNICA voce.")])

    path = result.process.main_success_path
    assert path[0] == "ricostruire"
    assert path.index("verificare") < path.index("integrare")
    assert path.index("verificare") < path.index("ordinare")
    assert result.consolidation.unordered == []


def test_what_no_link_orders_stays_at_the_tail_and_is_declared(monkeypatch):
    """Due pezzi che nessun legame collega: niente ordine inventato, e il piano lo dice."""
    department = ProcessUnderstanding(
        title="Acquisti",
        actors=[ProcessActor(id="reparto", label="Reparto", kind="team")],
        events=[ProcessEvent(id="ev_esigenza", label="Esigenza", type="start")],
        steps=[
            ProcessStep(id="rilevare", label="Rilevare il fabbisogno", actor_ids=["reparto"]),
            ProcessStep(id="compilare", label="Compilare la richiesta", actor_ids=["reparto"]),
            ProcessStep(id="inviare", label="Inviare la richiesta", actor_ids=["reparto"]),
        ],
        main_success_path=["rilevare", "compilare", "inviare"],
        flow_edges=_edges(("ev_esigenza", "rilevare")),
    )
    administration = ProcessUnderstanding(
        title="Acquisti",
        actors=[ProcessActor(id="amministrazione", label="Amministrazione", kind="team")],
        steps=[
            ProcessStep(id="registrare", label="Registrare la fattura", actor_ids=["amministrazione"]),
            ProcessStep(id="pagare", label="Pagare il fornitore", actor_ids=["amministrazione"]),
        ],
        main_success_path=["registrare", "pagare"],
    )
    _install(monkeypatch, {"REPARTO": department, "AMMINISTRAZIONE": administration})

    result = extract_plan_from_sources("Acquisti", [ADMIN, DEPARTMENT])

    assert result.process.main_success_path == ["rilevare", "compilare", "inviare", "registrare", "pagare"]
    assert result.consolidation.unordered == ["registrare", "pagare"]
    finding = next(item for item in result.process.consultant_findings if item.id == ORDER_FINDING_ID)
    assert "Registrare la fattura" in finding.finding and "Pagare il fornitore" in finding.finding


def test_an_unconnected_piece_does_not_hold_the_known_path_hostage(monkeypatch):
    """Una voce non collegata all'inizio che rimanda indietro non trascina in coda il resto.

    Caso golden: Acquisti rimanda la richiesta all'Ufficio tecnico. Il suo pezzo
    non e' collegato all'inizio, ma il suo arco di ritorno puntava dentro il
    percorso noto, e i passaggi dell'Ufficio tecnico finivano dopo i suoi.
    """
    department = ProcessUnderstanding(
        title="Acquisti",
        actors=[ProcessActor(id="reparto", label="Reparto", kind="team")],
        events=[ProcessEvent(id="ev_esigenza", label="Esigenza", type="start")],
        steps=[
            ProcessStep(id="rilevare", label="Rilevare il fabbisogno", actor_ids=["reparto"]),
            ProcessStep(id="ricostruire", label="Ricostruire la richiesta", actor_ids=["reparto"]),
            ProcessStep(id="inviare", label="Inviare la richiesta", actor_ids=["reparto"]),
        ],
        main_success_path=["rilevare", "ricostruire", "inviare"],
        flow_edges=_edges(("ev_esigenza", "rilevare")),
    )
    purchasing = ProcessUnderstanding(
        title="Acquisti",
        actors=[ProcessActor(id="acquisti", label="Acquisti", kind="team")],
        steps=[
            ProcessStep(id="ricevere", label="Ricevere la mail", actor_ids=["acquisti"]),
            ProcessStep(id="rimandare", label="Rimandare indietro", actor_ids=["acquisti"]),
        ],
        main_success_path=["ricevere", "rimandare"],
        flow_edges=_edges(("rimandare", "ricostruire")),
    )
    _install(monkeypatch, {"REPARTO": department, "ACQUISTI": purchasing})

    result = extract_plan_from_sources(
        "Acquisti", [_source("Intervista Acquisti", "ACQUISTI."), DEPARTMENT]
    )

    assert result.process.main_success_path == ["rilevare", "ricostruire", "inviare", "ricevere", "rimandare"]
    assert result.consolidation.unordered == ["ricevere", "rimandare"]


# --- 2. doppioni -------------------------------------------------------------


TECH_TEXT = (
    "TECNICO: ricostruisco la richiesta. Mando la richiesta agli acquisti. "
    "Poi Acquisti definisce il fornitore e crea l'ordine nel gestionale."
)
PURCHASING_TEXT = (
    "ACQUISTI: la richiesta arriva dall'ufficio tecnico. La prendo in carico. "
    "Scelgo il fornitore dalla mia lista. Emetto l'ordine."
)
TECH = _source("Intervista Tecnico", TECH_TEXT)
PURCHASING = _source("Intervista Acquisti", PURCHASING_TEXT)


def _two_voices_on_the_same_steps() -> dict[str, ProcessUnderstanding]:
    technical = ProcessUnderstanding(
        title="Acquisti",
        actors=[
            ProcessActor(id="ufficio_tecnico", label="Ufficio tecnico", kind="team"),
            ProcessActor(id="acquisti", label="Acquisti", kind="team"),
        ],
        steps=[
            ProcessStep(id="ricostruire_richiesta", label="Ricostruire la richiesta", actor_ids=["ufficio_tecnico"]),
            ProcessStep(
                id="inviare_richiesta_acquisti",
                label="Inviare la richiesta ad Acquisti",
                actor_ids=["ufficio_tecnico"],
                source_evidence=["Mando la richiesta agli acquisti"],
            ),
            ProcessStep(
                id="definire_fornitore",
                label="Definire il fornitore",
                actor_ids=["acquisti"],
                source_evidence=["Acquisti definisce il fornitore"],
            ),
            ProcessStep(
                id="creare_ordine_gestionale",
                label="Creare l'ordine nel gestionale",
                actor_ids=["acquisti"],
                source_evidence=["crea l'ordine nel gestionale"],
            ),
        ],
        main_success_path=[
            "ricostruire_richiesta",
            "inviare_richiesta_acquisti",
            "definire_fornitore",
            "creare_ordine_gestionale",
        ],
        flow_edges=_edges(
            ("ricostruire_richiesta", "inviare_richiesta_acquisti"),
            ("inviare_richiesta_acquisti", "definire_fornitore"),
            ("definire_fornitore", "creare_ordine_gestionale"),
        ),
        exceptions=[
            ProcessExceptionPath(id="ex_ritardo", label="Fornitore in ritardo", attached_to_step_id="definire_fornitore")
        ],
    )
    purchasing = ProcessUnderstanding(
        title="Acquisti",
        actors=[
            ProcessActor(id="ufficio_tecnico", label="Ufficio tecnico", kind="team"),
            ProcessActor(id="ufficio_acquisti", label="Ufficio Acquisti", kind="team"),
        ],
        steps=[
            ProcessStep(
                id="invio_richiesta",
                label="Inviare richiesta ad Acquisti",
                actor_ids=["ufficio_tecnico"],
                source_evidence=["la richiesta arriva dall'ufficio tecnico"],
            ),
            ProcessStep(id="prendere_in_carico", label="Prendere in carico la richiesta", actor_ids=["ufficio_acquisti"]),
            ProcessStep(
                id="selezionare_fornitore",
                label="Selezionare il fornitore",
                actor_ids=["ufficio_acquisti"],
                source_evidence=["Scelgo il fornitore dalla mia lista"],
            ),
            ProcessStep(
                id="emettere_ordine",
                label="Emettere l'ordine",
                actor_ids=["ufficio_acquisti"],
                source_evidence=["Emetto l'ordine"],
            ),
        ],
        decisions=[
            ProcessDecision(
                id="dec_lista",
                label="Fornitore in lista?",
                outcome_details=[
                    ProcessDecisionOutcome(id="si", label="Si", target_ref="selezionare_fornitore"),
                    ProcessDecisionOutcome(id="no", label="No", target_ref="emettere_ordine"),
                ],
            )
        ],
        main_success_path=["invio_richiesta", "prendere_in_carico", "selezionare_fornitore", "emettere_ordine"],
        flow_edges=_edges(
            ("invio_richiesta", "prendere_in_carico"),
            ("prendere_in_carico", "dec_lista"),
            ("selezionare_fornitore", "emettere_ordine"),
        ),
        bpmn_topology=BpmnParticipantTopology(
            pools=[BpmnPoolCandidate(id="pool", label="Azienda", actor_ids=["ufficio_tecnico", "ufficio_acquisti"])],
            lanes=[
                BpmnLaneCandidate(id="lane_acquisti", label="Acquisti", pool_id="pool", actor_ids=["ufficio_acquisti"])
            ],
        ),
    )
    return {"TECNICO": technical, "ACQUISTI": purchasing}


SAME_STEPS = PlanUnificationVerdict(
    groups=[
        SameElementGroup(kind="actor", element_ids=["acquisti", "ufficio_acquisti"], reason="stesso ufficio"),
        SameElementGroup(
            kind="step", element_ids=["inviare_richiesta_acquisti", "invio_richiesta"], reason="stesso invio"
        ),
        SameElementGroup(
            kind="step", element_ids=["definire_fornitore", "selezionare_fornitore"], reason="stessa scelta"
        ),
        SameElementGroup(
            kind="step", element_ids=["creare_ordine_gestionale", "emettere_ordine"], reason="stesso ordine"
        ),
    ]
)
ABSORBED = {"ufficio_acquisti", "invio_richiesta", "selezionare_fornitore", "emettere_ordine"}


def _mentions(plan: ProcessUnderstanding, ids: set[str]) -> list[str]:
    """Dove il piano nomina ancora gli id dati, fuori dalla traccia delle unificazioni."""
    data = plan.model_dump(mode="json")
    data.pop("unified_elements")
    text = json.dumps(data, ensure_ascii=False)
    return sorted(item for item in ids if f'"{item}"' in text)


def test_the_same_step_told_by_two_voices_becomes_one(monkeypatch):
    _install(monkeypatch, _two_voices_on_the_same_steps())
    seen: list = []

    result = extract_plan_from_sources(
        "Acquisti", [PURCHASING, TECH], unifier=_fixed_unifier(SAME_STEPS, seen)
    )
    plan = result.process

    assert len(seen) == 1, "una sola chiamata, sul piano fuso"
    assert result.consolidation.unifier_status == "done"
    assert result.consolidation.discarded == []
    assert {step.id for step in plan.steps} == {
        "ricostruire_richiesta",
        "inviare_richiesta_acquisti",
        "prendere_in_carico",
        "definire_fornitore",
        "creare_ordine_gestionale",
    }
    assert {actor.id for actor in plan.actors} == {"ufficio_tecnico", "acquisti"}

    # Nessun elemento sparisce senza traccia: ogni id assorbito ha il suo alias.
    aliases = {absorbed: item.id for item in plan.unified_elements for absorbed in item.absorbed_ids}
    assert aliases == {
        "ufficio_acquisti": "acquisti",
        "invio_richiesta": "inviare_richiesta_acquisti",
        "selezionare_fornitore": "definire_fornitore",
        "emettere_ordine": "creare_ordine_gestionale",
    }

    # Nessun riferimento resta rivolto a un id che non esiste piu'.
    assert _mentions(plan, ABSORBED) == []
    assert process_understanding_diagnostics(plan).blocking == []


def test_the_unified_step_keeps_the_evidence_of_every_voice(monkeypatch):
    """Un passaggio confermato da due interviste risulta piu' sostenuto, non meno."""
    _install(monkeypatch, _two_voices_on_the_same_steps())

    result = extract_plan_from_sources("Acquisti", [TECH, PURCHASING], unifier=_fixed_unifier(SAME_STEPS))
    plan = result.process
    supplier = next(step for step in plan.steps if step.id == "definire_fornitore")

    assert supplier.source_evidence == [
        "Acquisti definisce il fornitore",
        "Scelgo il fornitore dalla mia lista",
    ]
    report = verify_plan_provenance(plan, [TECH, PURCHASING])
    element = next(item for item in report.elements if item.source_ref == "steps:definire_fornitore")
    assert element.status == "verified"
    assert sorted(element.corroborating_sources) == ["Intervista Acquisti", "Intervista Tecnico"]
    assert report.summary()["corroborated"] >= 1


def test_references_are_rewritten_onto_the_survivor(monkeypatch):
    _install(monkeypatch, _two_voices_on_the_same_steps())

    plan = extract_plan_from_sources(
        "Acquisti", [TECH, PURCHASING], unifier=_fixed_unifier(SAME_STEPS)
    ).process

    decision = plan.decisions[0]
    assert [item.target_ref for item in decision.outcome_details] == [
        "definire_fornitore",
        "creare_ordine_gestionale",
    ]
    assert plan.exceptions[0].attached_to_step_id == "definire_fornitore"
    assert plan.bpmn_topology.lanes[0].actor_ids == ["acquisti"]
    assert plan.bpmn_topology.pools[0].actor_ids == ["ufficio_tecnico", "acquisti"]
    assert all(set(step.actor_ids) <= {"ufficio_tecnico", "acquisti"} for step in plan.steps)
    # Lo stesso arco raccontato da due voci resta un arco solo.
    pairs = [(edge.source_id, edge.target_id) for edge in plan.flow_edges]
    assert len(pairs) == len(set(pairs))
    assert ("definire_fornitore", "creare_ordine_gestionale") in pairs
    # E l'ordine si deduce dai legami di entrambe le voci.
    assert plan.main_success_path == [
        "ricostruire_richiesta",
        "inviare_richiesta_acquisti",
        "prendere_in_carico",
        "definire_fornitore",
        "creare_ordine_gestionale",
    ]


def test_an_absorbed_id_stays_reachable_through_an_amendment(monkeypatch):
    """Un emendamento che nomina il vecchio id non fa rientrare il doppione."""
    _install(monkeypatch, _two_voices_on_the_same_steps())
    plan = extract_plan_from_sources(
        "Acquisti", [TECH, PURCHASING], unifier=_fixed_unifier(SAME_STEPS)
    ).process

    amended, _diff = merge_process_understanding(
        plan,
        {
            "title": "Acquisti",
            "steps": [
                {
                    "id": "selezionare_fornitore",
                    "label": "Selezionare il fornitore",
                    "description": "Dalla lista personale di Acquisti.",
                }
            ],
            "flow_edges": [
                {"id": "e_new", "source_id": "selezionare_fornitore", "target_id": "emettere_ordine", "label": "poi"}
            ],
        },
    )

    assert len(amended.steps) == len(plan.steps)
    supplier = next(step for step in amended.steps if step.id == "definire_fornitore")
    assert supplier.description == "Dalla lista personale di Acquisti."
    assert _mentions(amended, ABSORBED) == []


# --- 3. gruppi che non reggono -------------------------------------------------


def test_a_group_without_grounds_is_discarded_and_counted(monkeypatch):
    _install(monkeypatch, _two_voices_on_the_same_steps())
    verdict = PlanUnificationVerdict(
        groups=[
            # Etichette senza parole in comune.
            SameElementGroup(
                kind="step", element_ids=["ricostruire_richiesta", "emettere_ordine"], reason="?"
            ),
            # Attori incompatibili: chi invia e chi prende in carico.
            SameElementGroup(
                kind="step", element_ids=["inviare_richiesta_acquisti", "prendere_in_carico"], reason="?"
            ),
            # Uno dopo l'altro nel racconto della stessa voce: una sequenza.
            SameElementGroup(kind="step", element_ids=["invio_richiesta", "prendere_in_carico"], reason="?"),
            # Un id che il piano non ha.
            SameElementGroup(kind="step", element_ids=["definire_fornitore", "fantasma"], reason="?"),
        ],
        process_start_id="non_un_candidato",
    )

    result = extract_plan_from_sources("Acquisti", [TECH, PURCHASING], unifier=_fixed_unifier(verdict))

    reasons = [item.reason for item in result.consolidation.discarded]
    assert len(result.consolidation.discarded) == 5, reasons
    assert any("parole in comune" in reason for reason in reasons)
    assert any("attori incompatibili" in reason for reason in reasons)
    assert any("sequenza" in reason for reason in reasons)
    assert any("fantasma" in reason for reason in reasons)
    assert any("candidati" in reason for reason in reasons)
    assert len(result.process.steps) == 8, "nessun gruppo accettato, nessun passaggio perso"
    assert result.process.unified_elements == []
    assert result.consolidation.as_log_entry()["discarded_groups"] == 5


def test_a_unifier_that_fails_does_not_cost_the_plan(monkeypatch):
    _install(monkeypatch, _two_voices_on_the_same_steps())

    def _down(request):
        raise TimeoutError("Request timed out.")

    result = extract_plan_from_sources("Acquisti", [TECH, PURCHASING], unifier=_down)

    assert result.process is not None
    assert len(result.process.steps) == 8
    assert result.consolidation.unifier_status == "failed"
    assert "TimeoutError" in result.consolidation.unifier_note
    assert result.llm_calls == 3, "due fonti piu' il consolidamento"


def test_the_agent_start_is_used_when_it_is_a_candidate(monkeypatch):
    _install(monkeypatch, _two_voices_from_both_ends())
    seen: list = []
    verdict = PlanUnificationVerdict(process_start_id="ev_esigenza")

    result = extract_plan_from_sources(
        "Acquisti", [ADMIN, DEPARTMENT], unifier=_fixed_unifier(verdict, seen)
    )

    assert {item["id"] for item in seen[0].start_candidates} >= {"ev_esigenza", "ev_fattura"}
    assert result.consolidation.start_basis == "agent"
    assert result.process.main_success_path[0] == "rilevare_fabbisogno"


# --- 4. determinismo -----------------------------------------------------------


@pytest.mark.parametrize("unifier", [None, _fixed_unifier(SAME_STEPS)], ids=["senza-agente", "con-agente"])
def test_two_rebuilds_on_the_same_sources_give_the_same_plan(monkeypatch, unifier):
    _install(monkeypatch, _two_voices_on_the_same_steps())

    first = extract_plan_from_sources("Acquisti", [TECH, PURCHASING], unifier=unifier)
    second = extract_plan_from_sources("Acquisti", [TECH, PURCHASING], unifier=unifier)

    assert first.process.model_dump(mode="json") == second.process.model_dump(mode="json")
