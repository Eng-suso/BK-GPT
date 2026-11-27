"""Due persone, due account: niente di quello che fa una arriva all'altra.

Il percorso e' quello vero: token Supabase firmato (JWKS servito da una
funzione, nessuna rete), API HTTP, Postgres del workspace e canonical. Ogni
persona ha il suo spazio di lavoro (`acct-<sub>`), la sua memoria (il
consulente canonical e lo spazio Mem0 ricavati dal suo id) e il suo limite di
spesa. Qui si prova che lo restano anche quando l'altra conosce i suoi id.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm

from backend.settings import settings

pytestmark = pytest.mark.skipif(
    not (settings.workspace_database_url and settings.canonical_database_url),
    reason="servono WORKSPACE_DATABASE_URL e CANONICAL_DATABASE_URL",
)

SUPABASE_URL = "https://progetto.supabase.co"
MODEL = "gpt-5.6-luna"


@pytest.fixture(scope="module")
def signing_key():
    private = ec.generate_private_key(ec.SECP256R1())
    public = json.loads(ECAlgorithm.to_jwk(private.public_key()))
    public.update({"kid": "kid-1", "alg": "ES256"})
    return private, public


@pytest.fixture()
def api(monkeypatch, signing_key):
    """L'app con gli account personali accesi e il modello finto (nessuna spesa)."""
    from backend.app import app
    from backend.auth import supabase_jwt

    monkeypatch.setattr(settings, "delir_auth_enabled", True)
    monkeypatch.setattr(settings, "delir_auth_provider", "supabase")
    monkeypatch.setattr(settings, "supabase_url", SUPABASE_URL)
    monkeypatch.setattr(settings, "supabase_publishable_key", "sb_publishable_test")
    monkeypatch.setattr(settings, "delir_api_token", "token-condiviso-che-non-deve-bastare-000")
    monkeypatch.setattr(settings, "delir_admin_token", "chiave-admin-distinta-0000000000000000")
    monkeypatch.setattr(settings, "delir_egress_allowed_hosts", "progetto.supabase.co")
    monkeypatch.setattr(settings, "delir_fake_llm", True)

    cache = supabase_jwt.JwksCache(
        "jwks", ttl_seconds=600, max_stale_seconds=0, fetch=lambda _url: {"keys": [signing_key[1]]}
    )
    verifier = supabase_jwt.SupabaseTokenVerifier(SUPABASE_URL, audience="authenticated", jwks=cache)
    monkeypatch.setattr(supabase_jwt, "get_verifier", lambda: verifier)
    with TestClient(app) as client:
        yield client


class Person:
    """Una persona con il suo token: ogni richiesta porta solo quello."""

    def __init__(self, client: TestClient, private_key) -> None:
        self.id = str(uuid.uuid4())
        self.tenant = f"acct-{self.id}"
        self._client = client
        now = int(time.time())
        self._token = jwt.encode(
            {
                "iss": f"{SUPABASE_URL}/auth/v1",
                "aud": "authenticated",
                "sub": self.id,
                "role": "authenticated",
                "is_anonymous": False,
                "iat": now,
                "exp": now + 1800,
            },
            private_key,
            algorithm="ES256",
            headers={"kid": "kid-1"},
        )

    def headers(self, **extra: str) -> dict[str, str]:
        # Un header del tenant "pilot" come lo manderebbe un browser rimasto
        # con la sessione vecchia: non deve contare niente.
        return {"Authorization": f"Bearer {self._token}", "X-DeliR-Tenant-ID": "pilot", **extra}

    def get(self, path: str, **kw):
        return self._client.get(path, headers=self.headers(), **kw)

    def post(self, path: str, **kw):
        return self._client.post(path, headers=self.headers(), **kw)

    def patch(self, path: str, **kw):
        return self._client.patch(path, headers=self.headers(), **kw)

    def delete(self, path: str, **kw):
        return self._client.delete(path, headers=self.headers(), **kw)


@pytest.fixture()
def anna(api, signing_key) -> Person:
    return Person(api, signing_key[0])


@pytest.fixture()
def bruno(api, signing_key) -> Person:
    return Person(api, signing_key[0])


def _client_with_project(person: Person, name: str) -> tuple[dict, dict]:
    created = person.post("/v1/workspace/clients", json={"name": name})
    assert created.status_code == 200, created.text
    project = person.post(
        "/v1/workspace/projects",
        json={"client_id": created.json()["id"], "name": f"Mappatura {name}"},
    )
    assert project.status_code == 200, project.text
    return created.json(), project.json()


def test_each_person_sees_only_their_own_clients_and_projects(anna, bruno):
    client, project = _client_with_project(anna, f"Esaote {uuid.uuid4().hex[:6]}")

    names = [c["name"] for c in bruno.get("/v1/workspace/clients").json()]
    assert client["name"] not in names
    assert client["name"] in [c["name"] for c in anna.get("/v1/workspace/clients").json()]
    assert project["id"] not in [p["id"] for p in bruno.get("/v1/workspace/projects").json()]


def test_knowing_the_id_is_not_enough(anna, bruno):
    client, project = _client_with_project(anna, f"Brembo {uuid.uuid4().hex[:6]}")

    assert bruno.get(f"/v1/workspace/projects/{project['id']}").status_code == 404
    renamed = bruno.patch(f"/v1/workspace/clients/{client['id']}", json={"name": "Preso"})
    assert renamed.status_code in {400, 404}
    deleted = bruno.delete(f"/v1/workspace/clients/{client['id']}")
    assert deleted.status_code in {400, 404}

    # Il cliente di Anna c'e' ancora, col suo nome.
    still = [c for c in anna.get("/v1/workspace/clients").json() if c["id"] == client["id"]]
    assert still and still[0]["name"] == client["name"]


def test_the_same_client_name_in_two_accounts_are_two_clients(anna, bruno):
    """Dieci consulenti possono seguire tutti un cliente che si chiama allo stesso modo."""
    name = f"Lavazza {uuid.uuid4().hex[:6]}"
    _client_with_project(anna, name)
    _client_with_project(bruno, name)

    assert [c["name"] for c in anna.get("/v1/workspace/clients").json()].count(name) == 1
    assert [c["name"] for c in bruno.get("/v1/workspace/clients").json()].count(name) == 1


def test_conversations_belong_to_whoever_started_them(anna, bruno):
    created = anna.post(
        "/v1/consultant-chat/sessions", json={"model_name": MODEL, "scope": {"type": "consultant"}}
    )
    assert created.status_code == 200, created.text
    thread_id = created.json()["thread_id"]
    with anna._client.stream(
        "POST",
        f"/v1/consultant-chat/sessions/{thread_id}/messages/stream",
        headers=anna.headers(),
        json={"message": "riassumi il processo ordini", "model_name": MODEL, "scope": {"type": "consultant"}},
    ) as response:
        assert response.status_code == 200
        assert [json.loads(line) for line in response.iter_lines() if line.strip()][-1]["type"] == "done"

    assert thread_id not in [s["thread_id"] for s in bruno.get("/v1/consultant-chat/sessions").json()]
    assert bruno.get(f"/v1/consultant-chat/sessions/{thread_id}").status_code == 404

    # Scrivere nella conversazione di Anna non e' possibile, nemmeno conoscendone l'id.
    hijack = bruno.post(
        f"/v1/consultant-chat/sessions/{thread_id}/messages/stream",
        json={"message": "cosa ti ha detto Anna?", "model_name": MODEL, "scope": {"type": "consultant"}},
    )
    assert hijack.status_code >= 400
    detail = anna.get(f"/v1/consultant-chat/sessions/{thread_id}").json()
    assert all("Anna" not in m["content"] for m in detail["messages"])


def test_the_agent_memory_of_one_thread_is_keyed_by_its_account(anna, bruno):
    """Il checkpointer LangGraph conosce solo una chiave: porta l'account."""
    from backend.security import reset_current_tenant_id, set_current_tenant_id
    from backend.services.agent_runtime import agent_checkpoint_thread_id

    keys = []
    for person in (anna, bruno):
        token = set_current_tenant_id(person.tenant)
        try:
            keys.append(agent_checkpoint_thread_id("stesso-thread", None))
        finally:
            reset_current_tenant_id(token)

    assert keys[0] != keys[1]
    assert keys[0].startswith(anna.tenant)


def test_canonical_memory_is_written_under_the_persons_consultant(anna, bruno):
    """Il grafo e la memoria di un progetto vivono sotto il consulente della persona."""
    from sqlalchemy import text

    from backend.db import canonical_session
    from backend.memory import scope
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    name = f"Ferrero {uuid.uuid4().hex[:6]}"
    _, project = _client_with_project(anna, name)

    token = set_current_tenant_id(anna.tenant)
    try:
        resolved = scope.resolve(project["id"])
    finally:
        reset_current_tenant_id(token)

    assert resolved.consultant_id == anna.id
    with canonical_session(anna.id) as session:
        mine = session.execute(
            text("SELECT count(*) FROM client WHERE id = CAST(:i AS uuid)"), {"i": resolved.client_id}
        ).scalar_one()
    with canonical_session(bruno.id) as session:
        theirs = session.execute(
            text("SELECT count(*) FROM client WHERE id = CAST(:i AS uuid)"), {"i": resolved.client_id}
        ).scalar_one()
    assert (mine, theirs) == (1, 0)


def test_mem0_keeps_one_namespace_per_account(anna, bruno):
    from backend.memory.mem0_client import mem0_user_id

    assert mem0_user_id(anna.id) == anna.id
    assert mem0_user_id(bruno.id) == bruno.id
    assert mem0_user_id(str(settings.default_consultant_id)) == settings.mem0_user_id


def test_spending_is_counted_per_person(anna, bruno, monkeypatch):
    """Quello che spende Anna esaurisce il limite di Anna, non quello di Bruno."""
    from backend.llm import budget
    from backend.workspace_storage import WorkspaceLlmUsage, workspace_connection

    monkeypatch.setattr(settings, "usage_limits_enabled", True)
    monkeypatch.setattr(settings, "usage_session_budget_usd", 1.0)
    budget.reset_cache()
    # La sessione di ognuno parte alla sua prima richiesta.
    for person in (anna, bruno):
        assert person.get("/v1/usage/me").json()["blocking"] is None
        budget.status(person.id, tenant_id=person.tenant, open_session=True)

    with workspace_connection() as session:
        session.add(
            WorkspaceLlmUsage(
                id=uuid.uuid4().hex,
                tenant_id=anna.tenant,
                user_id=anna.id,
                operation_kind="chat_turn",
                operation_id=uuid.uuid4().hex,
                task="chat_turn",
                model="gpt-test",
                input_tokens=0,
                output_tokens=0,
                reasoning_tokens=0,
                cached_input_tokens=0,
                outcome="ok",
                duration_ms=1,
                attempt=1,
                cost_estimate="5",
                created_at=datetime.now(UTC).isoformat(),
            )
        )

    budget.reset_cache()
    anna_status = budget.status(anna.id, tenant_id=anna.tenant, open_session=True)
    bruno_status = budget.status(bruno.id, tenant_id=bruno.tenant, open_session=True)
    budget.reset_cache()

    assert anna_status.session.used_usd == Decimal("5")
    assert anna_status.blocking is not None
    assert bruno_status.session.used_usd == Decimal("0")
    assert bruno_status.blocking is None

    usage = anna.get("/v1/usage/me").json()
    assert usage["blocking"] == "session"
    assert bruno.get("/v1/usage/me").json()["blocking"] is None


def test_the_admin_sets_one_persons_limit_without_touching_the_others(anna, bruno):
    admin = {"X-DeliR-Admin-Token": settings.delir_admin_token}

    changed = anna._client.put(
        f"/v1/usage/plans/{anna.id}", headers=bruno.headers(**admin), json={"week_budget_usd": "42"}
    )
    assert changed.status_code == 200, changed.text

    mine = anna._client.get(f"/v1/usage/plans/{anna.id}", headers=bruno.headers(**admin)).json()
    theirs = anna._client.get(f"/v1/usage/plans/{bruno.id}", headers=bruno.headers(**admin)).json()
    assert mine["week"]["limit_usd"] == "42"
    assert theirs["week"]["limit_usd"] != "42"
