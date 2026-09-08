"""PROCESS-V2-08 — la Process Chat vede solo l'evidenza del proprio processo.

Nel test E2E V2 il processo "Gestione acquisto materiali indiretti e servizi"
ha risposto citando fatti che nessuno degli intervistati aveva detto: una soglia
di 5.000 euro, un "fornitore abituale", un guasto tecnico, una data 15/05/2024 e
perfino una Laura Conti con il ruolo di Facility Manager. Quei fatti esistono -
ma appartengono a un altro processo dello stesso cliente.

Il percorso di scrittura del knowledge graph e' sempre stato scoped per
processo (`canonical.write_*` stampa `project_id` e `process_id` su ogni riga).
Il percorso di lettura no: `gateway.graph_retrieve` filtrava solo per
`client_id`, quindi ogni chunk e ogni entita' del cliente entrava nel contesto
di qualunque processo di quel cliente.

Qui si attraversano i path veri: workspace Postgres, tool di salvataggio
evidenza dell'agente, mirror canonical, coda di ingestion, proiezione Neo4j,
gateway di lettura. Niente e' mockato sotto il tool: se l'isolamento non regge
in produzione, non regge nemmeno qui.

Servono le DSN canonical + workspace + NEO4J_PASSWORD (`cd ops && docker
compose up -d`).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings

_NEEDED = (
    settings.workspace_database_url,
    settings.canonical_migrator_url,
    settings.canonical_database_url,
    settings.canonical_worker_url,
    settings.neo4j_password,
)
if not all(_NEEDED):
    pytest.skip(
        "servono WORKSPACE_DATABASE_URL + le DSN canonical + NEO4J_PASSWORD",
        allow_module_level=True,
    )

from backend.memory.knowledge_graph import neo4j_store  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)
FIXTURES = Path(__file__).parent / "fixtures" / "interviews"


# I fatti che appartengono SOLO al processo B. Se uno di questi compare in una
# risposta del processo A, l'evidenza e' contaminata: nessuno degli intervistati
# di A li ha mai pronunciati.
SENTINEL_FACTS = (
    "5.000",
    "fornitore abituale",
    "guasto tecnico",
    "facility manager",
    "15/05/2024",
    "zentrix",
    "modulo standard",
)


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# Le interviste del processo A: tre persone, ruoli diversi, una contraddizione
# controllata (Paolo dice che l'amministrativo "viene sistemato dopo" senza dire
# da chi; Francesca dice che il raccordo lo fa lei).
INTERVIEWS_A = (
    {
        "title": "Intervista Laura Conti - Ufficio Tecnico",
        "file": "a1_laura_conti_ufficio_tecnico.md",
        "participants": ["Laura Conti"],
        "entities": ["Laura Conti", "Ufficio Tecnico", "Richiesta di acquisto"],
        "claims": [
            {
                "claim": "Laura Conti riferisce che la richiesta arriva per mail, messaggio o a voce.",
                "process_area": "activity",
                "source_name": "Intervista Laura Conti - Ufficio Tecnico",
                "confidence": "high",
                "status": "partial",
            },
            {
                "claim": "Laura Conti dichiara di non sapere chi approvi la spesa.",
                "process_area": "control",
                "source_name": "Intervista Laura Conti - Ufficio Tecnico",
                "confidence": "high",
                "status": "partial",
            },
        ],
    },
    {
        "title": "Intervista Paolo Marchetti - Manutenzione",
        "file": "a2_paolo_marchetti_manutenzione.md",
        "participants": ["Paolo Marchetti"],
        "entities": ["Paolo Marchetti", "Manutenzione", "Richiesta urgente"],
        "claims": [
            {
                "claim": "Paolo Marchetti riferisce che nelle urgenze chiama direttamente il fornitore.",
                "process_area": "exception",
                "source_name": "Intervista Paolo Marchetti - Manutenzione",
                "confidence": "high",
                "status": "partial",
            },
        ],
    },
    {
        "title": "Intervista Francesca Neri - Acquisti",
        "file": "a3_francesca_neri_acquisti.md",
        "participants": ["Francesca Neri"],
        "entities": ["Francesca Neri", "Ufficio Acquisti", "Autorizzazione di spesa"],
        "claims": [
            {
                "claim": "Francesca Neri riferisce che oltre una certa cifra serve una autorizzazione.",
                "process_area": "control",
                "source_name": "Intervista Francesca Neri - Acquisti",
                "confidence": "medium",
                "status": "partial",
            },
        ],
    },
)

# Le interviste del processo B: stesso cliente, altro processo, e dentro ci sono
# i SENTINEL. Fra queste c'e' una seconda Laura Conti, con un ruolo diverso: e'
# la collisione di identita' che nel test E2E ha fatto comparire un Facility
# Manager dentro il processo acquisti.
INTERVIEWS_B = (
    {
        "title": "Intervista Laura Conti - Facility",
        "file": "b1_laura_conti_facility.md",
        "participants": ["Laura Conti"],
        "entities": ["Laura Conti", "Facility Manager", "Zentrix Impianti", "Modulo standard"],
        "claims": [
            {
                "claim": "Laura Conti, Facility Manager, riferisce la soglia di 5.000 euro con due offerte.",
                "process_area": "control",
                "source_name": "Intervista Laura Conti - Facility",
                "confidence": "high",
                "status": "partial",
            },
        ],
    },
    {
        "title": "Intervista Marco Gallo - Tecnico di sede",
        "file": "b2_marco_gallo_tecnico_sede.md",
        "participants": ["Marco Gallo"],
        "entities": ["Marco Gallo", "Zentrix Impianti", "Registro segnalazioni"],
        "claims": [
            {
                "claim": "Marco Gallo riferisce che il fornitore abituale interviene in giornata.",
                "process_area": "handoff",
                "source_name": "Intervista Marco Gallo - Tecnico di sede",
                "confidence": "medium",
                "status": "partial",
            },
        ],
    },
    {
        "title": "Intervista Chiara Verdi - Direzione",
        "file": "b3_chiara_verdi_direzione.md",
        "participants": ["Chiara Verdi"],
        "entities": ["Chiara Verdi", "Direzione", "Soglia di 5.000 euro"],
        "claims": [
            {
                "claim": "Chiara Verdi riferisce che sopra la soglia di 5.000 euro decide la Direzione.",
                "process_area": "decision",
                "source_name": "Intervista Chiara Verdi - Direzione",
                "confidence": "high",
                "status": "partial",
            },
        ],
    },
)


def _save_interviews(project_id: str, process_id: str, interviews) -> None:
    """Salva le interviste passando dal tool vero dell'agente."""
    from backend.toolsets.process_memory import manage_process_evidence

    for interview in interviews:
        raw = interview.get("raw_content") or _read(interview["file"])
        manage_process_evidence.invoke(
            {
                "operation": "save_interview",
                "project_id": project_id,
                "process_id": process_id,
                "title": interview["title"],
                "raw_content": raw,
                "summary": interview["title"],
                "participants": interview["participants"],
                "entities": interview["entities"],
                "claims": interview["claims"],
            }
        )


def _drain() -> None:
    """Ingestion asincrona + proiezione Neo4j, come in produzione."""
    from backend.workers.graph_worker import drain_once as drain_graph
    from backend.workers.ingest_worker import drain_once as drain_ingest

    for _ in range(6):
        drain_ingest(limit=50)
        drain_graph(limit=200)


# Un terzo processo, dentro lo STESSO progetto di A: il confine da verificare
# qui non e' il progetto ma il processo. Il suo fatto riconoscibile non deve
# comparire nella chat di A piu' di quanto ci compaiano quelli di B.
INTERVIEW_A2 = {
    "title": "Intervista Giulia Ferri - Trasferte",
    "participants": ["Giulia Ferri"],
    "entities": ["Giulia Ferri", "Nota spese"],
    "raw_content": (
        "La nota spese si compila sul portale trasferte entro il venerdi'. "
        "Chi rientra tardi usa il codice rimborso KM-77, che e' l'unico caso in "
        "cui l'anticipo di cassa viene restituito in busta paga. Il portale "
        "trasferte non parla con il gestionale, quindi i dati si ribattono."
    ),
    "claims": [
        {
            "claim": "Giulia Ferri riferisce che il codice rimborso KM-77 copre l'anticipo di cassa.",
            "process_area": "data",
            "source_name": "Intervista Giulia Ferri - Trasferte",
            "confidence": "high",
            "status": "partial",
        },
    ],
}

# Fatti riconoscibili del processo vicino, dentro lo stesso progetto.
SENTINEL_FACTS_SAME_PROJECT = ("km-77", "portale trasferte", "nota spese")


@pytest.fixture()
def workspace():
    """Un cliente, due progetti, tre processi.

    A e' il processo sotto esame. B vive in un altro progetto dello STESSO
    cliente - il confine che il gateway non stava rispettando. A2 vive nello
    STESSO progetto di A: li' il confine e' il processo, non l'incarico.
    """
    from backend import workspace_database as wd
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
    suffix = uuid.uuid4().hex[:8]
    client = wd.create_client(name=f"Contoso Manifattura {suffix}")
    project_a = wd.create_project(client_id=client["id"], name=f"Acquisti indiretti {suffix}")
    process_a = wd.create_process(
        project_id=project_a["id"], name="Gestione acquisto materiali indiretti e servizi"
    )
    process_a2 = wd.create_process(
        project_id=project_a["id"], name="Gestione note spese e trasferte"
    )
    project_b = wd.create_project(client_id=client["id"], name=f"Facility sede {suffix}")
    process_b = wd.create_process(
        project_id=project_b["id"], name="Gestione segnalazioni tecniche e guasti impianti sede"
    )

    scope = {
        "client_name": client["name"],
        "project_a": project_a["id"],
        "process_a": process_a["id"],
        "process_a2": process_a2["id"],
        "project_b": project_b["id"],
        "process_b": process_b["id"],
    }
    try:
        yield scope
    finally:
        canonical_client = _canonical_client_id(project_a["id"])
        _forget_episodes([project_a["id"], project_b["id"]])
        reset_current_tenant_id(token)
        if canonical_client:
            with MIGRATOR.begin() as conn:
                conn.execute(text("DELETE FROM client WHERE id = :i"), {"i": canonical_client})
            neo4j_store.purge_client(canonical_client)


def _canonical_client_id(workspace_project_id: str) -> str | None:
    from backend.memory import scope as canonical_scope

    return canonical_scope.resolve_client_id(workspace_project_id)


def _forget_episodes(project_ids: list[str]) -> None:
    from backend.memory.episodic import episodic_store

    with episodic_store.episodic_connection() as session:
        session.execute(
            text("DELETE FROM episodes WHERE project = ANY(:p)"),
            {"p": project_ids},
        )


def _bind_process_chat(project_id: str, process_id: str):
    """Il vincolo di scope che il backend mette attorno a un turno di chat."""
    from backend.agents.scope_guard import bind_active_scope
    from backend.schemas.chat import ProcessChatScope

    return bind_active_scope(
        ProcessChatScope(type="process", project_id=project_id, process_id=process_id)
    )


def _tool_payload(result: str) -> dict:
    return json.loads(result.split("\n", 1)[1])["payload"]


def _graph_context(project_id: str, process_id: str, query: str, entities: list[str]) -> dict:
    from backend.toolsets.process_memory import retrieve_process_graph_context

    with _bind_process_chat(project_id, process_id):
        result = retrieve_process_graph_context.invoke(
            {
                "project_id": project_id,
                "process_id": process_id,
                "query": query,
                "relation_focus": "evidence-lineage",
                "reason": "Sintesi delle interviste raccolte per questo processo.",
                "entities": entities,
                "limit": 20,
            }
        )
    return _tool_payload(result)["knowledge_graph"]


def _evidence_list(project_id: str, process_id: str) -> list[dict]:
    from backend.toolsets.process_memory import manage_process_evidence

    with _bind_process_chat(project_id, process_id):
        result = manage_process_evidence.invoke(
            {
                "operation": "list",
                "project_id": project_id,
                "process_id": process_id,
                "limit": 50,
            }
        )
    return _tool_payload(result)["evidence"]


def _retrieved_text(graph: dict) -> str:
    parts = [json.dumps(graph.get("matches") or [], ensure_ascii=False)]
    parts += [str(chunk.get("content") or "") for chunk in graph.get("chunks") or []]
    return " ".join(parts).lower()


def _contaminants(graph: dict) -> list[str]:
    haystack = _retrieved_text(graph)
    return [fact for fact in SENTINEL_FACTS if fact in haystack]


@pytest.fixture()
def two_processes_with_evidence(workspace):
    """Sei interviste salvate come le salva l'agente, poi ingerite e proiettate."""
    with _bind_process_chat(workspace["project_a"], workspace["process_a"]):
        _save_interviews(workspace["project_a"], workspace["process_a"], INTERVIEWS_A)
    with _bind_process_chat(workspace["project_a"], workspace["process_a2"]):
        _save_interviews(workspace["project_a"], workspace["process_a2"], [INTERVIEW_A2])
    with _bind_process_chat(workspace["project_b"], workspace["process_b"]):
        _save_interviews(workspace["project_b"], workspace["process_b"], INTERVIEWS_B)
    _drain()
    return workspace


# --- l'invariante ----------------------------------------------------------

def test_the_process_chat_only_sees_the_evidence_of_its_own_process(
    two_processes_with_evidence,
):
    """Nessun fatto del processo B entra nella sintesi del processo A."""
    ws = two_processes_with_evidence

    graph = _graph_context(
        ws["project_a"],
        ws["process_a"],
        "Cosa hanno raccontato gli intervistati su come nasce e viene autorizzata la richiesta?",
        ["Laura Conti", "Paolo Marchetti", "Francesca Neri"],
    )

    assert _contaminants(graph) == []


def test_the_evidence_of_the_process_is_actually_retrievable(two_processes_with_evidence):
    """L'isolamento non deve essere ottenuto restituendo il vuoto."""
    ws = two_processes_with_evidence

    graph = _graph_context(
        ws["project_a"],
        ws["process_a"],
        "Chi riceve la richiesta di acquisto e cosa succede dopo?",
        ["Laura Conti", "Ufficio Acquisti"],
    )
    retrieved = _retrieved_text(graph)

    assert graph["status"] == "ok"
    assert "acquisti" in retrieved


def test_the_evidence_list_returns_all_and_only_the_interviews_of_the_process(
    two_processes_with_evidence,
):
    """Tutte e tre le interviste di A, nessuna delle tre di B."""
    ws = two_processes_with_evidence

    titles = {item["title"] for item in _evidence_list(ws["project_a"], ws["process_a"])}

    assert titles == {interview["title"] for interview in INTERVIEWS_A}


def test_every_retrieved_interview_keeps_its_provenance(two_processes_with_evidence):
    """Un'affermazione senza fonte non e' evidenza: episode_id, source_id, processo."""
    ws = two_processes_with_evidence

    for item in _evidence_list(ws["project_a"], ws["process_a"]):
        assert item["episode_id"]
        assert item["source_id"]
        assert item["project"] == ws["project_a"]
        assert f"process:{ws['process_a']}" in json.loads(item["tags"])


def test_the_retrieved_chunks_declare_where_they_come_from(two_processes_with_evidence):
    """Ogni chunk di contesto porta la sua provenance, verificabile a valle."""
    ws = two_processes_with_evidence

    graph = _graph_context(
        ws["project_a"],
        ws["process_a"],
        "Come arriva la richiesta di acquisto?",
        ["Richiesta di acquisto"],
    )

    assert graph["chunks"]
    for chunk in graph["chunks"]:
        assert chunk["source_id"]
        assert chunk["source_title"] in {i["title"] for i in INTERVIEWS_A}


def test_two_people_with_the_same_name_in_two_processes_do_not_become_one(
    two_processes_with_evidence,
):
    """La Laura Conti di A non eredita il ruolo della Laura Conti di B."""
    ws = two_processes_with_evidence

    graph = _graph_context(
        ws["project_a"],
        ws["process_a"],
        "Che ruolo ha Laura Conti in questo processo?",
        ["Laura Conti"],
    )
    retrieved = _retrieved_text(graph)

    assert "facility manager" not in retrieved


def test_the_isolation_holds_across_a_new_chat_and_a_restart(two_processes_with_evidence):
    """Chat nuova, pool ricreato: l'isolamento non dipende dallo stato in memoria."""
    ws = two_processes_with_evidence
    query = "Riassumi cosa e' emerso dalle interviste e cosa resta incerto."
    entities = ["Laura Conti", "Paolo Marchetti", "Francesca Neri"]

    for _ in range(3):
        assert _contaminants(_graph_context(ws["project_a"], ws["process_a"], query, entities)) == []

    _restart_connections()

    assert _contaminants(_graph_context(ws["project_a"], ws["process_a"], query, entities)) == []
    assert {item["title"] for item in _evidence_list(ws["project_a"], ws["process_a"])} == {
        interview["title"] for interview in INTERVIEWS_A
    }


def test_a_sibling_process_of_the_same_project_stays_out(two_processes_with_evidence):
    """Il confine e' il processo, non solo l'incarico.

    A e A2 sono due processi dello stesso progetto: cio' che ha raccontato
    Giulia Ferri non e' contesto della discovery sugli acquisti.
    """
    ws = two_processes_with_evidence

    # Domanda legittima nel processo acquisti - Laura si lamenta proprio del
    # lavoro manuale - e che pero' pesca lessicalmente nel testo di A2.
    graph = _graph_context(
        ws["project_a"],
        ws["process_a"],
        "Quali dati si ribattono a mano fra i sistemi?",
        ["Nota spese", "Giulia Ferri", "Richiesta di acquisto"],
    )
    retrieved = _retrieved_text(graph)

    assert [fact for fact in SENTINEL_FACTS_SAME_PROJECT if fact in retrieved] == []


def test_the_sibling_process_sees_its_own_evidence(two_processes_with_evidence):
    """Lo stesso confine, letto dall'altro lato."""
    ws = two_processes_with_evidence

    graph = _graph_context(
        ws["project_a"],
        ws["process_a2"],
        "Quale codice si usa per il rimborso dell'anticipo di cassa?",
        ["Nota spese", "Giulia Ferri"],
    )

    assert "km-77" in _retrieved_text(graph)


def test_the_evidence_list_does_not_mix_two_processes_of_one_project(
    two_processes_with_evidence,
):
    ws = two_processes_with_evidence

    titles = {item["title"] for item in _evidence_list(ws["project_a"], ws["process_a"])}

    assert INTERVIEW_A2["title"] not in titles


# --- l'altra destinazione dell'evidenza: il pannello Fonti ----------------

def test_the_evidence_saved_in_a_chat_registers_its_source_on_that_process(
    two_processes_with_evidence,
):
    """Ogni intervista salvata compare fra le fonti, legata al proprio processo."""
    from backend import workspace_database as wd

    ws = two_processes_with_evidence
    sources = wd.list_project_sources(ws["project_a"])
    by_name = {source["name"]: source for source in sources}

    for interview in INTERVIEWS_A:
        assert by_name[interview["title"]]["process_id"] == ws["process_a"]
    # Il processo vicino ha la sua, sullo stesso progetto ma non sul processo A.
    assert by_name[INTERVIEW_A2["title"]]["process_id"] == ws["process_a2"]


def test_a_source_cannot_be_registered_on_a_process_outside_the_chat(
    two_processes_with_evidence,
):
    """L'evidenza e la sua fonte hanno lo stesso confine.

    Un turno aperto sul processo A non puo' far comparire una fonte nel
    pannello di un altro processo: isolare la memoria e lasciare aperta la
    registrazione della fonte sposterebbe il problema, non lo risolverebbe.
    """
    from backend import workspace_database as wd
    from backend.agents.scope_guard import ScopeViolation
    from backend.graphs.process.tools import save_process_evidence
    from backend.toolsets.process_memory import manage_process_evidence

    ws = two_processes_with_evidence
    before = {source["id"] for source in wd.list_project_sources(ws["project_b"])}

    with _bind_process_chat(ws["project_a"], ws["process_a"]):
        with pytest.raises(ScopeViolation):
            save_process_evidence.invoke(
                {
                    "process_id": ws["process_b"],
                    "name": "Fonte dirottata",
                    "evidence_type": "interview_notes",
                    "summary": "Non deve comparire nel pannello del processo B.",
                }
            )
        with pytest.raises(ScopeViolation):
            manage_process_evidence.invoke(
                {
                    "operation": "save_interview",
                    "project_id": ws["project_b"],
                    "process_id": ws["process_b"],
                    "title": "Intervista dirottata",
                    "raw_content": "Testo che appartiene a un altro incarico.",
                }
            )

    assert {source["id"] for source in wd.list_project_sources(ws["project_b"])} == before


def test_a_source_cannot_be_registered_on_a_sibling_process_either(
    two_processes_with_evidence,
):
    """Anche dentro lo stesso progetto: il confine e' il processo."""
    from backend import workspace_database as wd
    from backend.agents.scope_guard import ScopeViolation
    from backend.graphs.process.tools import save_process_evidence

    ws = two_processes_with_evidence
    before = {source["id"] for source in wd.list_project_sources(ws["project_a"])}

    with _bind_process_chat(ws["project_a"], ws["process_a"]):
        with pytest.raises(ScopeViolation):
            save_process_evidence.invoke(
                {
                    "process_id": ws["process_a2"],
                    "name": "Fonte sul processo vicino",
                    "evidence_type": "document",
                    "summary": "Stesso progetto, processo sbagliato.",
                }
            )

    assert {source["id"] for source in wd.list_project_sources(ws["project_a"])} == before


def test_the_other_process_still_sees_its_own_evidence(two_processes_with_evidence):
    """Isolare A non deve svuotare B: il confine e' bidirezionale, non un blocco."""
    ws = two_processes_with_evidence

    graph = _graph_context(
        ws["project_b"],
        ws["process_b"],
        "Qual e' la soglia oltre la quale serve l'approvazione della Direzione?",
        ["Laura Conti", "Direzione"],
    )

    assert "5.000" in _retrieved_text(graph)


def _restart_connections() -> None:
    """Butta via i pool e il driver: il giro successivo riparte a freddo."""
    from backend.db.session import canonical_engine
    from backend.local_store import local_engine
    from backend.memory.knowledge_graph import neo4j_store as store

    local_engine().dispose()
    canonical_engine().dispose()
    driver = store.get_driver()
    if driver is not None:
        driver.close()
    store.get_driver.cache_clear()
