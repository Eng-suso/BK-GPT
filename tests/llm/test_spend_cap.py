"""Il freno d'emergenza: un tetto di spesa per tutta l'installazione, sulle 24 ore.

Il contatore per consulente lascia finire il lavoro gia' accettato; questo tetto
ferma anche quello che parte dopo, in background compreso: le code si fermano,
le chiamate nuove si rifiutano, la chat risponde 429.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backend.llm import LlmTask, OperationKind, budget, operation, run, spend_cap
from backend.llm_config import MissingProviderKey
from backend.security import get_current_tenant_id
from backend.settings import settings
from backend.workspace_storage import WorkspaceLlmUsage, workspace_connection


@pytest.fixture(autouse=True)
def _fresh_cap():
    spend_cap.reset_cache()
    budget.reset_cache()
    yield
    spend_cap.reset_cache()
    budget.reset_cache()


@pytest.fixture
def cap_reached(monkeypatch):
    monkeypatch.setattr(settings, "usage_hard_cap_daily_usd", 5.0)
    monkeypatch.setattr(spend_cap, "spent_last_24h", lambda now=None: Decimal("5.01"))


def _row(when: datetime, cost: str | None, tokens: int = 0) -> None:
    with workspace_connection() as session:
        session.add(
            WorkspaceLlmUsage(
                id=uuid.uuid4().hex,
                tenant_id=get_current_tenant_id(),
                user_id="qualcuno",
                operation_kind="kg_ingest",
                operation_id=uuid.uuid4().hex,
                task="entity_resolution",
                model="gpt-test",
                input_tokens=tokens,
                output_tokens=0,
                reasoning_tokens=0,
                cached_input_tokens=0,
                outcome="ok",
                duration_ms=1,
                attempt=1,
                cost_estimate=cost,
                created_at=when.isoformat(),
            )
        )


class TestLaSpesaDelleUltime24Ore:
    def test_conta_le_righe_di_tutti_e_le_senza_prezzo_al_ripiego(self, monkeypatch):
        monkeypatch.setattr(settings, "usage_unpriced_usd_per_million_tokens", 10.0)
        now = datetime.now(UTC)
        before = spend_cap.spent_last_24h(now)
        _row(now - timedelta(hours=1), "0.30")
        _row(now - timedelta(hours=2), None, tokens=100_000)  # $1 al ripiego
        _row(now - timedelta(hours=30), "50.00")  # fuori dalla finestra
        assert spend_cap.spent_last_24h(now) - before == Decimal("1.30")


class TestIlFreno:
    def test_spento_non_ferma_niente(self, monkeypatch):
        monkeypatch.setattr(settings, "usage_hard_cap_daily_usd", 0.0)
        monkeypatch.setattr(spend_cap, "spent_last_24h", lambda now=None: Decimal("1000"))
        assert not spend_cap.tripped()
        spend_cap.check()

    def test_sotto_il_tetto_passa(self, monkeypatch):
        monkeypatch.setattr(settings, "usage_hard_cap_daily_usd", 5.0)
        monkeypatch.setattr(spend_cap, "spent_last_24h", lambda now=None: Decimal("4.99"))
        assert not spend_cap.tripped()

    def test_e_una_chiave_mancante_per_chi_sa_ripiegare(self, cap_reached):
        with pytest.raises(MissingProviderKey):
            spend_cap.check()

    def test_il_gateway_rifiuta_e_lo_scrive(self, cap_reached, monkeypatch):
        written: list[dict] = []
        monkeypatch.setattr("backend.llm.gateway.record", lambda **kw: written.append(kw))
        monkeypatch.setattr(settings, "openai_api_key", "sk-test-non-usata")
        with operation(OperationKind.PLAN_SYNTHESIS), pytest.raises(spend_cap.SpendCapReached):
            run(task=LlmTask.RETRIEVAL_RERANK, messages=[])
        assert written[-1]["outcome"] == "refused"
        assert written[-1]["error_kind"] == "SpendCapReached"

    def test_mem0_rifiuta_e_lo_scrive(self, cap_reached, monkeypatch):
        from backend.llm import mem0_meter

        written: list[dict] = []
        monkeypatch.setattr(mem0_meter, "record", lambda **kw: written.append(kw))
        called: list[bool] = []
        metered = mem0_meter._wrap(lambda **kw: called.append(True), LlmTask.MEMORY_EXTRACTION)
        with operation(OperationKind.PLAN_SYNTHESIS), pytest.raises(spend_cap.SpendCapReached):
            metered(model="gpt-test")
        assert called == []
        assert written[-1]["outcome"] == "refused"

    def test_il_consulente_riceve_il_429_anche_con_i_limiti_spenti(self, cap_reached, monkeypatch):
        monkeypatch.setattr(settings, "usage_limits_enabled", False)
        with pytest.raises(budget.UsageLimitReached) as caught:
            budget.check("consulente")
        assert caught.value.window == "installation"
        with pytest.raises(budget.UsageLimitReached):
            budget.check_audio("consulente")


class TestLeCodeSiFermano:
    def test_a_tetto_raggiunto_la_coda_non_prende_lavori_e_poi_riparte(self, monkeypatch):
        from backend.workers import supervisor

        monkeypatch.setattr(supervisor, "_CAP_PAUSE_SECONDS", 0.01)
        state = {"tripped": True, "drained": 0}
        monkeypatch.setattr(spend_cap, "tripped", lambda: state["tripped"])

        def drain() -> int:
            state["drained"] += 1
            return 0

        async def scenario() -> None:
            task = asyncio.create_task(
                supervisor._drain_loop("t", drain, lambda: {"pending": 0, "stuck": 0}, 0.01)
            )
            await asyncio.sleep(0.1)
            assert state["drained"] == 0  # in pausa: nessuna passata
            state["tripped"] = False
            deadline = asyncio.get_running_loop().time() + 5
            while state["drained"] == 0 and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(scenario())
        assert state["drained"] > 0

    def test_un_worker_a_se_aspetta_invece_di_fallire(self, monkeypatch):
        calls = iter([True, True, False])
        monkeypatch.setattr(spend_cap, "tripped", lambda: next(calls))
        spend_cap.pause_while_tripped("t", poll_seconds=0)


class TestDallaReview:
    def test_mem0_restituisce_la_risposta_con_il_freno_spento(self, monkeypatch):
        """Il `return` era finito dopo un `raise`: ogni chiamata di Mem0 tornava None."""
        from backend.llm import mem0_meter

        monkeypatch.setattr(settings, "usage_hard_cap_daily_usd", 0.0)
        monkeypatch.setattr(mem0_meter, "record", lambda **kw: None)
        metered = mem0_meter._wrap(lambda **kw: "risposta", LlmTask.MEMORY_EXTRACTION)
        with operation(OperationKind.PLAN_SYNTHESIS):
            assert metered(model="gpt-test") == "risposta"

    def test_un_registro_che_non_risponde_non_ferma_le_code(self, monkeypatch):
        monkeypatch.setattr(settings, "usage_hard_cap_daily_usd", 5.0)

        def broken(now=None):
            raise RuntimeError("database giu'")

        monkeypatch.setattr(spend_cap, "spent_last_24h", broken)
        assert spend_cap.tripped() is False

    def test_un_registro_che_non_risponde_tiene_l_ultima_lettura(self, monkeypatch):
        monkeypatch.setattr(settings, "usage_hard_cap_daily_usd", 5.0)
        monkeypatch.setattr(spend_cap, "spent_last_24h", lambda now=None: Decimal("9"))
        assert spend_cap.tripped()
        monkeypatch.setattr(spend_cap, "_CACHE_SECONDS", -1.0)

        def broken(now=None):
            raise RuntimeError("database giu'")

        monkeypatch.setattr(spend_cap, "spent_last_24h", broken)
        assert spend_cap.tripped()

    def test_per_le_code_il_freno_e_credito_finito(self):
        """`exhausted`: non consuma tentativi e mette in pausa la coda."""
        from backend.workers import retry

        failure = retry.classify(spend_cap.SpendCapReached(spend_cap.MESSAGE), attempts=4)
        assert failure.kind == "exhausted"
