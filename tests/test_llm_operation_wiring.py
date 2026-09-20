"""P1.5 tappa 1-2 — l'operazione arriva dove si spende.

Il gateway rifiuta una chiamata senza operazione aperta (L2). E' una garanzia
utile solo se i punti d'ingresso l'operazione la aprono davvero: altrimenti L2
non protegge la misura, rompe il prodotto.

Questi test guardano il percorso vero, non l'unita': dalla riga di coda fino
dentro i thread del pool di estrazione, che e' il punto dove la spesa si perdeva
perche' i `ContextVar` non si ereditano.
"""

from __future__ import annotations

import pytest

from backend.llm import OperationKind, current_operation


def _plan(title: str, actor: str, step: str):
    """Un piano minimo ma **valido**.

    Se non lo e', `_extract` cattura l'errore di validazione come guasto
    ritentabile e ogni fonte viene estratta due volte: il test conterebbe il
    doppio delle chiamate e sembrerebbe un difetto del codice.
    """
    from backend.process_understanding import (
        ProcessActor,
        ProcessStep,
        ProcessUnderstanding,
        ProcessUnderstandingResult,
    )

    return ProcessUnderstandingResult(
        status="success",
        process=ProcessUnderstanding(
            title=title,
            actors=[ProcessActor(id=actor, label=actor.title(), kind="team")],
            steps=[ProcessStep(id=step, label=step.replace("_", " "), actor_ids=[actor])],
        ),
    )


def test_the_extraction_pool_carries_the_operation_into_its_threads(monkeypatch):
    """Le chiamate piu' care che facciamo: una per intervista, in parallelo.

    Se l'operazione non entra nei thread, sono esattamente quelle che non si
    vedono nel registro — e sono la maggior parte della spesa.
    """
    from backend.agents import process_synthesis
    from backend.llm import operation

    viste: list[object] = []

    def _fake_extraction(title, source_text, *, with_quality_report=True):
        viste.append(current_operation())
        return _plan(title, "ufficio_tecnico", "apri_richiesta")

    monkeypatch.setattr(process_synthesis, "build_process_understanding", _fake_extraction)

    sources = [
        {"id": f"s{n}", "name": f"Intervista {n}", "content": f"Testo della voce {n}."}
        for n in range(4)
    ]

    with operation(OperationKind.PLAN_SYNTHESIS, process_id="proc-42") as aperta:
        process_synthesis.extract_plan_from_sources("Ciclo passivo", sources)

    assert len(viste) == len(sources), (
        "una chiamata per fonte: se sono il doppio, il doppio del test non "
        "restituisce un piano valido e il retry per fonte sta scattando"
    )
    assert all(op is not None for op in viste), (
        "un'estrazione senza operazione e' spesa non attribuibile, ed e' il "
        "difetto per cui il credito e' finito senza che si sapesse dove"
    )
    assert {op.id for op in viste} == {aperta.id}, (
        "il lavoro in un thread e' lo *stesso* lavoro: un'operazione nuova per "
        "thread renderebbe illeggibile il costo per risultato"
    )
    assert {op.process_id for op in viste} == {"proc-42"}


def test_the_extraction_pool_carries_the_tenant_too(monkeypatch):
    """Il tenant nei thread era gia' un problema noto in questo repo.

    `test_product_language` lo dice a parole: «l'agente gira in un thread proprio,
    che non eredita la contextvar del tenant». Qui quella perdita e' chiusa per il
    pool di estrazione, e verificata.
    """
    from backend.agents import process_synthesis
    from backend.llm import operation
    from backend.security import get_current_tenant_id

    tenant_visti: list[str] = []

    def _fake_extraction(title, source_text, *, with_quality_report=True):
        tenant_visti.append(get_current_tenant_id())
        return _plan(title, "ufficio_tecnico", "apri_richiesta")

    monkeypatch.setattr(process_synthesis, "build_process_understanding", _fake_extraction)

    sources = [
        {"id": "s1", "name": "Intervista 1", "content": "Prima voce."},
        {"id": "s2", "name": "Intervista 2", "content": "Seconda voce."},
    ]

    with operation(OperationKind.PLAN_SYNTHESIS, tenant_id="acme"):
        process_synthesis.extract_plan_from_sources("Ciclo passivo", sources)

    assert tenant_visti == ["acme", "acme"]


class TestIPuntiDIngressoApronoLOperazione:
    """Se un ingresso si dimentica, L2 non protegge la misura: rompe il prodotto."""

    def test_la_coda_dei_piani_apre_un_operazione_di_sintesi(self, monkeypatch):
        from backend.workers import plan_worker

        vista: dict = {}

        def _fake_ensure(process_id):
            op = current_operation()
            vista["kind"] = op.kind if op else None
            vista["process_id"] = op.process_id if op else None
            vista["tenant_id"] = op.tenant_id if op else None
            raise RuntimeError("basta: quello che serve l'abbiamo letto")

        monkeypatch.setattr(
            "backend.agents.process_synthesis.ensure_process_plan", _fake_ensure
        )
        monkeypatch.setattr(plan_worker.wd, "fail_plan_materialization", lambda *a, **k: None)

        plan_worker._work_one(
            {"id": 1, "tenant_id": "acme", "process_id": "proc-7"}
        )

        assert vista["kind"] == OperationKind.PLAN_SYNTHESIS
        assert vista["process_id"] == "proc-7"
        assert vista["tenant_id"] == "acme"

    def test_la_coda_dei_confronti_apre_un_operazione_di_revisione(self, monkeypatch):
        from backend.workers import conformance_worker

        vista: dict = {}

        def _fake_audit(process_id):
            op = current_operation()
            vista["kind"] = op.kind if op else None
            vista["process_id"] = op.process_id if op else None
            vista["tenant_id"] = op.tenant_id if op else None
            return None

        monkeypatch.setattr(
            "backend.agents.conformance_audit.audit_process_conformance", _fake_audit
        )
        monkeypatch.setattr(
            conformance_worker.wd, "release_conformance_check", lambda *a, **k: None
        )

        conformance_worker._work_one(
            {"id": 1, "tenant_id": "acme", "process_id": "proc-9", "bpmn_model_id": "bpmn-9"}
        )

        assert vista["kind"] == OperationKind.CONFORMANCE_AUDIT
        assert vista["process_id"] == "proc-9"
        assert vista["tenant_id"] == "acme"

    def test_l_operazione_si_chiude_anche_quando_il_lavoro_fallisce(self, monkeypatch):
        """Un'operazione che resta aperta dopo un guasto attribuirebbe la spesa
        della riga successiva a quella di prima."""
        from backend.workers import plan_worker

        def _boom(process_id):
            raise RuntimeError("guasto")

        monkeypatch.setattr("backend.agents.process_synthesis.ensure_process_plan", _boom)
        monkeypatch.setattr(plan_worker.wd, "fail_plan_materialization", lambda *a, **k: None)

        plan_worker._work_one({"id": 1, "tenant_id": "acme", "process_id": "proc-7"})

        assert current_operation() is None


def test_a_model_call_without_an_entry_point_is_refused_not_silently_unattributed():
    """La garanzia dietro tutto: meglio un errore che una spesa senza nome."""
    from backend.llm import LlmTask, OperationNotOpen, run

    with pytest.raises(OperationNotOpen):
        run(task=LlmTask.PLAN_EXTRACTION, messages=[])
