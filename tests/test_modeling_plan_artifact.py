"""Il Modeling Plan e il BPMN Draft sono due artefatti, e si comportano da due.

Il difetto misurato: con tre interviste agli atti e un AS-IS gia' ragionato in
chat, "mettilo nel piano" veniva interpretato come una richiesta sul disegno.
DeliR chiedeva di passare alla modalita' che serve a costruire il canvas, il
piano non veniva scritto, e la rilettura mostrava la stessa versione di prima.
Nel frattempo la struttura ragionata - pool, corsie candidate, percorso
ordinario, percorso urgente, verifiche - si riduceva a qualche bullet.

Non era un difetto di prompt. Erano cinque cose diverse, tutte nel runtime:

1. **l'intento non sceglieva l'artefatto.** Niente, nel contratto di routing,
   diceva *quale* dei due artefatti una richiesta modifica;
2. **il piano si poteva solo riscrivere.** L'unico write agentico sostituiva
   l'intero piano, quindi una modifica incrementale non aveva un'operazione;
3. **ogni scrittura era distruttiva.** Cio' che non veniva ripetuto spariva;
4. **il rifiuto per modalita' nominava la modalita' sbagliata.** Quale modalita'
   servisse lo sceglieva il modello, e sceglieva quella per disegnare;
5. **il piano non aveva un loop di review.** Il canvas ce l'aveva.

Qui si verificano le invarianti che quelle cinque cose violavano. Servono la DSN
workspace e quelle canonical (`cd ops && docker compose up -d`).
"""

from __future__ import annotations

import json

import pytest

from backend.settings import settings

if not all((settings.workspace_database_url, settings.canonical_database_url)):
    pytest.skip(
        "servono WORKSPACE_DATABASE_URL e le DSN canonical",
        allow_module_level=True,
    )

from backend import workspace_database as wd  # noqa: E402
from backend.agents.process_plan import (  # noqa: E402
    merge_process_understanding,
    review_process_plan,
    write_process_plan,
)
from backend.agents.process_snapshot import build_process_snapshot  # noqa: E402
from backend.graphs.process.graph import (  # noqa: E402
    build_canvas_delegation_node,
    evaluate_plan_review,
    misdirected_plan_request,
    process_routing_state,
    route_after_plan_review,
)
from backend.graphs.routing_contracts import (  # noqa: E402
    CAPABILITY_REGISTRY,
    ProcessRoutingDecision,
    authorize_routing_decision,
    narrowest_mode_for,
)
from backend.process_understanding import (  # noqa: E402
    ProcessActor,
    ProcessFlowEdge,
    ProcessPath,
    ProcessStep,
    ProcessUnderstanding,
)

from tests.test_process_canvas_handoff_e2e import (  # noqa: E402
    _bind_process_chat,
    _save_interviews,
    _supported_understanding,
    empty_process,  # noqa: F401 - fixture
)


# Un canvas che non modella niente e che nomina un passaggio del piano dentro
# una nota. Serve a distinguere "rappresentato" da "citato".
START_END_WITH_NOTE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                  id="Definitions_note" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_note" isExecutable="false">
    <bpmn:startEvent id="StartEvent_1" name="Inizio">
      <bpmn:outgoing>Flow_1</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:endEvent id="EndEvent_1" name="Fine">
      <bpmn:incoming>Flow_1</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="EndEvent_1" />
    <bpmn:textAnnotation id="Note_1">
      <bpmn:text>Crea e invia ordine al fornitore</bpmn:text>
    </bpmn:textAnnotation>
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_note">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="160" y="100" width="36" height="36" />
      </bpmndi:BPMNShape>
      <bpmndi:BPMNShape id="EndEvent_1_di" bpmnElement="EndEvent_1">
        <dc:Bounds x="320" y="100" width="36" height="36" />
      </bpmndi:BPMNShape>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>
"""


@pytest.fixture(autouse=True)
def _no_live_model(monkeypatch):
    """Qui si verifica il contratto fra artefatti, non la qualita' dell'LLM."""
    monkeypatch.setattr(settings, "openai_api_key", None)


@pytest.fixture()
def interviewed_process(empty_process):
    """Tre interviste agli atti e nessun piano: lo stato reale del difetto."""
    _save_interviews(empty_process)
    return empty_process


@pytest.fixture()
def planned_process(interviewed_process):
    """Le tre interviste e un piano scritto su quelle."""
    with _bind_process_chat(
        interviewed_process["project_id"], interviewed_process["process_id"]
    ):
        result = write_process_plan(
            interviewed_process["process_id"],
            _supported_understanding(),
            strategy="replace",
            change_summary="Piano iniziale dalle tre interviste.",
        )
    assert result.persisted, result.reason
    return interviewed_process


def _plan_decision(**overrides) -> ProcessRoutingDecision:
    return ProcessRoutingDecision(
        route=overrides.pop("route", "modeling"),
        suggested_capability=overrides.pop("suggested_capability", "process.plan_edit"),
        target_artifact=overrides.pop("target_artifact", "modeling_plan"),
        **overrides,
    )


def _tool_payload(output: str) -> dict:
    return json.loads(output.split("\n", 1)[1])


# --- TEST 1 — l'intento sceglie l'artefatto -------------------------------


def test_a_plan_request_is_not_a_canvas_request(planned_process):
    """"Mettilo nel piano" non e' "disegnalo", e il runtime lo sa senza chiedere.

    Il router puo' ancora sbagliare la route - classificare l'intento e' lavoro
    del modello. Cio' che non puo' piu' succedere e' che la richiesta arrivi al
    canvas: l'artefatto dichiarato e l'artefatto della capability devono essere
    lo stesso, e quando non lo sono il runtime rifiuta l'accoppiamento.
    """
    decision = _plan_decision(
        route="delegate_canvas", suggested_capability="process.canvas_handoff"
    )
    authorization = authorize_routing_decision(
        owner="process",
        decision=decision,
        state={"chat_mode": "agent", "process_id": planned_process["process_id"]},
        parse_source="structured",
        parse_error=None,
    )
    assert authorization["status"] == "artifact_route_mismatch"
    assert authorization["route"] == "clarification"


def test_a_plan_request_routed_to_the_canvas_lands_on_the_plan(planned_process):
    """Rifiutare non basta: la richiesta deve finire dove appartiene."""
    decision = _plan_decision(
        route="delegate_canvas", suggested_capability="process.canvas_handoff"
    )
    state = process_routing_state(
        decision,
        user_request="mettilo nel piano",
        state={"chat_mode": "agent", "process_id": planned_process["process_id"]},
    )
    assert state["process_route"] == "modeling"
    assert state["authorized_capability"] == "process.plan_edit"
    assert state["target_artifact"] == "modeling_plan"


def test_editing_the_plan_does_not_ask_for_the_mode_that_draws():
    """La modalita' che sblocca il rifiuto la calcola il runtime, non il modello.

    Con la chat in conversazione entrambe le capability sono fuori, ma non allo
    stesso livello: il piano si modifica in Piano, il disegno si tocca da
    Modifica in su. Chiedere Modifica per scrivere sul piano e' la risposta che
    il consulente riceveva.
    """
    assert narrowest_mode_for(CAPABILITY_REGISTRY["process.plan_edit"]) == "plan"
    assert narrowest_mode_for(CAPABILITY_REGISTRY["process.canvas_handoff"]) == "edit"

    authorization = authorize_routing_decision(
        owner="process",
        decision=_plan_decision(),
        state={"chat_mode": "conversation", "process_id": "p"},
        parse_source="structured",
        parse_error=None,
    )
    assert authorization["status"] == "capability_not_in_mode"
    assert authorization["required_mode"] == "plan"
    assert authorization["active_chat_mode"] == "conversation"


def test_the_mode_state_comes_from_the_runtime_not_from_what_the_user_said():
    """Un "si', fatto" nel messaggio non cambia la modalita' del turno."""
    authorization = authorize_routing_decision(
        owner="process",
        decision=_plan_decision(),
        state={"chat_mode": "conversation", "process_id": "p"},
        parse_source="structured",
        parse_error=None,
    )
    # Lo stato riportato e' quello che il runtime ha applicato, non quello che il
    # turno precedente aveva chiesto all'utente di attivare.
    assert authorization["active_chat_mode"] == "conversation"
    assert authorization["status"] == "capability_not_in_mode"


def test_a_plan_request_never_crosses_into_the_canvas(planned_process):
    """L'ultimo punto in cui i due artefatti si potevano ancora confondere."""
    invoked: list[dict] = []

    class _Canvas:
        def invoke(self, payload, config=None):
            invoked.append(payload)
            return {}

    delegate = build_canvas_delegation_node(_Canvas())
    result = delegate(
        {
            "process_id": planned_process["process_id"],
            "project_id": planned_process["project_id"],
            "bpmn_model_id": planned_process["bpmn_model_id"],
            "target_artifact": "modeling_plan",
            "delegation_payload": {"target_artifact": "modeling_plan"},
            "messages": [],
        },
        config=None,
    )
    assert invoked == []
    assert result["delegation_events"][0]["status"] == "blocked"


# --- TEST 2 — la struttura sopravvive alla persistenza --------------------


def test_the_structure_survives_persistence_and_reload(interviewed_process):
    """Pool, corsie, attivita', percorso principale, percorso urgente, lacune.

    Il ragionamento ricco arrivava alla chat e non arrivava all'artefatto: dopo
    la persistenza restavano pochi bullet generici. Qui si verifica che cio' che
    entra nel piano si rilegga uguale, voce per voce.
    """
    understanding = _supported_understanding()
    with _bind_process_chat(
        interviewed_process["project_id"], interviewed_process["process_id"]
    ):
        result = write_process_plan(
            interviewed_process["process_id"],
            understanding,
            strategy="replace",
            change_summary="AS-IS preliminare dalle tre interviste.",
        )
    assert result.persisted, result.reason

    reloaded = build_process_snapshot(interviewed_process["process_id"])
    plan = reloaded.process_understanding
    assert {actor["label"] for actor in plan["actors"]} >= {
        "Ufficio Tecnico",
        "Ufficio Acquisti",
        "Manutenzione",
    }
    assert {step["id"] for step in plan["steps"]} >= {
        "apri_richiesta",
        "verifica_autorizzazione",
        "firma_direttore",
        "crea_ordine",
        "chiama_fornitore",
    }
    assert plan["main_success_path"] == [
        "apri_richiesta",
        "verifica_autorizzazione",
        "crea_ordine",
    ]
    assert [path["id"] for path in plan["alternative_paths"]] == ["sopra_soglia"]
    assert [item["id"] for item in plan["exceptions"]] == ["linea_ferma"]
    assert [item["label"] for item in plan["decisions"]] == [
        "Importo sopra i cinquemila euro?"
    ]
    assert [item["question"] for item in plan["unknowns"]]


def test_an_amendment_adds_without_erasing_what_the_plan_knew(planned_process):
    """"Mettilo nel piano" aggiunge. Non riscrive, e non cancella per omissione.

    Un emendamento che porta il percorso urgente non ripete le tre corsie: se
    ripeterle fosse obbligatorio, ogni modifica parziale cancellerebbe il piano
    intorno a se', e una dimenticanza del turno diventerebbe una lacuna del
    processo.
    """
    before = build_process_snapshot(planned_process["process_id"])
    before_steps = {step["id"] for step in before.process_understanding["steps"]}

    amendment = ProcessUnderstanding(
        title="Gestione acquisto materiali indiretti e servizi",
        actors=[ProcessActor(id="amministrazione", label="Amministrazione", kind="team")],
        steps=[
            ProcessStep(
                id="verifica_fattura",
                label="Verifica la fattura contro l'ordine",
                actor_ids=["amministrazione"],
            )
        ],
        alternative_paths=[
            ProcessPath(
                id="verifica_amministrativa",
                label="Verifica amministrativa della fattura",
                sequence=["verifica_fattura"],
            )
        ],
        flow_edges=[
            ProcessFlowEdge(
                id="ordine_to_fattura",
                source_id="crea_ordine",
                target_id="verifica_fattura",
                label="Fattura ricevuta",
            )
        ],
    )
    with _bind_process_chat(planned_process["project_id"], planned_process["process_id"]):
        result = write_process_plan(
            planned_process["process_id"],
            amendment,
            strategy="amend",
            change_summary="Aggiunta la verifica fattura.",
        )
    assert result.persisted, result.reason

    after = build_process_snapshot(planned_process["process_id"])
    after_steps = {step["id"] for step in after.process_understanding["steps"]}
    assert before_steps <= after_steps
    assert "verifica_fattura" in after_steps
    assert "Amministrazione" in {
        actor["label"] for actor in after.process_understanding["actors"]
    }
    # Il percorso principale non e' stato dichiarato dall'emendamento: resta.
    assert after.process_understanding["main_success_path"] == before.process_understanding[
        "main_success_path"
    ]


def test_a_real_gap_stays_a_gap_and_does_not_delete_what_is_known():
    """Una lacuna aperta non cancella le attivita' che le stanno intorno."""
    base = _supported_understanding()
    merged, _ = merge_process_understanding(
        base,
        {
            "title": base.title,
            "unknowns": [
                {
                    "question": "Chi firma sopra i ventimila euro?",
                    "affects": "soglia di firma",
                    "severity": "non_blocking",
                    "grounded_in": "Francesca parla della soglia dei cinquemila, non oltre.",
                }
            ],
        },
    )
    assert len(merged.steps) == len(base.steps)
    assert len(merged.unknowns) == len(base.unknowns) + 1


# --- TEST 3 — il piano e' persistito e versionato -------------------------


def test_the_plan_is_versioned_and_reads_back_identical_after_reload(planned_process):
    """Scrivi, rileggi la stessa versione, riapri: stesso contenuto."""
    first = build_process_snapshot(planned_process["process_id"])

    with _bind_process_chat(planned_process["project_id"], planned_process["process_id"]):
        result = write_process_plan(
            planned_process["process_id"],
            ProcessUnderstanding(
                title="Gestione acquisto materiali indiretti e servizi",
                actors=[
                    ProcessActor(id="amministrazione", label="Amministrazione", kind="team")
                ],
                steps=[
                    ProcessStep(
                        id="verifica_fattura",
                        label="Verifica la fattura contro l'ordine",
                        actor_ids=["amministrazione"],
                    )
                ],
                flow_edges=[
                    ProcessFlowEdge(
                        id="ordine_to_fattura",
                        source_id="crea_ordine",
                        target_id="verifica_fattura",
                        label="Fattura ricevuta",
                    )
                ],
            ),
            strategy="amend",
            change_summary="Verifica fattura.",
        )
    assert result.version == first.version + 1

    # Una sessione nuova: nessuno stato di grafo, solo il database.
    reopened = build_process_snapshot(planned_process["process_id"])
    assert reopened.version == result.version
    assert reopened.snapshot_id != first.snapshot_id
    assert "verifica_fattura" in {
        step["id"] for step in reopened.process_understanding["steps"]
    }

    # La versione precedente resta leggibile: il piano si versiona, non si
    # sovrascrive.
    previous = wd.get_bpmn_review_version(planned_process["bpmn_model_id"], first.version)
    assert previous is not None


def test_editing_the_plan_leaves_the_diagram_untouched(planned_process):
    """Modificare il piano non disegna niente: sono due artefatti."""
    before = (wd.get_bpmn_model(planned_process["bpmn_model_id"]) or {}).get("xml")

    with _bind_process_chat(planned_process["project_id"], planned_process["process_id"]):
        write_process_plan(
            planned_process["process_id"],
            ProcessUnderstanding(
                title="Gestione acquisto materiali indiretti e servizi",
                actors=[
                    ProcessActor(id="amministrazione", label="Amministrazione", kind="team")
                ],
                steps=[
                    ProcessStep(
                        id="verifica_fattura",
                        label="Verifica la fattura",
                        actor_ids=["amministrazione"],
                    )
                ],
                flow_edges=[
                    ProcessFlowEdge(
                        id="ordine_to_fattura",
                        source_id="crea_ordine",
                        target_id="verifica_fattura",
                        label="Fattura ricevuta",
                    )
                ],
            ),
            strategy="amend",
        )

    after = (wd.get_bpmn_model(planned_process["bpmn_model_id"]) or {}).get("xml")
    assert after == before


# --- TEST 4 — bozza e validazione sono due soglie -------------------------


def test_a_plan_with_open_gaps_is_drawable_but_not_validated(planned_process):
    """Il dataset basta per una bozza e non basta per dichiarare l'AS-IS.

    Erano la stessa soglia, e la seconda vinceva: una domanda aperta impediva di
    disegnare un flusso che le interviste descrivevano gia'.
    """
    snapshot = build_process_snapshot(planned_process["process_id"])
    review = review_process_plan(snapshot)

    assert review.draft_allowed is True
    assert review.validation_complete is False
    # E il piano non si riduce a inizio e fine.
    assert len(snapshot.process_understanding["steps"]) >= 4


def test_evidence_from_one_voice_still_reaches_the_draft(planned_process):
    """Il passaggio che dice solo Paolo resta nel piano, non viene tolto."""
    snapshot = build_process_snapshot(planned_process["process_id"])
    steps = {step["id"] for step in snapshot.process_understanding["steps"]}
    assert "chiama_fornitore" in steps


# --- TEST 5 — dal piano approvato al BPMN ---------------------------------


def test_a_rich_plan_is_what_the_canvas_gate_asks_for(planned_process):
    """Con un piano cosi', il passaggio al disegno non ha prerequisiti mancanti."""
    from backend.graphs.process.nodes import load_process_context
    from backend.graphs.routing_contracts import missing_prerequisites

    state = {
        **load_process_context({"process_id": planned_process["process_id"]}),
        "process_id": planned_process["process_id"],
        "project_id": planned_process["project_id"],
    }
    missing = missing_prerequisites(CAPABILITY_REGISTRY["process.canvas_handoff"], state)
    assert missing == []


def test_the_canvas_request_is_not_rerouted_to_the_plan(planned_process):
    """La separazione vale in entrambi i versi: "genera il BPMN" va al disegno."""
    decision = ProcessRoutingDecision(
        route="delegate_canvas",
        suggested_capability="process.canvas_handoff",
        target_artifact="bpmn_canvas",
    )
    assert (
        misdirected_plan_request(
            decision=decision, status="authorized", state={"chat_mode": "agent"}
        )
        is None
    )
    from backend.graphs.process.nodes import load_process_context

    authorization = authorize_routing_decision(
        owner="process",
        decision=decision,
        state={
            **load_process_context({"process_id": planned_process["process_id"]}),
            "chat_mode": "agent",
            "process_id": planned_process["process_id"],
            "project_id": planned_process["project_id"],
        },
        parse_source="structured",
        parse_error=None,
    )
    assert authorization["status"] == "authorized"
    assert authorization["route"] == "delegate_canvas"


# --- TEST 6 — la modalita' non blocca cio' che non deve bloccare ----------


def test_reading_and_reviewing_the_plan_does_not_depend_on_a_canvas_mode():
    """Il giudizio sul piano si forma senza nessuna modalita' di scrittura."""
    assert "plan" in CAPABILITY_REGISTRY["process.plan_edit"].modes
    assert "edit" not in CAPABILITY_REGISTRY["process.plan_edit"].modes
    assert CAPABILITY_REGISTRY["process.plan_edit"].artifact == "modeling_plan"
    assert CAPABILITY_REGISTRY["process.canvas_handoff"].artifact == "bpmn_canvas"


def test_a_plan_capability_is_allowed_in_plan_mode(planned_process):
    authorization = authorize_routing_decision(
        owner="process",
        decision=_plan_decision(),
        state={"chat_mode": "plan", "process_id": planned_process["process_id"]},
        parse_source="structured",
        parse_error=None,
    )
    assert authorization["status"] == "authorized"
    assert authorization["authorized_capability"] == "process.plan_edit"


# --- TEST 7 — nessun successo senza rilettura -----------------------------


def test_a_write_that_does_not_persist_is_not_reported_as_saved(
    planned_process, monkeypatch
):
    """Forzato il fallimento della scrittura: nessun "salvato", e il piano intatto."""
    from backend.agents import process_plan as plan_module

    before = build_process_snapshot(planned_process["process_id"])

    def _explode(*_args, **_kwargs):
        raise plan_module.PersistenceVerificationError(
            "La review riletta e' alla versione precedente."
        )

    monkeypatch.setattr(plan_module, "verify_review_persisted", _explode)
    with _bind_process_chat(planned_process["project_id"], planned_process["process_id"]):
        result = write_process_plan(
            planned_process["process_id"],
            ProcessUnderstanding(
                title="x",
                actors=[ProcessActor(id="a", label="A", kind="team")],
                steps=[ProcessStep(id="s", label="S", actor_ids=["a"])],
            ),
            strategy="amend",
        )

    assert result.action == "write_failed"
    assert result.persisted is False
    assert "salvat" not in result.reason.casefold()

    # La versione precedente resta leggibile e con il suo contenuto.
    after = build_process_snapshot(planned_process["process_id"])
    assert {step["id"] for step in after.process_understanding["steps"]} >= {
        step["id"] for step in before.process_understanding["steps"]
    }


def test_a_plan_that_would_erase_the_evidence_is_refused(planned_process):
    """Un piano vuoto su un processo con fonti agli atti non si salva."""
    with _bind_process_chat(planned_process["project_id"], planned_process["process_id"]):
        result = write_process_plan(
            planned_process["process_id"],
            ProcessUnderstanding(title="Solo il titolo"),
            strategy="replace",
        )
    assert result.action == "rejected_empty_plan"
    assert result.persisted is False


def test_an_amendment_that_changes_nothing_does_not_raise_the_version(planned_process):
    """Non far salire la versione e' parte dell'onesta': il Canvas legge quel numero."""
    before = build_process_snapshot(planned_process["process_id"])
    with _bind_process_chat(planned_process["project_id"], planned_process["process_id"]):
        result = write_process_plan(
            planned_process["process_id"],
            _supported_understanding(),
            strategy="amend",
        )
    assert result.action == "unchanged"
    after = build_process_snapshot(planned_process["process_id"])
    assert after.version == before.version


# --- il loop di review del piano ------------------------------------------


def test_the_plan_review_loop_sends_a_collapsed_plan_back_to_be_fixed(
    interviewed_process,
):
    """Un piano collassato non esce come "passata completata"."""
    with _bind_process_chat(
        interviewed_process["project_id"], interviewed_process["process_id"]
    ):
        write_process_plan(
            interviewed_process["process_id"],
            ProcessUnderstanding(
                title="Gestione acquisto materiali indiretti e servizi",
                actors=[ProcessActor(id="a1", label="Ufficio Acquisti", kind="team")],
                # Un'attivita' sola, senza nessun percorso che la agganci: e' il
                # piano che usciva come completato.
                steps=[ProcessStep(id="s1", label="Fai qualcosa", actor_ids=["a1"])],
            ),
            strategy="replace",
        )

    state = {
        "process_id": interviewed_process["process_id"],
        "plan_review_attempt": 0,
        "plan_review": None,
    }
    result = evaluate_plan_review(state)
    assert result["plan_review"]["issues"]
    assert result["plan_review_continue"] is True
    assert route_after_plan_review(result) == "modeling_subgraph"


def test_the_plan_review_loop_stops_instead_of_spinning(interviewed_process):
    """Gli stessi difetti due volte non valgono un'altra passata."""
    with _bind_process_chat(
        interviewed_process["project_id"], interviewed_process["process_id"]
    ):
        write_process_plan(
            interviewed_process["process_id"],
            ProcessUnderstanding(
                title="Gestione acquisto materiali indiretti e servizi",
                actors=[ProcessActor(id="a1", label="Ufficio Acquisti", kind="team")],
                steps=[ProcessStep(id="s1", label="Fai qualcosa", actor_ids=["a1"])],
            ),
            strategy="replace",
        )

    first = evaluate_plan_review(
        {"process_id": interviewed_process["process_id"], "plan_review_attempt": 0}
    )
    second = evaluate_plan_review(
        {
            "process_id": interviewed_process["process_id"],
            "plan_review_attempt": first["plan_review_attempt"],
            "plan_review": first["plan_review"],
        }
    )
    assert second["plan_review_continue"] is False
    assert route_after_plan_review(second) == "evaluate_process_iteration"
    assert second["blocking_conditions"]


def test_a_plan_that_holds_passes_the_review_without_a_second_pass(planned_process):
    result = evaluate_plan_review(
        {"process_id": planned_process["process_id"], "plan_review_attempt": 0}
    )
    assert result["plan_review"]["issues"] == []
    assert result["plan_review"]["draft_allowed"] is True
    assert result["plan_review"]["validation_complete"] is False
    assert result.get("plan_review_continue") is False


# --- i difetti che la review del codice ha trovato dopo -------------------


def test_the_substitution_still_goes_through_the_gate(planned_process):
    """Reinstradare non e' autorizzare.

    La sostituzione asseriva route e capability a mano: una capability che nessuno
    aveva autorizzato partiva perche' il runtime l'aveva scelta. In conversazione
    il lavoro sul piano non e' permesso, e il consulente deve leggere quello - non
    vedere il piano riscritto perche' il runtime ha rimediato a un errore di
    instradamento.
    """
    decision = _plan_decision(
        route="delegate_canvas", suggested_capability="process.canvas_handoff"
    )
    state = process_routing_state(
        decision,
        user_request="mettilo nel piano",
        state={"chat_mode": "conversation", "process_id": planned_process["process_id"]},
    )
    assert state["process_route"] == "clarification"
    assert state["orchestration_status"] == "capability_not_in_mode"
    assert state["required_chat_mode"] == "plan"


def test_a_refusal_for_its_own_reason_is_not_overwritten_by_the_reroute():
    """Un prerequisito mancante resta la ragione vera del rifiuto."""
    decision = _plan_decision(
        route="delegate_canvas", suggested_capability="process.canvas_handoff"
    )
    # Nessun process_id: il rifiuto e' per prerequisito, non per artefatto.
    assert (
        misdirected_plan_request(
            decision=decision, status="missing_prerequisite", state={"chat_mode": "agent"}
        )
        is None
    )


def test_a_blocking_gap_closes_the_canvas_even_on_a_drawable_plan(planned_process):
    """Le due soglie sono due, ma "bloccante" chiude comunque.

    Le scorciatoie della soglia bozza uscivano dal gate prima del controllo sulle
    lacune: una lacuna che l'agente ha classificato bloccante apriva il canvas, e
    una bozza con dentro una lacuna bloccante non e' una bozza onesta.
    """
    from backend.graphs.process.nodes import load_process_context
    from backend.graphs.routing_contracts import missing_prerequisites

    state = {
        **load_process_context({"process_id": planned_process["process_id"]}),
        "process_id": planned_process["process_id"],
        "project_id": planned_process["project_id"],
    }
    assert missing_prerequisites(CAPABILITY_REGISTRY["process.canvas_handoff"], state) == []

    blocked = {
        **state,
        "process_gaps": [
            {"title": "Chi autorizza sopra soglia", "severity": "blocking"}
        ],
    }
    assert missing_prerequisites(
        CAPABILITY_REGISTRY["process.canvas_handoff"], blocked
    ) == ["readiness_for_canvas"]


def test_rebuilding_from_prose_does_not_erase_the_plan_provenance(planned_process):
    """Un chiamante che non conosce il set di fonti non lo cancella."""
    before = wd.get_bpmn_review(planned_process["bpmn_model_id"], include_approved=True)
    assert before["evidence_source_set_id"]

    with _bind_process_chat(planned_process["project_id"], planned_process["process_id"]):
        wd.prepare_bpmn_review(
            bpmn_model_id=planned_process["bpmn_model_id"],
            process_description="Una riscrittura che non dichiara le fonti.",
            process_understanding=_supported_understanding().model_dump(mode="json"),
        )

    after = wd.get_bpmn_review(planned_process["bpmn_model_id"], include_approved=True)
    assert after["evidence_source_set_id"] == before["evidence_source_set_id"]


def test_the_plan_history_says_which_sources_each_version_was_built_on(planned_process):
    versions = wd.list_bpmn_review_versions(planned_process["bpmn_model_id"])
    assert versions
    assert any(item.get("evidence_source_set_id") for item in versions)


def test_a_plan_judged_not_modelable_is_not_overruled_by_counting_sources(
    planned_process,
):
    """Il conteggio delle fonti non ribalta il verdetto del piano.

    La scorciatoia "c'e' evidenza, il piano si puo' sintetizzare" serve dove il
    piano non c'e'. Applicata a un piano agli atti che si dichiara non
    modellabile, apriva il canvas contando le interviste che quel piano aveva
    gia' guardato per dire di no.
    """
    from backend.graphs.process.nodes import load_process_context
    from backend.graphs.routing_contracts import missing_prerequisites

    state = {
        **load_process_context({"process_id": planned_process["process_id"]}),
        "process_id": planned_process["process_id"],
        "project_id": planned_process["project_id"],
    }
    refused = {
        **state,
        "draft_readiness": {
            "status": "not_modelable",
            "blockers": ["Il flusso del piano non e' coerente."],
            "gaps": [],
        },
        "readiness_score": None,
    }
    assert missing_prerequisites(
        CAPABILITY_REGISTRY["process.canvas_handoff"], refused
    ) == ["readiness_for_canvas"]


def test_a_step_named_only_in_an_annotation_is_not_a_step_on_the_canvas():
    """Il metro non si lascia soddisfare da un commento.

    Il testo confrontato fondeva nomi e documentazione di ogni elemento,
    annotazioni comprese: un'attivita' del piano citata in una nota risultava
    rappresentata, e il controllo che deve accorgersi di un disegno vuoto
    passava.
    """
    from backend.process_understanding import ProcessUnderstanding
    from backend.workspace_services.bpmn_canvas_validation import (
        validate_canvas_against_process,
    )

    annotated_xml = START_END_WITH_NOTE_XML
    plan = ProcessUnderstanding(
        title="Ciclo passivo",
        actors=[ProcessActor(id="a1", label="Ufficio Acquisti", kind="team")],
        steps=[
            ProcessStep(
                id="crea_ordine",
                label="Crea e invia ordine al fornitore",
                actor_ids=["a1"],
            )
        ],
        main_success_path=["crea_ordine"],
    )
    report = validate_canvas_against_process(
        xml=annotated_xml,
        process_understanding=plan.model_dump(mode="json"),
        bpmn_semantic_model=None,
    )
    assert any("non ne rappresenta nessuna" in issue for issue in report["issues"])


def test_the_construction_check_survives_the_first_fix_attempt(planned_process):
    """Il controllo di verificabilita' non sparisce quando il loop corregge.

    `evaluate_canvas_completion` riscrive `canvas_route` in "patch_edit" al primo
    giro di correzione: letto da li', il controllo sulla costruzione spariva
    proprio quando serviva, e un disegno non verificabile usciva come completato.
    """
    from backend.agents.process_snapshot import build_process_snapshot
    from backend.graphs.canvas_edit.graph import _unverifiable_completion_issues

    # Uno snapshot con evidenza agli atti e senza piano: non c'e' niente contro
    # cui confrontare il disegno.
    snapshot = build_process_snapshot(planned_process["process_id"]).model_copy(
        update={"bpmn_semantic_model": None}
    )

    first_pass = {"canvas_initial_route": "construction", "canvas_route": "construction"}
    after_fix = {"canvas_initial_route": "construction", "canvas_route": "patch_edit"}

    assert _unverifiable_completion_issues(first_pass, snapshot, False)
    assert _unverifiable_completion_issues(after_fix, snapshot, False)

    # Una modifica locale nata come tale non deve pretendere un piano.
    local_only = {"canvas_initial_route": "patch_edit", "canvas_route": "patch_edit"}
    assert _unverifiable_completion_issues(local_only, snapshot, False) == []


# --- TEST 8 — il giro intero ----------------------------------------------


def test_from_three_interviews_to_a_plan_to_a_diagram(interviewed_process):
    """Tre interviste -> piano -> modifica del piano -> disegno, senza perdite.

    E' il percorso reale, con le due operazioni tenute separate: la modifica del
    piano non tocca il disegno, e il disegno arriva dopo, su un piano che a quel
    punto contiene sia cio' che c'era sia cio' che e' stato aggiunto.
    """
    from backend.workspace_services.bpmn_review import bpmn_xml_from_review

    with _bind_process_chat(
        interviewed_process["project_id"], interviewed_process["process_id"]
    ):
        created = write_process_plan(
            interviewed_process["process_id"],
            _supported_understanding(),
            strategy="replace",
            change_summary="AS-IS preliminare.",
        )
        assert created.persisted

        amended = write_process_plan(
            interviewed_process["process_id"],
            ProcessUnderstanding(
                title="Gestione acquisto materiali indiretti e servizi",
                actors=[
                    ProcessActor(id="amministrazione", label="Amministrazione", kind="team")
                ],
                steps=[
                    ProcessStep(
                        id="verifica_fattura",
                        label="Verifica la fattura contro l'ordine",
                        actor_ids=["amministrazione"],
                    )
                ],
                flow_edges=[
                    ProcessFlowEdge(
                        id="ordine_to_fattura",
                        source_id="crea_ordine",
                        target_id="verifica_fattura",
                        label="Fattura ricevuta",
                    )
                ],
            ),
            strategy="amend",
            change_summary="Verifica fattura di Francesca.",
        )
        assert amended.persisted
        assert amended.version == created.version + 1

    # Riletto da zero: entrambe le scritture sono li'.
    reopened = build_process_snapshot(interviewed_process["process_id"])
    steps = {step["id"] for step in reopened.process_understanding["steps"]}
    assert {"apri_richiesta", "chiama_fornitore", "verifica_fattura"} <= steps

    # Il piano regge la review e la bozza e' autorizzata.
    review = review_process_plan(reopened)
    assert review.is_clean, review.issues
    assert review.draft_allowed is True

    # E da quel piano esce un BPMN che rappresenta il processo, non start -> end.
    stored = wd.get_bpmn_review(interviewed_process["bpmn_model_id"], include_approved=True)
    xml = bpmn_xml_from_review(json.dumps(stored["bpmn_semantic_model"]))
    assert "verifica la fattura" in xml.casefold()
    assert "chiama direttamente il fornitore" in xml.casefold()
