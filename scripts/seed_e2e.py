"""Il workspace minimo su cui gira l'e2e full-stack.

Le spec di `e2e/` sostituiscono il backend con `page.route`: verificano che
l'interfaccia sappia disegnare una risposta, non che il prodotto la produca. Per
attraversarlo davvero serve un workspace vero, e serve che sia sempre lo stesso,
altrimenti un test che passa non dice se ha funzionato il prodotto o la fortuna.

Questo script scrive quel workspace e stampa i suoi id, cosi' le spec possono
aprire un indirizzo profondo senza indovinarlo.

Uso:

    uv run python -m scripts.seed_e2e                  # scrive e stampa il manifesto
    uv run python -m scripts.seed_e2e --out seed.json  # e lo salva

E' idempotente: `create_client` unisce per nome, e progetti e processi vengono
riusati quando esistono gia' con lo stesso nome nello stesso posto. Rilanciarlo
non moltiplica le righe.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.local_store import ensure_schema
from backend.security import set_current_tenant_id
from backend.workspace_database import (
    create_client,
    create_process,
    create_project,
    get_bpmn_review,
    list_project_processes,
    list_projects,
    prepare_bpmn_review,
)

#: Lo spazio di lavoro che il frontend manda quando nessuno configura niente
#: (`frontend/src/lib/security.ts`). Il seed deve stare li', altrimenti l'e2e
#: apre un workspace vuoto e non lo capisce.
TENANT_ID = "local"

CLIENT_NAME = "Esaote S.p.A."
PROJECT_NAME = "Riorganizzazione ciclo passivo"
PROCESS_NAME = "Ciclo passivo"
#: Un processo il cui piano, approvato, darebbe un disegno in deadlock: una
#: scelta esclusiva che finisce in un gateway parallelo. Serve a provare che il
#: gate L3 al salvataggio arriva al consulente come frase leggibile.
DEADLOCK_PROCESS_NAME = "Approvazione fatture"


def _existing_project(client_id: str, name: str) -> dict | None:
    for project in list_projects():
        if project["name"] == name and project.get("client_id") == client_id:
            return project
    return None


def _existing_process(project_id: str, name: str) -> dict | None:
    for process in list_project_processes(project_id):
        if process["name"] == name:
            return process
    return None


def seed() -> dict[str, str]:
    """Scrive il workspace di prova e restituisce i suoi id.

    Returns:
        dict[str, str]: `client_id`, `project_id`, `process_id`, `bpmn_model_id`
            e i nomi, che le spec usano per cercare le righe a schermo.
    """
    # Il database di un job CI nasce vuoto e il seed gira prima che l'app parta:
    # portare lo schema a head qui e' cio' che rende lo script bastante a se'
    # stesso, invece di dipendere dall'ordine dei passi del workflow.
    ensure_schema()
    set_current_tenant_id(TENANT_ID)

    client = create_client(
        name=CLIENT_NAME,
        sector="Medicale",
        status="Attivo",
        owner="Studio DeliR",
        contact="operations@esaote.example",
    )

    project = _existing_project(client["id"], PROJECT_NAME) or create_project(
        client_id=client["id"],
        name=PROJECT_NAME,
        objective="Ricostruire l'AS-IS del ciclo passivo e simularlo.",
        phase="Discovery",
        status="In corso",
    )

    process = _existing_process(project["id"], PROCESS_NAME) or create_process(
        project_id=project["id"],
        name=PROCESS_NAME,
        stage="AS-IS",
        owner="Amministrazione",
    )

    deadlock_process = _existing_process(project["id"], DEADLOCK_PROCESS_NAME) or create_process(
        project_id=project["id"],
        name=DEADLOCK_PROCESS_NAME,
        stage="AS-IS",
        owner="Amministrazione",
    )
    _seed_deadlocking_review(deadlock_process["bpmn_model_id"])

    return {
        "tenant_id": TENANT_ID,
        "client_id": client["id"],
        "client_name": CLIENT_NAME,
        "project_id": project["id"],
        "project_name": PROJECT_NAME,
        "process_id": process["id"],
        "process_name": PROCESS_NAME,
        "bpmn_model_id": process["bpmn_model_id"],
        "deadlock_process_id": deadlock_process["id"],
        "deadlock_process_name": DEADLOCK_PROCESS_NAME,
        "deadlock_bpmn_model_id": deadlock_process["bpmn_model_id"],
    }


def _seed_deadlocking_review(bpmn_model_id: str) -> None:
    """Un piano pendente che supera la prontezza ma non il gate L3.

    Il piano passa da `prepare_bpmn_review` come ogni piano vero; poi il seed
    ne riscrive il flusso e il giudizio di qualita'. Nessun estrattore gira in
    e2e (`DELIR_FAKE_LLM`), e un piano estratto non conterrebbe questo errore:
    qui serve proprio un flusso che l'analisi del piano (`soundness.py`) lascia
    passare e quella a token del disegno rifiuta. Rilanciare il seed lo riporta
    pendente e identico.
    """
    from backend.bpmn import BPMNSemanticModel
    from backend.process_understanding import ProcessActor, ProcessStep, ProcessUnderstanding
    from backend.workspace_storage import WorkspaceBpmnReview, workspace_connection

    if get_bpmn_review(bpmn_model_id) is None:
        understanding = ProcessUnderstanding(
            title=DEADLOCK_PROCESS_NAME,
            actors=[ProcessActor(id="Amministrazione", label="Amministrazione", kind="team")],
            steps=[ProcessStep(id="Task_Registra", label="Registra fattura", actor_ids=["Amministrazione"])],
            sequence=["Task_Registra"],
        )
        prepare_bpmn_review(
            bpmn_model_id=bpmn_model_id,
            process_description="L'amministrazione riceve la fattura, la verifica e la registra.",
            process_understanding=understanding.model_dump(mode="json"),
        )
    flow = BPMNSemanticModel(
        id="Process_approvazione_fatture",
        name=DEADLOCK_PROCESS_NAME,
        flowNodes=[
            {"id": "Start", "type": "startEvent", "name": "Fattura ricevuta"},
            {"id": "Soglia", "type": "exclusiveGateway", "name": "Importo sopra soglia?"},
            {"id": "Direttore", "type": "userTask", "name": "Approvazione del direttore"},
            {"id": "Diretta", "type": "userTask", "name": "Registrazione diretta"},
            {"id": "Sync", "type": "parallelGateway", "name": "Entrambe le verifiche concluse"},
            {"id": "End", "type": "endEvent", "name": "Fattura registrata"},
        ],
        sequenceFlows=[
            {"id": f"Flow_{index}", "sourceRef": source, "targetRef": target}
            for index, (source, target) in enumerate([
                ("Start", "Soglia"), ("Soglia", "Direttore"), ("Soglia", "Diretta"),
                ("Direttore", "Sync"), ("Diretta", "Sync"), ("Sync", "End"),
            ])
        ],
    ).model_dump(mode="json")
    with workspace_connection() as session:
        review = session.get(WorkspaceBpmnReview, bpmn_model_id)
        stored = json.loads(review.bpmn_semantic_model_json)
        stored.update(flowNodes=flow["flowNodes"], sequenceFlows=flow["sequenceFlows"], lanes=[])
        stored["sourceProcessUnderstanding"]["quality_report"] = {
            "schema_version": "process_understanding_quality.v1",
            "overall_score": 9,
            "dimension_scores": [],
            "blocking_issues": [],
            "warnings": [],
            "improvement_actions": [],
            "approval_recommendation": "ready_to_generate",
        }
        review.bpmn_semantic_model_json = json.dumps(stored, ensure_ascii=False)
        review.status = "pending"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Dove salvare il manifesto. Senza, viene solo stampato.",
    )
    args = parser.parse_args()

    manifest = seed()
    payload = json.dumps(manifest, ensure_ascii=False, indent=2)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")

    print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
