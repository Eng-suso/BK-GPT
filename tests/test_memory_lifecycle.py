"""Ciclo di vita della memoria consulente: conferma con stato e cancellazione vera.

Copre i difetti C-MEM-01..C-MEM-04 emersi nel test E2E del Consultant:

- la conferma di una cancellazione si perdeva fra un turno e l'altro, perche'
  veniva ricostruita dal testo invece che ripresa da uno stato;
- "l'ho eliminata" non corrispondeva a una cancellazione: l'agente non aveva
  nemmeno un tool per farlo, e la delete diretta lasciava viva la riga
  canonical e i fratelli estratti dalla stessa frase;
- il recall tornava memorie vagamente simili come fossero fatti del profilo.

Mem0 e' finto (`FakeMem0`): il contratto che verifichiamo e' il nostro, non il
loro embedding. I pezzi che toccano Postgres canonical girano quando le DSN ci
sono (in CI ci sono) e vengono skippati altrove.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from backend.memory import forget, gateway, pending_actions
from backend.memory import mem0_client
from backend.memory.semantic import semantic_store
from backend.settings import settings
from backend.toolsets import memory as memory_tools

CANONICAL = bool(settings.canonical_database_url)
requires_canonical = pytest.mark.skipif(
    not CANONICAL, reason="CANONICAL_DATABASE_URL non configurata"
)


class FakeMem0:
    """Mem0 quanto basta: add / search / get_all / get / delete.

    `search` fa match per sottostringa e assegna uno score decrescente, cosi' i
    test possono asserire su soglia e ordine senza un modello di embedding.
    """

    def __init__(self) -> None:
        self.items: dict[str, dict] = {}
        self.add_calls: list[dict] = []
        self.search_calls: list[dict] = []
        self.undeletable: set[str] = set()

    # -- scrittura ------------------------------------------------------
    def add(self, messages, *, user_id=None, metadata=None, infer=True, **kwargs):
        self.add_calls.append(
            {"text": messages, "user_id": user_id, "metadata": metadata, "infer": infer}
        )
        memory_id = str(uuid.uuid4())
        self.items[memory_id] = {
            "id": memory_id,
            "memory": messages,
            "user_id": user_id,
            "metadata": metadata or {},
        }
        return {"results": [{"id": memory_id, "memory": messages, "event": "ADD"}]}

    # -- lettura --------------------------------------------------------
    def _scoped(self, filters):
        user_id = (filters or {}).get("user_id")
        return [i for i in self.items.values() if i["user_id"] == user_id]

    def search(self, query="", *, filters=None, top_k=20, threshold=0.1, **kwargs):
        self.search_calls.append(
            {"query": query, "filters": filters, "top_k": top_k, "threshold": threshold}
        )
        terms = [w for w in str(query).lower().split() if len(w) > 3]
        results = []
        for item in self._scoped(filters):
            haystack = item["memory"].lower()
            hits = sum(1 for term in terms if term in haystack)
            score = min(0.95, 0.2 * hits) if hits else 0.05
            if score < threshold:
                continue
            results.append({**item, "score": score})
        results.sort(key=lambda i: -i["score"])
        return {"results": results[:top_k]}

    def get_all(self, *, filters=None, top_k=20, **kwargs):
        return {"results": self._scoped(filters)[:top_k]}

    def get(self, memory_id):
        return self.items.get(str(memory_id))

    # -- cancellazione --------------------------------------------------
    def delete(self, memory_id=None):
        key = str(memory_id)
        if key in self.undeletable:
            return {"message": "ok"}  # bugia deliberata: la memoria resta
        self.items.pop(key, None)
        return {"message": "deleted"}


@pytest.fixture()
def fake_mem0(monkeypatch):
    fake = FakeMem0()
    monkeypatch.setattr(mem0_client, "get_memory", lambda: fake)
    monkeypatch.setattr(settings, "mem0_user_id", f"test-{uuid.uuid4()}")
    return fake


@pytest.fixture(autouse=True)
def clean_state():
    """Stato del consulente di default riportato com'era: questi test scrivono
    lapidi e azioni in attesa su righe condivise."""
    pending_actions.reset_memory_store()
    yield
    pending_actions.reset_memory_store()
    if not CANONICAL:
        return
    from backend.db import canonical_session

    with canonical_session(settings.default_consultant_id) as session:
        session.execute(text("DELETE FROM memory_tombstone"))
        session.execute(text("DELETE FROM pending_action"))


@pytest.fixture()
def thread(monkeypatch):
    thread_id = f"test-thread-{uuid.uuid4()}"
    from backend.agents import run_context

    monkeypatch.setattr(run_context, "active_thread_id", lambda: thread_id)
    return thread_id


def _result(tool_result: str) -> dict:
    """I tool ritornano il nome dell'azione e poi un JSON: qui serve il JSON."""
    return json.loads(tool_result[tool_result.index("{") :])


def _seed(fake: FakeMem0, statement: str) -> str:
    _, memory_id = semantic_store.add_mem0_memory_with_id(statement)
    assert memory_id, "il fake deve restituire un id"
    return memory_id


# --------------------------------------------------------------------------- #
# salvataggio verbatim
# --------------------------------------------------------------------------- #


def test_durable_fact_is_stored_verbatim(fake_mem0):
    statement = "Marco lavora principalmente con PMI e aziende industriali."
    semantic_store.add_mem0_memory_with_id(statement)

    call = fake_mem0.add_calls[-1]
    assert call["infer"] is False, "l'inferenza riscrive e spezza i fatti confermati"
    assert call["text"] == statement


def test_inference_can_be_re_enabled_by_settings(fake_mem0, monkeypatch):
    monkeypatch.setattr(settings, "memory_verbatim_facts", False)
    semantic_store.add_mem0_memory_with_id("qualcosa")
    assert fake_mem0.add_calls[-1]["infer"] is True


# --------------------------------------------------------------------------- #
# recall
# --------------------------------------------------------------------------- #


def test_recall_uses_top_k_and_threshold(fake_mem0):
    _seed(fake_mem0, "Marco e' un consulente indipendente con 32 anni di esperienza.")

    result = gateway.memory_search(
        consultant_id=settings.default_consultant_id,
        query="chi e' Marco come consulente",
        limit=5,
    )

    call = fake_mem0.search_calls[-1]
    assert call["top_k"] == 20, "`limit` non e' un parametro di Mem0 2.x: veniva ignorato"
    assert call["threshold"] == settings.memory_recall_threshold
    assert result["status"] == "ok"


def test_weak_matches_stay_out_of_the_profile(fake_mem0):
    _seed(fake_mem0, "Marco valida gli SLA con una checklist prima di ogni intervista.")

    result = gateway.memory_search(
        consultant_id=settings.default_consultant_id,
        query="quali sono i settori target del consulente",
        limit=5,
    )

    assert result["status"] == "empty"
    assert result["matches"] == []


def test_recall_context_carries_no_memory_ids(fake_mem0):
    memory_id = _seed(fake_mem0, "Marco lavora con PMI industriali.")

    rendered = semantic_store.search_consultant_memory(query="PMI industriali Marco")

    assert "PMI industriali" in rendered
    assert memory_id not in rendered
    assert "memory_id" not in rendered


def test_lifecycle_listing_does_carry_memory_ids(fake_mem0):
    memory_id = _seed(fake_mem0, "Marco lavora con PMI industriali.")

    listed = semantic_store.list_consultant_memories()

    assert [m["memory_id"] for m in listed["memories"]] == [memory_id]


# --------------------------------------------------------------------------- #
# conferma legata al comando, non ricostruita
# --------------------------------------------------------------------------- #


def test_propose_does_not_delete_anything(fake_mem0, thread):
    memory_id = _seed(fake_mem0, "Marco valida gli SLA con una checklist.")

    result = _result(
        memory_tools.manage_consultant_memory.invoke(
            {"operation": "forget", "query": "checklist SLA", "reason": "non e' vero"}
        )
    )

    assert result["status"] == "awaiting_confirmation"
    assert [t["memory_id"] for t in result["payload"]["targets"]] == [memory_id]
    assert memory_id in fake_mem0.items, "proporre non e' eliminare"


def test_confirmation_executes_the_frozen_target(fake_mem0, thread):
    memory_id = _seed(fake_mem0, "Marco valida gli SLA con una checklist.")
    memory_tools.manage_consultant_memory.invoke(
        {"operation": "forget", "query": "checklist SLA"}
    )

    # turno successivo: l'utente dice solo "si'". Nessun id, nessuna query.
    result = _result(
        memory_tools.manage_consultant_memory.invoke({"operation": "confirm"})
    )

    assert result["status"] == "deleted"
    assert result["payload"]["deleted"] == [memory_id]
    assert memory_id not in fake_mem0.items


def test_second_confirmation_is_a_noop(fake_mem0, thread):
    _seed(fake_mem0, "Marco valida gli SLA con una checklist.")
    memory_tools.manage_consultant_memory.invoke(
        {"operation": "forget", "query": "checklist SLA"}
    )
    memory_tools.manage_consultant_memory.invoke({"operation": "confirm"})

    result = _result(
        memory_tools.manage_consultant_memory.invoke({"operation": "confirm"})
    )

    assert result["status"] == "not_found"


def test_cancel_keeps_the_memory(fake_mem0, thread):
    memory_id = _seed(fake_mem0, "Marco valida gli SLA con una checklist.")
    memory_tools.manage_consultant_memory.invoke(
        {"operation": "forget", "query": "checklist SLA"}
    )

    result = _result(
        memory_tools.manage_consultant_memory.invoke({"operation": "cancel"})
    )

    assert result["status"] == "cancelled"
    assert memory_id in fake_mem0.items


def test_confirmation_without_a_proposal_deletes_nothing(fake_mem0, thread):
    memory_id = _seed(fake_mem0, "Marco valida gli SLA con una checklist.")

    result = _result(
        memory_tools.manage_consultant_memory.invoke({"operation": "confirm"})
    )

    assert result["status"] == "not_found"
    assert memory_id in fake_mem0.items


def test_a_new_proposal_supersedes_the_previous_one(fake_mem0, thread):
    first = _seed(fake_mem0, "Marco valida gli SLA con una checklist.")
    second = _seed(fake_mem0, "Marco lavora soltanto in inglese.")
    memory_tools.manage_consultant_memory.invoke(
        {"operation": "forget", "query": "checklist SLA"}
    )
    memory_tools.manage_consultant_memory.invoke(
        {"operation": "forget", "query": "soltanto inglese"}
    )

    result = _result(
        memory_tools.manage_consultant_memory.invoke({"operation": "confirm"})
    )

    assert result["payload"]["deleted"] == [second]
    assert first in fake_mem0.items


def test_partial_deletion_is_reported_as_partial(fake_mem0, thread):
    memory_id = _seed(fake_mem0, "Marco valida gli SLA con una checklist.")
    fake_mem0.undeletable.add(memory_id)  # delete che risponde ok e non cancella
    memory_tools.manage_consultant_memory.invoke(
        {"operation": "forget", "query": "checklist SLA"}
    )

    result = _result(
        memory_tools.manage_consultant_memory.invoke({"operation": "confirm"})
    )

    assert result["status"] == "partial"
    assert result["payload"]["still_present"] == [memory_id]


# --------------------------------------------------------------------------- #
# la cancellazione regge nel tempo (lapidi)
# --------------------------------------------------------------------------- #


@requires_canonical
def test_forgotten_memory_never_comes_back_even_with_a_new_id(fake_mem0, thread):
    statement = "Marco valida gli SLA con una checklist prima di ogni intervista."
    _seed(fake_mem0, statement)
    memory_tools.manage_consultant_memory.invoke(
        {"operation": "forget", "query": "checklist SLA intervista"}
    )
    memory_tools.manage_consultant_memory.invoke({"operation": "confirm"})

    # Mem0 riscrive lo stesso fatto sotto un id nuovo (o la proiezione viene
    # ricostruita dal log): il recall deve comunque non mostrarlo piu'.
    _seed(fake_mem0, statement)

    result = gateway.memory_search(
        consultant_id=settings.default_consultant_id,
        query="checklist SLA intervista",
        limit=5,
    )

    assert result["status"] == "empty"


@requires_canonical
def test_tombstone_matches_a_reworded_but_identical_statement(fake_mem0, thread):
    _seed(fake_mem0, "Marco valida gli SLA con una checklist.")
    memory_tools.manage_consultant_memory.invoke(
        {"operation": "forget", "query": "checklist SLA"}
    )
    memory_tools.manage_consultant_memory.invoke({"operation": "confirm"})

    _seed(fake_mem0, "  marco valida gli SLA con una CHECKLIST!  ")

    result = gateway.memory_search(
        consultant_id=settings.default_consultant_id,
        query="checklist SLA",
        limit=5,
    )

    assert result["status"] == "empty"


@requires_canonical
def test_canonical_row_is_rejected_so_a_replay_cannot_resurrect_it(fake_mem0, thread):
    from backend.db import canonical_session
    from backend.memory import canonical_memory

    statement = f"Marco tiene un registro {uuid.uuid4().hex[:8]} delle interviste."
    row_id = canonical_memory.write_semantic_memory(
        settings.default_consultant_id,
        kind="fact",
        statement=statement,
        category="delivery_method",
        already_applied_mem0_id=None,
    )
    _seed(fake_mem0, statement)
    memory_tools.manage_consultant_memory.invoke(
        {"operation": "forget", "query": statement}
    )
    memory_tools.manage_consultant_memory.invoke({"operation": "confirm"})

    with canonical_session(settings.default_consultant_id) as session:
        status = session.execute(
            text("SELECT status FROM semantic_memory WHERE id = CAST(:id AS uuid)"),
            {"id": row_id},
        ).scalar_one()
    assert status == "rejected"


@requires_canonical
def test_tombstones_are_scoped_to_the_consultant(fake_mem0, thread):
    _seed(fake_mem0, "Marco valida gli SLA con una checklist.")
    memory_tools.manage_consultant_memory.invoke(
        {"operation": "forget", "query": "checklist SLA"}
    )
    memory_tools.manage_consultant_memory.invoke({"operation": "confirm"})

    mine, my_hashes = forget.tombstones(settings.default_consultant_id)
    assert mine and my_hashes

    # un altro consulente non eredita le lapidi del primo (RLS)
    theirs, their_hashes = forget.tombstones(str(uuid.uuid4()))
    assert theirs == set()
    assert their_hashes == set()


# --------------------------------------------------------------------------- #
# lo stato dell'azione in attesa
# --------------------------------------------------------------------------- #


def test_pending_action_is_visible_to_the_next_turn(thread):
    from backend.agents.primary_scope import agent_scope_state, build_scope_system_prompt

    pending_actions.propose(
        consultant_id=settings.default_consultant_id,
        thread_id=thread,
        action="forget_memory",
        params={"targets": [{"memory_id": "m1", "statement": "un fatto"}]},
        preview="- un fatto",
    )

    state = agent_scope_state(None, "agent", None, thread_id=thread)
    prompt = build_scope_system_prompt(state)

    assert state["pending_action"]["action"] == "forget_memory"
    assert "AZIONE IN ATTESA DI CONFERMA" in prompt
    assert "un fatto" in prompt


def test_expired_pending_action_is_not_confirmable(thread, monkeypatch):
    """Sul fallback in-process, dove il tempo lo decide `_now`. Sul path
    Postgres la stessa regola sta nella query (`expires_at > now()`)."""
    import datetime as dt

    from backend.memory import pending_actions as pa

    monkeypatch.setattr(settings, "canonical_database_url", None)
    pa.propose(
        consultant_id=settings.default_consultant_id,
        thread_id=thread,
        action="forget_memory",
        params={"targets": []},
        preview="- un fatto",
        ttl_seconds=60,
    )

    real_now = pa._now
    monkeypatch.setattr(pa, "_now", lambda: real_now() + dt.timedelta(hours=2))

    assert (
        pa.open_action(
            consultant_id=settings.default_consultant_id, thread_id=thread
        )
        is None
    )
