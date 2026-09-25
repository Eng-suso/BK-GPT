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
    list_project_processes,
    list_projects,
)

#: Lo spazio di lavoro che il frontend manda quando nessuno configura niente
#: (`frontend/src/lib/security.ts`). Il seed deve stare li', altrimenti l'e2e
#: apre un workspace vuoto e non lo capisce.
TENANT_ID = "local"

CLIENT_NAME = "Esaote S.p.A."
PROJECT_NAME = "Riorganizzazione ciclo passivo"
PROCESS_NAME = "Ciclo passivo"


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

    return {
        "tenant_id": TENANT_ID,
        "client_id": client["id"],
        "client_name": CLIENT_NAME,
        "project_id": project["id"],
        "project_name": PROJECT_NAME,
        "process_id": process["id"],
        "process_name": PROCESS_NAME,
        "bpmn_model_id": process["bpmn_model_id"],
    }


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
