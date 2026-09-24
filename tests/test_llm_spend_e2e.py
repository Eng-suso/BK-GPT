"""P1.5 — e2e: la spesa di un'ingestione arriva al registro, passando dal codice vero.

Gli altri test del gateway sostituiscono pezzi interni per isolare un
comportamento. Qui no: si accoda un'evidenza come fa il tool dell'agente, la
processa `ingest_worker`, e il percorso che ne segue - operazione aperta dal
worker, `canonical.write_evidence`, `memory/embeddings`, `llm.embed`, la
scrittura del registro su Postgres - e' quello di produzione, riga per riga.

**L'unica cosa finta e' il confine di rete**, cioe' il client dell'SDK. Un test
che finge anche `llm.embed` dimostrerebbe soltanto che il test sa chiamare il
proprio doppio: la domanda a cui questo file risponde e' un'altra, ed e' quella
da cui e' nato il gateway — «dove sono andati i soldi ieri» e' una query?

Skip senza le DSN canonical + NEO4J_PASSWORD, come gli altri test di ingestione.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select, text

from backend.settings import settings

_NEEDED = (
    settings.canonical_migrator_url,
    settings.canonical_database_url,
    settings.canonical_worker_url,
    settings.neo4j_password,
)
if not all(_NEEDED):
    pytest.skip("servono le DSN canonical + NEO4J_PASSWORD", allow_module_level=True)

from backend.db import canonical_session  # noqa: E402
from backend.llm import LlmTask, Outcome  # noqa: E402
from backend.memory import embeddings  # noqa: E402
from backend.memory.knowledge_graph import canonical, neo4j_store  # noqa: E402
from backend.workers import ingest_worker  # noqa: E402
from backend.workspace_storage import WorkspaceLlmUsage, workspace_connection  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)

_PROMPT_TOKENS = 137


class _FakeEmbeddingResponse:
    """La forma che l'SDK OpenAI restituisce davvero: vettori in `data`, token in
    `usage.prompt_tokens`."""

    def __init__(self, n: int, dimensions: int):
        self.data = [type("_Item", (), {"embedding": [0.01] * dimensions})() for _ in range(n)]
        self.usage = type(
            "_Usage", (), {"prompt_tokens": _PROMPT_TOKENS, "total_tokens": _PROMPT_TOKENS}
        )()


@pytest.fixture()
def rete_finta(monkeypatch):
    """Sostituisce i due client del fornitore, e niente altro.

    Il client della chat non risponde: solleva. Nell'ingestione di entita' nuove
    il confronto deterministico chiude tutto da solo, quindi un giudizio del
    modello qui sarebbe spesa che non ci aspettiamo - e un test che la lascia
    passare in silenzio non la vedrebbe mai.
    """
    chiamate: dict = {"embed": 0, "testi": []}

    class _FakeEmbeddings:
        def create(self, *, model, input, dimensions):  # noqa: A002 - firma dell'SDK
            chiamate["embed"] += 1
            chiamate["testi"].extend(input)
            chiamate["model"] = model
            return _FakeEmbeddingResponse(len(input), dimensions)

    class _FakeEmbeddingClient:
        embeddings = _FakeEmbeddings()

    def _niente_chat(*_args, **_kwargs):
        raise AssertionError("l'ingestione non dovrebbe chiedere nessun giudizio di chat")

    monkeypatch.setattr(settings, "openai_api_key", "sk-test-e2e")
    monkeypatch.setattr("backend.llm.gateway._embedding_client", lambda: _FakeEmbeddingClient())
    monkeypatch.setattr("backend.llm.gateway._client", _niente_chat)
    return chiamate


@pytest.fixture()
def scope(monkeypatch):
    """Un consulente, un cliente, un progetto e un processo veri, poi ripuliti."""
    c, cl, pj, pr = (uuid.uuid4() for _ in range(4))
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("INSERT INTO consultant (id, email, display_name) VALUES (:i,:e,'spend')"),
            {"i": c, "e": f"{c}@t.local"},
        )
        conn.execute(
            text("SELECT set_config('app.current_consultant_id', :v, true)"), {"v": str(c)}
        )
        conn.execute(
            text("SELECT set_config('app.current_client_id', '', true)"),
        )
        conn.execute(
            text("INSERT INTO client (id, consultant_id, name) VALUES (:i,:c,'AcmeSpend')"),
            {"i": cl, "c": c},
        )
        conn.execute(
            text("INSERT INTO project (id, client_id, consultant_id, name) VALUES (:i,:cl,:c,'P')"),
            {"i": pj, "cl": cl, "c": c},
        )
        conn.execute(
            text(
                "INSERT INTO process (id, project_id, client_id, consultant_id, name) "
                "VALUES (:i,:p,:cl,:c,'Order to Cash')"
            ),
            {"i": pr, "p": pj, "cl": cl, "c": c},
        )
    monkeypatch.setattr(settings, "default_consultant_id", str(c))
    yield {"consultant": str(c), "client": str(cl), "project": str(pj), "process": str(pr)}
    with MIGRATOR.begin() as conn:
        conn.execute(text("DELETE FROM consultant WHERE id = :i"), {"i": c})
    neo4j_store.purge_client(str(cl))


def _righe_del_registro(project_id: str) -> list[WorkspaceLlmUsage]:
    """Le righe di consumo di un progetto.

    Il filtro e' il progetto e non il tenant perche' il tenant del registro e'
    quello **workspace** (`local` finche' il prodotto e' mono-consulente), non
    l'id del consulente canonical: sarebbe lo stesso valore per tutte le righe
    di tutti i test.
    """
    with workspace_connection() as session:
        return list(
            session.scalars(
                select(WorkspaceLlmUsage).where(WorkspaceLlmUsage.project_id == project_id)
            )
        )


@pytest.fixture()
def ws() -> dict[str, str]:
    """Gli id **workspace** del turno, nuovi a ogni test.

    Il registro dei consumi e' un tavolo condiviso e le righe restano: due test
    che riusassero lo stesso progetto si leggerebbero i consumi a vicenda, e il
    primo a rompersi sarebbe quello che conta le operazioni.
    """
    suffisso = uuid.uuid4().hex[:8]
    return {"project": f"ws-project-{suffisso}", "process": f"ws-process-{suffisso}"}


def test_un_ingestione_lascia_la_sua_spesa_nel_registro(scope, rete_finta, ws):
    """Il percorso intero: dal job in coda alla riga di consumo."""
    job_id = canonical.enqueue_evidence(
        workspace_project_id=ws["project"],
        workspace_process_id=ws["process"],
        consultant_id=scope["consultant"],
        client_id=scope["client"],
        project_id=scope["project"],
        process_id=scope["process"],
        process_name="Order to Cash",
        entities=["Ufficio crediti", "Direzione amministrativa"],
        relationships=[
            {
                "source": "Direzione amministrativa",
                "relation": "autorizza",
                "target": "Ufficio crediti",
                "confidence": 0.7,
            }
        ],
        source_title="Intervista Finance",
        source_text=(
            "Quando un cliente supera il limite di fido la pratica resta sospesa "
            "finche' la direzione amministrativa non autorizza il rilascio."
        ),
    )
    assert job_id

    assert ingest_worker.drain_once() == 1

    # Il lavoro e' andato a buon fine: senza questo, un registro vuoto avrebbe
    # due spiegazioni e il test non distinguerebbe fra loro.
    with canonical_session(scope["consultant"], scope["client"]) as s:
        stato = s.execute(
            text("SELECT status, result FROM kg_ingest_queue WHERE id = :i"), {"i": job_id}
        ).one()
    assert stato.status == "done"
    assert stato.result["chunks"] >= 1

    assert rete_finta["embed"] >= 1, "l'ingestione deve aver embeddato qualcosa"
    assert rete_finta["model"] == embeddings.EMBED_MODEL

    righe = _righe_del_registro(ws["project"])
    assert righe, "la spesa dell'ingestione non e' arrivata nel registro"

    embedding = [r for r in righe if r.task == LlmTask.EMBEDDING.value]
    assert embedding, f"nessuna riga di embedding: {[r.task for r in righe]}"

    riga = embedding[0]
    assert riga.operation_kind == "kg_ingestion"
    assert riga.operation_id
    assert riga.outcome == Outcome.OK
    assert riga.model == embeddings.EMBED_MODEL
    assert riga.input_tokens == _PROMPT_TOKENS
    # Un embedding non produce uscita: zero qui e' il valore giusto, non un dato
    # mancante.
    assert riga.output_tokens == 0

    # Tutte le chiamate di questo job appartengono alla stessa esecuzione: e'
    # cio' che rende «quanto e' costata questa ingestione» una somma e non una
    # ricostruzione a mano.
    assert len({r.operation_id for r in righe}) == 1


def test_la_spesa_dell_ingestione_usa_gli_id_workspace_come_la_chat(scope, rete_finta, ws):
    """Il registro ha **una** colonna `project_id`, e ci scrivono due mondi.

    La chat e la sintesi del piano spendono sugli id workspace; l'ingestione
    lavora su quelli canonical, che sono id diversi dello stesso progetto. Se
    ognuno scrivesse i suoi, «quanto costa questo progetto» dividerebbe in due
    lo stesso progetto e nessuno se ne accorgerebbe guardando la colonna.
    """
    canonical.enqueue_evidence(
        workspace_project_id=ws["project"],
        workspace_process_id=ws["process"],
        consultant_id=scope["consultant"],
        client_id=scope["client"],
        project_id=scope["project"],
        process_id=scope["process"],
        process_name="Order to Cash",
        entities=["Tesoreria"],
        source_title="Nota",
        source_text="La tesoreria verifica gli incassi ogni mattina.",
    )

    assert ingest_worker.drain_once() == 1

    righe = _righe_del_registro(ws["project"])
    assert righe
    assert righe[0].project_id == ws["project"]
    assert righe[0].process_id == ws["process"]
    # e non gli id canonical, che restano nel pacchetto di evidenza
    assert not _righe_del_registro(scope["project"])


def test_un_job_accodato_prima_ricade_sugli_id_canonical(scope, rete_finta, ws):
    """Compatibilita': i job gia' in coda non hanno il campo nuovo.

    Meglio una riga con l'id canonical che una riga senza progetto: il primo si
    riconosce e si converte, la seconda e' spesa che non si sa dove mettere.
    """
    canonical.enqueue_evidence(
        consultant_id=scope["consultant"],
        client_id=scope["client"],
        project_id=scope["project"],
        process_id=scope["process"],
        process_name="Order to Cash",
        entities=["Tesoreria"],
        source_title="Nota",
        source_text="La tesoreria verifica gli incassi ogni mattina.",
    )

    assert ingest_worker.drain_once() == 1

    righe = _righe_del_registro(scope["project"])
    assert righe
    assert righe[0].process_id == scope["process"]


# --------------------------------------------------------------------------- #
# il turno di chat — il buco dichiarato in §① del doc di stato
# --------------------------------------------------------------------------- #


@pytest.fixture()
def chat_finta(monkeypatch):
    """Un client di chat che risponde con i token dove langchain li mette."""

    class _Risposta:
        content = "ok"
        usage_metadata = {
            "input_tokens": 90,
            "output_tokens": 10,
            "total_tokens": 100,
            "input_token_details": {"cache_read": 0},
            "output_token_details": {"reasoning": 0},
        }

    class _FakeChat:
        def bind(self, **_kwargs):
            return self

        def with_structured_output(self, _schema, include_raw=False):
            return self

        def stream(self, *_args, **_kwargs):
            yield _Risposta()

    monkeypatch.setattr(settings, "openai_api_key", "sk-test-e2e")
    monkeypatch.setattr("backend.llm.gateway._client", lambda *_a, **_k: _FakeChat())


def test_il_turno_di_chat_attribuisce_la_spesa_dei_suoi_strumenti(monkeypatch, chat_finta, ws):
    """Il percorso che t.1 ha cablato, provato dall'esterno.

    Le parti erano coperte una per una (`new_operation`, `adopt`, l'eredita' nei
    thread), il percorso intero no - ed e' il percorso che conta, perche'
    l'operazione della chat nasce nella richiesta e viene adottata in un
    **thread** che il generatore non controlla. Qui si chiama la funzione vera e
    si guarda il registro: se l'aggancio si rompe, la riga non c'e'.
    """
    from backend.llm import LlmTask
    from backend.llm import run as llm_run
    from backend.schemas.chat import ProcessChatScope
    from backend.services import agent_runtime

    visto: dict = {}

    class _AgenteFinto:
        def stream(self, *_args, **_kwargs):
            # Questo gira nel thread dell'agente: e' esattamente il punto in cui
            # un ContextVar non ereditato farebbe sparire l'operazione.
            visto["risposta"] = llm_run(task=LlmTask.RETRIEVAL_RERANK, messages=[])
            return iter(())

    monkeypatch.setattr(agent_runtime, "get_agent", lambda *_a, **_k: _AgenteFinto())

    eventi = list(
        agent_runtime.stream_agent_events(
            thread_id=f"t-spend-{uuid.uuid4().hex[:8]}",
            model_name=None,
            messages=[{"role": "user", "content": "ciao"}],
            scope=ProcessChatScope(
                type="process", project_id=ws["project"], process_id=ws["process"]
            ),
        )
    )

    assert "error" not in [e.type for e in eventi]
    assert visto.get("risposta") is not None, "il gateway non e' stato chiamato"

    righe = [
        r
        for r in _righe_del_registro(ws["project"])
        if r.operation_kind == "chat_turn" and r.task == LlmTask.RETRIEVAL_RERANK.value
    ]
    assert righe, "la spesa del turno di chat non e' arrivata nel registro"
    assert righe[0].process_id == ws["process"]
    assert righe[0].input_tokens == 90


def test_un_turno_stremato_lascia_due_righe_turno_e_instradamento(monkeypatch, ws):
    """t.6 — la chat non passa da `run()`, ma finisce lo stesso nel registro.

    Il modello della chat lo esegue LangGraph e quello che esce e' uno stream
    di pezzi: i token arrivano sull'ultimo pezzo (`stream_usage=True`) e il
    runtime li somma gia' per mandarli al frontend. Qui si verifica che quella
    somma diventi righe di consumo, **divise per compito**: dentro un turno
    gira anche l'instradamento, che ha un profilo suo. Sommarli darebbe un
    totale giusto e due medie sbagliate.
    """
    from backend.agent import CONTEXT_ROUTER_NODE
    from backend.llm import LlmTask
    from backend.schemas.chat import ProcessChatScope
    from backend.services import agent_runtime

    class _Pezzo:
        type = "AIMessageChunk"

        def __init__(self, testo: str, input_tokens: int, output_tokens: int):
            self.content = testo
            self.usage_metadata = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            }

    class _AgenteFinto:
        def stream(self, *_args, **_kwargs):
            # Prima instrada, poi risponde: due nodi, due compiti.
            yield (_Pezzo("", 40, 5), {"langgraph_node": CONTEXT_ROUTER_NODE})
            yield (_Pezzo("ecco", 300, 120), {"langgraph_node": "consulting_subgraph"})

    monkeypatch.setattr(agent_runtime, "get_agent", lambda *_a, **_k: _AgenteFinto())

    eventi = list(
        agent_runtime.stream_agent_events(
            thread_id=f"t-stream-{uuid.uuid4().hex[:8]}",
            model_name=None,
            messages=[{"role": "user", "content": "ciao"}],
            scope=ProcessChatScope(
                type="process", project_id=ws["project"], process_id=ws["process"]
            ),
        )
    )

    assert "error" not in [e.type for e in eventi]

    righe = {r.task: r for r in _righe_del_registro(ws["project"])}

    assert LlmTask.CHAT_TURN.value in righe, f"nessuna riga per il turno: {list(righe)}"
    assert LlmTask.CONTEXT_ROUTING.value in righe, "l'instradamento e' sparito dentro il turno"

    turno = righe[LlmTask.CHAT_TURN.value]
    instradamento = righe[LlmTask.CONTEXT_ROUTING.value]

    assert (turno.input_tokens, turno.output_tokens) == (300, 120)
    assert (instradamento.input_tokens, instradamento.output_tokens) == (40, 5)
    assert turno.operation_kind == instradamento.operation_kind == "chat_turn"
    # Stessa esecuzione: "quanto e' costato questo turno" resta una somma.
    assert turno.operation_id == instradamento.operation_id


def test_un_turno_che_fallisce_a_meta_ha_speso_lo_stesso(monkeypatch, ws):
    """La spesa che conta di piu' e' quella senza un risultato in mano.

    Registrare solo sul percorso felice avrebbe lasciato fuori proprio i turni
    andati male: quelli che il consulente rifa, pagandoli due volte.
    """
    from backend.llm import LlmTask
    from backend.schemas.chat import ProcessChatScope
    from backend.services import agent_runtime

    class _Pezzo:
        type = "AIMessageChunk"
        content = "inizio"
        usage_metadata = {"input_tokens": 210, "output_tokens": 15, "total_tokens": 225}

    class _AgenteCheSiRompe:
        def stream(self, *_args, **_kwargs):
            yield (_Pezzo(), {"langgraph_node": "consulting_subgraph"})
            raise RuntimeError("il grafo si e' rotto a meta'")

    monkeypatch.setattr(agent_runtime, "get_agent", lambda *_a, **_k: _AgenteCheSiRompe())

    eventi = list(
        agent_runtime.stream_agent_events(
            thread_id=f"t-rotto-{uuid.uuid4().hex[:8]}",
            model_name=None,
            messages=[{"role": "user", "content": "ciao"}],
            scope=ProcessChatScope(
                type="process", project_id=ws["project"], process_id=ws["process"]
            ),
        )
    )

    assert "error" in [e.type for e in eventi], "il turno doveva fallire"

    righe = _righe_del_registro(ws["project"])
    assert righe, "un turno fallito a meta' ha comunque pagato i token consumati"
    assert righe[0].task == LlmTask.CHAT_TURN.value
    assert righe[0].input_tokens == 210


def test_il_registro_dice_il_modello_che_ha_girato(monkeypatch, ws):
    """La chat e' l'unico compito in cui il modello lo sceglie il consulente.

    Il profilo ne dichiara uno di default, ma scriverlo nel registro quando ne
    ha girato un altro produce un costo stimato da un listino che non c'entra.
    Oggi `ALLOWED_MODELS` ne contiene uno solo, quindi il difetto non si vede in
    produzione: si vedrebbe il giorno che se ne aggiunge un secondo, ed e' un
    giorno qualunque.
    """
    from backend.schemas.chat import ProcessChatScope
    from backend.services import agent_runtime
    from backend.settings import ALLOWED_MODELS, settings

    altro_modello = "gpt-5.6-luna-mini"
    monkeypatch.setattr(
        "backend.agent.ALLOWED_MODELS", {*ALLOWED_MODELS, altro_modello}, raising=False
    )

    class _Pezzo:
        type = "AIMessageChunk"
        content = "ecco"
        usage_metadata = {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15}

    class _AgenteFinto:
        def stream(self, *_args, **_kwargs):
            yield (_Pezzo(), {"langgraph_node": "consulting_subgraph"})

    monkeypatch.setattr(agent_runtime, "get_agent", lambda *_a, **_k: _AgenteFinto())

    list(
        agent_runtime.stream_agent_events(
            thread_id=f"t-modello-{uuid.uuid4().hex[:8]}",
            model_name=altro_modello,
            messages=[{"role": "user", "content": "ciao"}],
            scope=ProcessChatScope(
                type="process", project_id=ws["project"], process_id=ws["process"]
            ),
        )
    )

    righe = _righe_del_registro(ws["project"])
    assert righe
    assert righe[0].model == altro_modello, (
        "il registro ha scritto il modello del profilo invece di quello che ha girato"
    )
    assert righe[0].model != settings.openai_model
