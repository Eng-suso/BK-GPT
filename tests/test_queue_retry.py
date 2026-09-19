"""Cosa fa una coda quando il provider dice "non ora" e quando il dato e' storto.

Due esiti che prima erano lo stesso `attempts + 1`, e che invece hanno bisogno
di trattamenti opposti:

  429 del provider   non e' un difetto del job. Non deve consumare il budget dei
                     tentativi, e la riga deve tornare dopo l'attesa dichiarata,
                     non due secondi dopo. Il fatto va proiettato lo stesso.
  payload non valido non passera' mai. Va fermato all'accodamento; se e' gia' in
                     coda, va in dead-letter alla prima passata invece di
                     occupare cinque giri per arrivarci.

Nessun DB e nessuna rete: qui si verificano la classificazione e la forma degli
UPDATE che i worker emettono, con una connessione finta che li registra.
"""

from __future__ import annotations

import pytest

from backend.memory.knowledge_graph import projector
from backend.memory.knowledge_graph.projector import InvalidGraphPayload
from backend.workers import graph_worker, mem0_worker, retry


# --- il doppio della connessione ------------------------------------------


class Row:
    def __init__(self, **fields):
        self.__dict__.update(fields)


class Savepoint:
    def __init__(self, conn):
        self._conn = conn
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True
        self._conn.rollbacks += 1


class FakeConn:
    """Registra gli UPDATE invece di eseguirli."""

    def __init__(self):
        self.calls: list[dict] = []
        self.savepoints: list[Savepoint] = []
        self.rollbacks = 0

    def begin_nested(self) -> Savepoint:
        savepoint = Savepoint(self)
        self.savepoints.append(savepoint)
        return savepoint

    def execute(self, statement, params=None):
        self.calls.append({"sql": str(statement), "params": dict(params or {})})
        return None

    @property
    def last(self) -> dict:
        return self.calls[-1]["params"]


class RateLimited(Exception):
    """Come si presenta un 429 di OpenAI attraverso mem0."""


# --- 1. 429 su Mem0: si riprova, senza perdere la riga ---------------------


def test_rate_limit_does_not_spend_an_attempt_and_waits_the_declared_delay():
    row = Row(id=42, attempts=0, throttled_count=0)
    conn = FakeConn()

    mem0_worker._reschedule(
        conn,
        row,
        RateLimited(
            "Error code: 429 - Rate limit reached for gpt-4o-mini in organization "
            "org-x on tokens per min (TPM). Please try again in 1.5s."
        ),
    )

    params = conn.last
    assert params["spend"] == 0, "un rate limit non e' un tentativo fallito del job"
    assert params["throttle"] == 1
    assert params["permanent"] is False
    # L'attesa e' quella dichiarata dal provider (piu' jitter), non due secondi.
    assert 1.5 <= params["delay"] <= 1.5 * 1.25


def test_repeated_rate_limits_eventually_cost_an_attempt():
    """Un 429 gratis all'infinito e' un loop, non una difesa."""
    conn = FakeConn()
    mem0_worker._reschedule(
        conn,
        Row(id=42, attempts=0, throttled_count=retry.THROTTLE_BUDGET),
        RateLimited("429 rate limit"),
    )
    assert conn.last["spend"] == 1


def test_rate_limited_pass_stops_early_but_keeps_what_it_applied(monkeypatch):
    """La riga che ha preso 429 resta in coda; quelle gia' applicate restano applicate."""
    applied: list[str] = []

    class Memory:
        def add(self, text_value, user_id, metadata=None):
            if len(applied) >= 2:
                raise RateLimited("Error code: 429 - Please try again in 0.2s.")
            applied.append(text_value)
            return {"results": [{"id": f"mem-{len(applied)}"}]}

    rows = [
        Row(id=index, op="add", mem0_payload={"text": f"fatto {index}", "user_id": "u1"},
            attempts=0, throttled_count=0)
        for index in (1, 2, 3, 4)
    ]

    class Conn(FakeConn):
        def execute(self, statement, params=None):
            sql = str(statement)
            if "SELECT" in sql:
                self.calls.append({"sql": sql, "params": dict(params or {})})
                return _Result(rows)
            return super().execute(statement, params)

    class _Result:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

    conn = Conn()
    monkeypatch.setattr(mem0_worker.mem0_client, "get_memory", lambda: Memory())
    monkeypatch.setattr(mem0_worker, "_engine", lambda: _EngineStub(conn))

    done = mem0_worker.drain_once()

    assert done == 2, "le prime due sono state applicate davvero"
    assert applied == ["fatto 1", "fatto 2"]
    reschedules = [c for c in conn.calls if "SET" in c["sql"] and "next_attempt_at" in c["sql"]]
    assert len(reschedules) == 1, "si smette al primo 429, senza bruciare le altre righe"
    assert reschedules[0]["params"]["spend"] == 0
    # La riga 4 non e' stata toccata: torna alla passata successiva, intatta.
    assert reschedules[0]["params"]["id"] == 3


_NO_CREDITS = (
    "Error code: 429 - {'error': {'message': 'You have no credits remaining. Add credits to "
    "continue using the API at https://platform.openai.com/settings/organization/billing/.', "
    "'type': 'insufficient_quota', 'param': None, 'code': 'credit_balance_exhausted'}}"
)


@pytest.fixture(autouse=True)
def _queue_not_paused(monkeypatch):
    monkeypatch.setattr(mem0_worker, "_paused_until", 0.0)


def test_exhausted_credit_is_not_a_rate_limit_and_spends_nothing():
    """Un 429 per credito finito non passa aspettando: non deve bruciare ne'
    i tentativi ne' il budget di banda, o la coda intera finisce in dead-letter."""
    conn = FakeConn()

    mem0_worker._reschedule(
        conn,
        Row(id=7, attempts=0, throttled_count=retry.THROTTLE_BUDGET),
        RateLimited(_NO_CREDITS),
    )

    params = conn.last
    assert (params["spend"], params["throttle"], params["permanent"]) == (0, 0, False)
    assert params["delay"] >= retry.EXHAUSTED_PAUSE_SECONDS


def test_a_real_rate_limit_is_not_mistaken_for_exhausted_credit():
    failure = retry.classify(
        RateLimited("Error code: 429 - Rate limit reached on tokens per min (TPM)."), attempts=0
    )
    assert failure.kind == "throttled"


def test_a_refused_pass_pauses_the_whole_queue(monkeypatch):
    """Dopo il 429 la passata successiva non sonda il provider con la riga dopo."""
    calls: list[str] = []

    class Memory:
        def add(self, text_value, user_id, metadata=None):
            calls.append(text_value)
            raise RateLimited(_NO_CREDITS)

    rows = [
        Row(id=index, op="add", mem0_payload={"text": f"fatto {index}", "user_id": "u1"},
            attempts=0, throttled_count=0)
        for index in (1, 2)
    ]

    class Conn(FakeConn):
        def execute(self, statement, params=None):
            if "SELECT" in str(statement):
                return type("R", (), {"all": lambda _self: list(rows)})()
            return super().execute(statement, params)

    conn = Conn()
    monkeypatch.setattr(mem0_worker.mem0_client, "get_memory", lambda: Memory())
    monkeypatch.setattr(mem0_worker, "_engine", lambda: _EngineStub(conn))

    assert mem0_worker.drain_once() == 0
    assert mem0_worker.drain_once() == 0

    assert calls == ["fatto 1"], "la seconda passata resta ferma durante la pausa"


class _EngineStub:
    def __init__(self, conn):
        self._conn = conn

    def begin(self):
        conn = self._conn

        class _Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, *exc):
                return False

        return _Ctx()


# --- 2. payload non valido: rifiutato prima della coda ---------------------


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"kind": None},
        {"kind": "node"},  # senza label/id_prop/id_value
        {"kind": "sproloquio", "label": "Entity"},
        {"kind": "node", "label": "Entity; MATCH (n) DETACH DELETE n //",
         "id_prop": "entity_id", "id_value": "x"},
        {"kind": "edge", "label": "APPROVES", "source": {"label": "Entity"}},
        "non sono nemmeno un oggetto",
    ],
)
def test_invalid_payload_is_refused_before_it_reaches_the_queue(payload):
    with pytest.raises(InvalidGraphPayload):
        projector.validate_payload(payload)


def test_canonical_emit_refuses_to_enqueue_an_unapplicable_payload():
    """Il rifiuto arriva a chi scrive, non al worker tre giorni dopo."""

    class Session:
        def execute(self, *args, **kwargs):  # pragma: no cover — non deve arrivarci
            raise AssertionError("nessun INSERT deve partire con un payload non valido")

    from backend.memory.knowledge_graph import canonical

    with pytest.raises(InvalidGraphPayload):
        canonical._emit(
            Session(),
            aggregate_type="entity",
            aggregate_id="00000000-0000-0000-0000-000000000001",
            consultant_id="c1",
            client_id="cl1",
            payload={"label": "Entity"},  # manca kind
        )


def test_poison_row_leaves_the_queue_at_the_first_pass():
    """Il veleno si sposta nel dead-letter: annotarlo sul posto violerebbe il
    CHECK della 0017 e, in una passata a transazione unica, fermerebbe la coda."""
    conn = FakeConn()

    graph_worker._handle_failure(
        conn,
        Row(id=76652, attempts=0, throttled_count=0),
        InvalidGraphPayload("payload graph_outbox non riconosciuto: kind=None"),
    )

    sql = " ".join(call["sql"] for call in conn.calls)
    assert "graph_outbox_dead_letter" in sql
    assert "DELETE FROM graph_outbox" in sql
    assert "next_attempt_at" not in sql, "una riga non applicabile non si riprogramma"
    assert conn.last["id"] == 76652
    assert conn.savepoints[-1].committed


def test_neo4j_down_is_not_treated_as_poison():
    """Un guasto momentaneo resta in coda: torna piu' tardi, non si butta via."""
    conn = FakeConn()
    graph_worker._handle_failure(
        conn, Row(id=7, attempts=1, throttled_count=0), ConnectionError("Neo4j irraggiungibile")
    )
    sql = " ".join(call["sql"] for call in conn.calls)
    assert "dead_letter" not in sql
    params = conn.last
    assert params["spend"] == 1
    assert params["delay"] > 0


def test_a_failure_to_record_the_outcome_does_not_stop_the_pass():
    """Nemmeno la contabilita' puo' bloccare la coda: e' cosi' che una riga sola
    ha fermato tutte le altre."""

    class Hostile(FakeConn):
        def execute(self, statement, params=None):
            raise RuntimeError("CheckViolation sulla riga gia' corrotta")

    conn = Hostile()
    graph_worker._handle_failure(
        conn, Row(id=1, attempts=0, throttled_count=0), InvalidGraphPayload("kind=None")
    )
    assert conn.savepoints[-1].rolled_back


# --- la classificazione, nei suoi casi limite ------------------------------


def test_retry_after_header_wins_over_the_message():
    class WithHeaders(Exception):
        class response:  # noqa: N801 — imita la forma di httpx.Response
            headers = {"retry-after": "30"}

    assert retry.retry_after_seconds(WithHeaders("429")) == 30.0


def test_absurd_retry_after_is_capped():
    class WithHeaders(Exception):
        class response:  # noqa: N801
            headers = {"retry-after": "86400"}

    assert retry.retry_after_seconds(WithHeaders("429")) == retry.MAX_HONORED_RETRY_AFTER_SECONDS


def test_backoff_grows_and_stays_within_the_ceiling():
    delays = [retry.backoff_delay(n) for n in range(12)]
    assert all(0 <= d <= retry.MAX_DELAY_SECONDS for d in delays)
    assert max(retry.backoff_delay(10) for _ in range(50)) > retry.backoff_delay(0)
