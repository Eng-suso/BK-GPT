"""Il revisore legge davvero, e non rilegge cio' che ha gia' letto.

Due difetti diversi nello stesso punto, e questo file li tiene entrambi.

**Il revisore non leggeva niente.** `_audit_sources` lancia il revisore in un
pool di thread, e un thread nuovo nasce con i `ContextVar` vuoti. Da quando il
revisore passa dal gateway (P1, t.5), ogni sua chiamata partiva senza
operazione, il gateway la rifiutava (L2), e l'`except` del pool la contava come
fonte non letta. In produzione il verdetto era `failed` su ogni processo, e
nessun test lo vedeva: i test usavano un revisore finto, che non passa dal
gateway e quindi non si accorge dell'operazione mancante.

**Il revisore rileggeva tutto.** Ogni confronto rifatto - un canvas risalvato,
una verifica chiesta di nuovo - rileggeva ogni fonte contro lo stesso piano, e
ripagava la stessa risposta. Ora il verdetto e' un artefatto (P2).
"""

from __future__ import annotations

import uuid

import pytest

from backend.agents.conformance_audit import (
    AuditedFact,
    SourceAuditRequest,
    SourceAuditVerdict,
    evaluate_conformance,
)
from backend.agents.process_snapshot import ProcessKnowledgeSnapshot
from backend.llm import LlmTask, OperationKind, OperationNotOpen, current_operation, operation
from backend.process_understanding import ProcessActor, ProcessStep, ProcessUnderstanding
from backend.settings import settings

if not settings.workspace_database_url:
    pytest.skip("serve WORKSPACE_DATABASE_URL", allow_module_level=True)

SOURCE = (
    "Paolo Marchetti, Manutenzione. Quando la linea e' ferma non aspetto Acquisti: "
    "chiamo direttamente il fornitore e faccio consegnare."
)
PAOLO = {"id": "src-paolo", "name": "Intervista Paolo", "content": SOURCE}


def _snapshot(step_label: str = "Crea ordine") -> ProcessKnowledgeSnapshot:
    return ProcessKnowledgeSnapshot(
        process_id="p",
        process_name="Acquisti",
        process_understanding=ProcessUnderstanding(
            title="Acquisti",
            actors=[ProcessActor(id="acquisti", label="Acquisti", kind="team")],
            steps=[ProcessStep(id="crea_ordine", label=step_label, actor_ids=["acquisti"])],
        ).model_dump(mode="json"),
    )


def _evaluate(snapshot: ProcessKnowledgeSnapshot, auditor, *, reuse: bool = True):
    return evaluate_conformance(
        snapshot,
        sources=[PAOLO],
        canvas_xml=None,
        review_brief=None,
        auditor=auditor,
        reuse_artifacts=reuse,
    )


def _gateway_like(calls: list[SourceAuditRequest]):
    """Un revisore finto che si comporta come il gateway su L2.

    E' la differenza che conta: il revisore finto dei test di prima rispondeva
    anche senza operazione, ed e' esattamente per questo che il difetto e'
    passato.
    """

    def _audit(request: SourceAuditRequest) -> SourceAuditVerdict:
        if current_operation() is None:
            raise OperationNotOpen("revisore chiamato fuori da un'operazione")
        calls.append(request)
        return SourceAuditVerdict(
            missing_facts=[
                AuditedFact(
                    kind="activity",
                    diagram_change="new_activity",
                    statement="chiama il fornitore",
                    quote="chiamo direttamente il fornitore",
                )
            ]
        )

    return _audit


@pytest.fixture()
def tenant():
    """Un tenant per test: i verdetti sopravvivono al test che li ha scritti."""
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
    try:
        yield
    finally:
        reset_current_tenant_id(token)


# --- il revisore legge davvero ---------------------------------------------


def test_the_reviewer_reads_inside_the_operation_that_asked(tenant):
    """La regressione: nel pool l'operazione c'e', e la fonte viene letta."""
    calls: list[SourceAuditRequest] = []

    with operation(OperationKind.CONFORMANCE_AUDIT):
        report = _evaluate(_snapshot(), _gateway_like(calls), reuse=False)

    assert report.llm_audit == "done", report.llm_audit_note
    assert report.sources_audited == 1
    assert len(calls) == 1
    # Il rilievo del revisore c'e': la fonte e' stata letta davvero. (Gli altri
    # layer sono deterministici e qui non c'entrano: il canvas di prova e' vuoto.)
    assert [item.code for item in report.findings if item.layer == "source_coverage"] == [
        "missing_activity"
    ]


def test_a_forgotten_entry_point_is_a_bug_not_a_missing_source(tenant):
    """Senza operazione aperta il confronto non degrada a "fonte non letta":
    un punto d'ingresso dimenticato e' un difetto, e deve fare rumore."""
    with pytest.raises(OperationNotOpen):
        _evaluate(_snapshot(), _gateway_like([]), reuse=False)


# --- il revisore non rilegge -----------------------------------------------


def test_the_same_source_against_the_same_plan_is_read_once(tenant):
    calls: list[SourceAuditRequest] = []

    with operation(OperationKind.CONFORMANCE_AUDIT):
        prima = _evaluate(_snapshot(), _gateway_like(calls))
        dopo = _evaluate(_snapshot(), _gateway_like(calls))

    assert len(calls) == 1, "il verdetto pagato una volta non si ripaga"
    assert prima.llm_calls == 1
    assert dopo.llm_calls == 0
    assert dopo.sources_reused == 1
    assert dopo.sources_audited == 1, "riusata e' comunque confrontata"
    assert dopo.llm_audit == "done"
    # Il verdetto riusato passa dalla stessa verifica delle citazioni.
    assert [item.message for item in dopo.findings] == [item.message for item in prima.findings]


def test_a_changed_plan_is_a_new_comparison(tenant):
    """Il verdetto di prima parlava di un altro piano: riusarlo darebbe per
    conforme cio' che nessuno ha guardato."""
    calls: list[SourceAuditRequest] = []

    with operation(OperationKind.CONFORMANCE_AUDIT):
        _evaluate(_snapshot("Crea ordine"), _gateway_like(calls))
        dopo = _evaluate(_snapshot("Crea ordine d'urgenza"), _gateway_like(calls))

    assert len(calls) == 2
    assert dopo.sources_reused == 0


def test_a_reused_verdict_leaves_a_cache_hit_in_the_ledger(tenant, monkeypatch):
    written: list[dict] = []
    monkeypatch.setattr("backend.llm.gateway.record", lambda **kwargs: written.append(kwargs))

    with operation(OperationKind.CONFORMANCE_AUDIT):
        _evaluate(_snapshot(), _gateway_like([]))
        written.clear()
        _evaluate(_snapshot(), _gateway_like([]))

    evitate = [row for row in written if row.get("outcome") == "cache_hit"]
    assert len(evitate) == 1
    assert evitate[0]["task"] == LlmTask.CONFORMANCE_AUDIT.value
    assert evitate[0]["prompt_version"].startswith("conformance_audit@")


def test_without_reuse_every_comparison_reads_again(tenant):
    """Il riuso si chiede: un revisore finto nei test non eredita il magazzino."""
    calls: list[SourceAuditRequest] = []

    with operation(OperationKind.CONFORMANCE_AUDIT):
        _evaluate(_snapshot(), _gateway_like(calls), reuse=False)
        _evaluate(_snapshot(), _gateway_like(calls), reuse=False)

    assert len(calls) == 2


def test_an_unreachable_store_does_not_stop_the_comparison(tenant, monkeypatch):
    def _esplode(_keys):
        raise RuntimeError("database non raggiungibile")

    monkeypatch.setattr("backend.workspace_database.source_audits_by_key", _esplode)
    calls: list[SourceAuditRequest] = []

    with operation(OperationKind.CONFORMANCE_AUDIT):
        report = _evaluate(_snapshot(), _gateway_like(calls))

    assert report.llm_audit == "done"
    assert len(calls) == 1


def test_another_tenant_never_reuses_the_verdict():
    """L8."""
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    calls: list[SourceAuditRequest] = []
    for _ in range(2):
        token = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
        try:
            with operation(OperationKind.CONFORMANCE_AUDIT):
                _evaluate(_snapshot(), _gateway_like(calls))
        finally:
            reset_current_tenant_id(token)

    assert len(calls) == 2
