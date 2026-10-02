"""Una fonte cambia quando cambia il suo testo, non solo quando cambia il nome.

L'identita' del set di fonti diceva *quali* fonti ci sono - id, nome, scope - e
non *cosa dicono*. Un'intervista corretta e risalvata con lo stesso titolo
lasciava quindi l'identita' ferma: il piano risultava "costruito sul set
corrente", nessuno lo risintetizzava, e il processo continuava a essere descritto
dal testo di prima. Un piano indietro senza sintomo, che e' il difetto peggiore.

Qui si verifica il rimedio e, soprattutto, la trappola che il rimedio poteva
aprire: l'identita' si calcola in **due** posti - il registro dell'evidenza, che
carica i testi, e lo sweep dei piani indietro, che legge i soli record - e se i
due divergessero ogni processo risulterebbe sempre indietro. Sarebbe una
ricostruzione del piano a ogni passata: l'esatto contrario del lavoro evitato.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from backend.settings import settings

if not settings.workspace_database_url:
    pytest.skip("serve WORKSPACE_DATABASE_URL", allow_module_level=True)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "interviews"
INTERVIEW = "a2_paolo_marchetti_manutenzione.md"
TITLE = "Intervista Paolo Marchetti - Manutenzione"


# --- l'impronta ------------------------------------------------------------


def test_the_digest_moves_only_when_the_text_moves():
    from backend.workspace_services.source_document import content_digest

    assert content_digest("le urgenze passano dal capo reparto") == content_digest(
        "le urgenze passano dal capo reparto"
    )
    assert content_digest("le urgenze passano dal capo reparto") != content_digest(
        "le urgenze passano dalla direzione"
    )


def test_a_trailing_newline_is_not_a_new_interview():
    """Un testo risalvato con un a capo in piu' non e' un'intervista diversa, e
    trattarlo come tale costerebbe una ricostruzione del piano per niente."""
    from backend.workspace_services.source_document import content_digest

    assert content_digest(" testo \n") == content_digest("testo")


def test_no_text_is_not_an_empty_text():
    """Il vuoto non e' un'impronta: dice "questa fonte non dichiara un
    contenuto", ed e' cio' che distingue un documento senza trascrizione da una
    trascrizione vuota."""
    from backend.workspace_services.source_document import content_digest

    assert content_digest(None) == ""
    assert content_digest("   ") == ""


# --- l'identita' del set ---------------------------------------------------


def _record(name: str, content_hash: str = "") -> dict:
    return {
        "id": f"src-{name}",
        "name": name,
        "project_id": "prj-1",
        "process_id": "prc-1",
        "content_hash": content_hash,
    }


def test_a_source_without_a_digest_keeps_the_identity_it_had():
    """La chiave e' condizionale, e la ragione e' la spesa: aggiungerla vuota a
    tutte le fonti gia' registrate cambierebbe ogni identita' salvata e mandera'
    in coda la risintesi di ogni processo, per un'informazione che non abbiamo.
    """
    from backend.graphs.process.nodes import source_set_identity

    senza_chiave = {
        key: value for key, value in _record("Paolo").items() if key != "content_hash"
    }

    assert source_set_identity([senza_chiave]) == source_set_identity([_record("Paolo")])


def test_the_identity_follows_the_text_of_a_source():
    from backend.graphs.process.nodes import source_set_identity

    prima = source_set_identity([_record("Paolo", "aaaa1111")])
    dopo = source_set_identity([_record("Paolo", "bbbb2222")])

    assert prima != dopo
    assert prima == source_set_identity([_record("Paolo", "aaaa1111")])


# --- il record della fonte -------------------------------------------------


@pytest.fixture()
def workspace():
    """Un progetto con un processo, in un tenant suo."""
    from backend import workspace_database as wd
    from backend.memory.episodic import episodic_store
    from backend.security import reset_current_tenant_id, set_current_tenant_id
    from sqlalchemy import text

    tenant = f"t-{uuid.uuid4().hex[:8]}"
    token = set_current_tenant_id(tenant)
    suffix = uuid.uuid4().hex[:8]
    client = wd.create_client(name=f"Contoso {suffix}")
    project = wd.create_project(client_id=client["id"], name=f"Manutenzione {suffix}")
    process = wd.create_process(project_id=project["id"], name="Richieste urgenti")
    try:
        yield {
            "tenant": tenant,
            "project": project["id"],
            "process": process["id"],
            "bpmn_model_id": wd.get_process(process["id"])["bpmn_model_id"],
        }
    finally:
        with episodic_store.episodic_connection() as session:
            session.execute(
                text("DELETE FROM episodes WHERE project = :p"), {"p": project["id"]}
            )
        reset_current_tenant_id(token)


def _drain_queue(process_id: str) -> None:
    """La coda lasciata dal salvataggio precedente, lavorata.

    Serve a rendere leggibile il test che segue: una riga `pending` gia' li'
    nasconderebbe se il caso in esame ne produce una nuova.
    """
    from backend import workspace_database as wd

    row = wd.plan_materialization_for(process_id)
    if row and row["status"] == "pending":
        wd.complete_plan_materialization(row["id"], action="synthesized", plan_version=1)


def test_the_same_source_with_a_new_text_is_not_the_same_source(workspace):
    from backend import workspace_database as wd

    fonte, creata = wd.ensure_project_source(
        project_id=workspace["project"],
        process_id=workspace["process"],
        name=TITLE,
        type="Intervista",
        meta="Prima versione.",
        content_hash="aaaa1111",
    )
    assert creata
    _drain_queue(workspace["process"])

    rivista, creata_di_nuovo = wd.ensure_project_source(
        project_id=workspace["project"],
        process_id=workspace["process"],
        name=TITLE,
        type="Intervista",
        meta="Prima versione.",
        content_hash="bbbb2222",
    )

    # Non e' una fonte nuova - il pannello Fonti non deve mostrarne due - ma il
    # suo testo e' cambiato, e il piano costruito su di lei e' da rifare.
    assert not creata_di_nuovo
    assert rivista["id"] == fonte["id"]
    assert rivista["content_hash"] == "bbbb2222"
    in_coda = wd.plan_materialization_for(workspace["process"])
    assert in_coda["status"] == "pending"
    assert "testo della fonte cambiato" in in_coda["reason"]


def test_resaving_the_very_same_text_costs_nothing(workspace):
    from backend import workspace_database as wd

    wd.ensure_project_source(
        project_id=workspace["project"],
        process_id=workspace["process"],
        name=TITLE,
        type="Intervista",
        content_hash="aaaa1111",
    )
    _drain_queue(workspace["process"])

    wd.ensure_project_source(
        project_id=workspace["project"],
        process_id=workspace["process"],
        name=TITLE,
        type="Intervista",
        content_hash="aaaa1111",
    )

    # Il consulente riformula e il turno viene ripetuto: l'evidenza e' la
    # stessa, e una ricostruzione del piano qui sarebbe spesa per niente.
    assert wd.plan_materialization_for(workspace["process"])["status"] == "done"


def test_a_caller_without_the_text_does_not_erase_the_digest(workspace):
    """Chi registra la fonte senza avere il testo - un perimetro, un documento
    caricato a mano - non sa dire cosa contiene. Cancellare l'impronta gia'
    scritta direbbe "non si sa piu'" di una fonte che non e' cambiata."""
    from backend import workspace_database as wd

    wd.ensure_project_source(
        project_id=workspace["project"],
        process_id=workspace["process"],
        name=TITLE,
        type="Intervista",
        content_hash="aaaa1111",
    )
    _drain_queue(workspace["process"])

    fonte, _ = wd.ensure_project_source(
        project_id=workspace["project"],
        process_id=workspace["process"],
        name=TITLE,
        type="Intervista",
    )

    assert fonte["content_hash"] == "aaaa1111"
    assert wd.plan_materialization_for(workspace["process"])["status"] == "done"


# --- i due posti che calcolano l'identita' ---------------------------------


def _save_interview(workspace: dict, raw: str) -> None:
    from backend.agents.scope_guard import bind_active_scope
    from backend.schemas.chat import ProcessChatScope
    from backend.toolsets.process_memory import manage_process_evidence

    with bind_active_scope(
        ProcessChatScope(
            type="process",
            project_id=workspace["project"],
            process_id=workspace["process"],
        )
    ):
        manage_process_evidence.invoke(
            {
                "operation": "save_interview",
                "project_id": workspace["project"],
                "process_id": workspace["process"],
                "title": TITLE,
                "raw_content": raw,
                "summary": "Come si chiudono le richieste urgenti.",
                "participants": ["Paolo Marchetti"],
            }
        )


def test_an_interview_saved_from_chat_declares_its_text(workspace):
    from backend import workspace_database as wd
    from backend.workspace_services.source_document import content_digest

    raw = (FIXTURES / INTERVIEW).read_text(encoding="utf-8")
    _save_interview(workspace, raw)

    fonte = next(
        item
        for item in wd.list_project_sources(workspace["project"])
        if item["name"] == TITLE
    )
    assert fonte["content_hash"] == content_digest(raw)


def test_the_sweep_and_the_evidence_ledger_agree_on_the_identity(workspace):
    """La trappola di questo cambiamento, e il motivo per cui l'impronta sta in
    una colonna invece di essere calcolata dal testo.

    Il registro dell'evidenza carica le trascrizioni; lo sweep dei piani
    indietro legge i soli record, perche' aprire ogni intervista di ogni
    progetto a ogni passata non si puo' fare. Se le due identita' divergessero,
    ogni processo risulterebbe sempre indietro e si ricostruirebbe il piano a
    ogni giro.
    """
    from backend import workspace_database as wd
    from backend.graphs.process.nodes import load_evidence_ledger, source_set_identity

    raw = (FIXTURES / INTERVIEW).read_text(encoding="utf-8")
    _save_interview(workspace, raw)

    dal_registro = load_evidence_ledger(workspace["project"], workspace["process"])[
        "source_set_id"
    ]
    dai_record = source_set_identity(
        [
            item
            for item in wd.list_project_sources(workspace["project"])
            if item.get("process_id") in {None, workspace["process"]}
        ]
    )

    assert dal_registro == dai_record


def test_a_plan_built_on_the_current_text_is_not_queued_again(workspace):
    from backend import workspace_database as wd
    from backend.graphs.process.nodes import load_evidence_ledger

    raw = (FIXTURES / INTERVIEW).read_text(encoding="utf-8")
    _save_interview(workspace, raw)
    ledger = load_evidence_ledger(workspace["project"], workspace["process"])
    wd.prepare_bpmn_review(
        bpmn_model_id=workspace["bpmn_model_id"],
        process_description="Le richieste urgenti passano dal capo reparto.",
        process_understanding={
            "title": "Richieste urgenti",
            "actors": [{"id": "capo-reparto", "label": "Capo reparto", "kind": "role"}],
            "steps": [
                {
                    "id": "apri-richiesta",
                    "label": "Apri la richiesta",
                    "actor_ids": ["capo-reparto"],
                }
            ],
        },
        evidence_source_set_id=ledger["source_set_id"],
    )
    _drain_queue(workspace["process"])

    queued = wd.enqueue_stale_plan_materializations(only_tenant_id=workspace["tenant"])

    assert all(row["process_id"] != workspace["process"] for row in queued)
    assert wd.plan_materialization_for(workspace["process"])["status"] == "done"


def test_a_plan_built_on_the_old_text_is_queued(workspace):
    """L'altra meta' del test precedente: l'identita' si muove davvero quando il
    testo cambia, in **tutti e due** i posti che la calcolano. Senza questo, un
    set che non si muove mai darebbe lo stesso verde."""
    from backend import workspace_database as wd
    from backend.graphs.process.nodes import load_evidence_ledger

    raw = (FIXTURES / INTERVIEW).read_text(encoding="utf-8")
    _save_interview(workspace, raw)
    ledger = load_evidence_ledger(workspace["project"], workspace["process"])
    wd.prepare_bpmn_review(
        bpmn_model_id=workspace["bpmn_model_id"],
        process_description="Le richieste urgenti passano dal capo reparto.",
        process_understanding={
            "title": "Richieste urgenti",
            "actors": [{"id": "capo-reparto", "label": "Capo reparto", "kind": "role"}],
            "steps": [
                {
                    "id": "apri-richiesta",
                    "label": "Apri la richiesta",
                    "actor_ids": ["capo-reparto"],
                }
            ],
        },
        evidence_source_set_id=ledger["source_set_id"],
    )

    # La stessa intervista, corretta: stesso titolo, testo diverso.
    _save_interview(workspace, raw + "\n\nNota: le urgenze le approva la direzione.")
    _drain_queue(workspace["process"])

    queued = wd.enqueue_stale_plan_materializations(only_tenant_id=workspace["tenant"])

    assert any(row["process_id"] == workspace["process"] for row in queued)
