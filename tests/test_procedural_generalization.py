"""P7.3 — promozione client -> consultant come generalizzazione (INV-13).

`generalize` legge un playbook client-scoped, lo fa riscrivere senza riferimenti
cliente e crea un NUOVO candidate consultant-scoped (`derived_from` = sorgente,
`guardrail_status='pending'`). Il guardrail in fase di promote blocca se un nome
cliente e' sopravvissuto. Mai una copia.

L'LLM di generalizzazione e' sostituito da un fake. Skip senza CANONICAL_*.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings

if not settings.canonical_migrator_url or not settings.canonical_database_url:
    pytest.skip(
        "CANONICAL_MIGRATOR_URL / CANONICAL_DATABASE_URL non configurate",
        allow_module_level=True,
    )

from backend import workspace_database  # noqa: E402
from backend.memory import canonical_memory  # noqa: E402
from backend.memory import scope as canonical_scope  # noqa: E402
from backend.memory.procedural.extraction import GeneralizedPlaybook  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)


@pytest.fixture()
def project_scope(monkeypatch):
    workspace_project_id = f"proj-gen-{uuid.uuid4().hex[:8]}"
    client_name = f"Bianchi Logistica {uuid.uuid4().hex[:6]}"
    monkeypatch.setattr(
        workspace_database,
        "get_project",
        lambda p: {"id": p, "name": "Progetto Gen", "client": client_name}
        if p == workspace_project_id
        else None,
    )
    monkeypatch.setattr(workspace_database, "get_process", lambda p: None)

    started_at = datetime.now(timezone.utc)
    yield workspace_project_id, client_name

    client_ws = f"client:{canonical_scope._slug(client_name)}"
    with MIGRATOR.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.current_consultant_id', :v, true)"),
            {"v": settings.default_consultant_id},
        )
        conn.execute(text("SELECT set_config('app.current_client_id', :v, true)"), {"v": ""})
        conn.execute(
            text(
                "DELETE FROM procedural_memory "
                "WHERE consultant_id = :c AND scope = 'consultant' AND created_at >= :t"
            ),
            {"c": settings.default_consultant_id, "t": started_at},
        )
        conn.execute(text("DELETE FROM client WHERE workspace_id = :w"), {"w": client_ws})


def _make_source_playbook(client_id: str, project_id: str, client_name: str) -> str:
    return canonical_memory.write_procedural_candidate(
        settings.default_consultant_id,
        kind="playbook",
        title=f"Delivery settimanale per {client_name}",
        applies_when="ogni settimana di delivery",
        body=(
            f"Con {client_name} invia lo stato il venerdi, blocca il 30 percento "
            f"del budget alla conferma e allinea le operations."
        ),
        scope="client",
        client_id=client_id,
        project_id=project_id,
    )


def test_generalize_creates_consultant_candidate_and_promotes_when_clean(project_scope, monkeypatch):
    workspace_project_id, client_name = project_scope
    consultant = settings.default_consultant_id
    resolved = canonical_scope.resolve(workspace_project_id)
    source_id = _make_source_playbook(resolved.client_id, resolved.project_id, client_name)

    clean = GeneralizedPlaybook(
        title="Cadenza di stato settimanale nella delivery",
        applies_when="delivery con reporting settimanale",
        body=(
            "A fine settimana invia una nota di stato: avanzamento, rischi, blocchi, "
            "priorita' della settimana successiva. Evita di far slittare senza avvisare."
        ),
    )
    monkeypatch.setattr(
        "backend.memory.procedural.extraction.generalize_playbook_body",
        lambda playbook, client_names, **kwargs: clean,
    )

    from backend.toolsets.memory import manage_consultant_playbook as tool

    out = tool.invoke(
        {"operation": "generalize", "project": workspace_project_id, "playbook_id": source_id}
    )
    payload = json.loads(out.split("\n", 1)[1])
    assert payload["status"] == "saved"
    candidate_id = payload["payload"]["candidate_id"]

    detail = canonical_memory.get_procedural(candidate_id, consultant_id=consultant)
    assert detail["scope"] == "consultant"
    assert detail["client_id"] is None
    assert detail["status"] == "candidate"
    assert detail["guardrail_status"] == "pending"
    assert [str(x) for x in detail["derived_from"]] == [source_id]

    promoted = canonical_memory.promote_procedural(candidate_id, consultant_id=consultant)
    assert promoted["status"] == "promoted"


def test_generalize_that_leaves_a_client_name_is_blocked_at_promote(project_scope, monkeypatch):
    workspace_project_id, client_name = project_scope
    consultant = settings.default_consultant_id
    resolved = canonical_scope.resolve(workspace_project_id)
    source_id = _make_source_playbook(resolved.client_id, resolved.project_id, client_name)

    leaky = GeneralizedPlaybook(
        title="Metodo di delivery",
        applies_when="",
        body=f"Allinea sempre {client_name} prima di partire con la settimana.",
    )
    monkeypatch.setattr(
        "backend.memory.procedural.extraction.generalize_playbook_body",
        lambda playbook, client_names, **kwargs: leaky,
    )

    from backend.toolsets.memory import manage_consultant_playbook as tool

    out = tool.invoke(
        {"operation": "generalize", "project": workspace_project_id, "playbook_id": source_id}
    )
    candidate_id = json.loads(out.split("\n", 1)[1])["payload"]["candidate_id"]

    result = canonical_memory.promote_procedural(candidate_id, consultant_id=consultant)
    assert result["status"] == "guardrail_flagged"
    assert any(f["kind"] == "client_reference" for f in result["findings"])
