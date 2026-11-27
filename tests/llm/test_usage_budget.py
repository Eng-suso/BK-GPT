"""Il limite d'uso della prova: sessione di cinque ore, settimana, prova.

La spesa si legge dal registro dei consumi; qui si scrivono righe finte con un
costo noto e si guarda cosa dice il contatore.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.llm import OperationKind, budget, operation
from backend.security import get_current_tenant_id
from backend.settings import settings
from backend.workspace_storage import WorkspaceLlmUsage, WorkspaceUsagePlan, workspace_connection


@pytest.fixture()
def limits(monkeypatch):
    monkeypatch.setattr(settings, "usage_limits_enabled", True)
    monkeypatch.setattr(settings, "usage_session_hours", 5.0)
    monkeypatch.setattr(settings, "usage_session_budget_usd", 1.0)
    monkeypatch.setattr(settings, "usage_week_budget_usd", 4.0)
    monkeypatch.setattr(settings, "usage_trial_budget_usd", 10.0)
    monkeypatch.setattr(settings, "usage_trial_days", 14)
    monkeypatch.setattr(settings, "usage_unpriced_usd_per_million_tokens", 10.0)
    budget.reset_cache()
    yield
    budget.reset_cache()


@pytest.fixture()
def user() -> str:
    return f"consulente-{uuid.uuid4().hex[:10]}"


def _spend(user_id: str, when: datetime, cost: str | None, tokens: int = 0) -> None:
    with workspace_connection() as session:
        session.add(
            WorkspaceLlmUsage(
                id=uuid.uuid4().hex,
                tenant_id=get_current_tenant_id(),
                user_id=user_id,
                operation_kind="chat_turn",
                operation_id=uuid.uuid4().hex,
                task="chat_turn",
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


def _start_trial(user_id: str, started: datetime, session_started: datetime | None = None) -> None:
    with workspace_connection() as session:
        session.add(
            WorkspaceUsagePlan(
                user_id=user_id,
                tenant_id=get_current_tenant_id(),
                trial_started_at=started.isoformat(),
                session_started_at=session_started.isoformat() if session_started else None,
                updated_at=started.isoformat(),
            )
        )


NOW = datetime.now(UTC).replace(microsecond=0)


class TestSessione:
    def test_guardare_il_pannello_non_fa_partire_la_sessione(self, limits, user):
        current = budget.status(user, now=NOW)

        assert current.session.started_at is None
        assert current.session.resets_at is None
        assert current.session.used_usd == 0

    def test_la_sessione_parte_dalla_prima_richiesta_e_dura_cinque_ore(self, limits, user):
        budget.check(user)

        current = budget.status(user)
        assert current.session.started_at is not None
        assert current.session.resets_at - current.session.started_at == timedelta(hours=5)

    def test_conta_solo_la_spesa_dentro_la_sessione(self, limits, user):
        _start_trial(user, NOW - timedelta(days=1), session_started=NOW - timedelta(hours=1))
        _spend(user, NOW - timedelta(hours=3), "0.5000")  # prima della sessione
        _spend(user, NOW - timedelta(minutes=30), "0.2500")

        current = budget.status(user, now=NOW)

        assert current.session.used_usd == Decimal("0.2500")
        assert current.session.used_share == 0.25
        assert current.week.used_usd == Decimal("0.7500")

    def test_una_sessione_scaduta_si_chiude_e_la_prossima_richiesta_ne_apre_una(self, limits, user):
        _start_trial(user, NOW - timedelta(days=1), session_started=NOW - timedelta(hours=6))
        _spend(user, NOW - timedelta(hours=5, minutes=30), "0.9000")

        assert budget.status(user, now=NOW).session.started_at is None
        budget.check(user)
        assert budget.status(user).session.used_usd == 0


class TestBlocco:
    def test_la_sessione_esaurita_ferma_la_richiesta_nuova(self, limits, user):
        _start_trial(user, NOW - timedelta(days=1), session_started=NOW - timedelta(hours=1))
        _spend(user, NOW - timedelta(minutes=10), "1.0000")

        with pytest.raises(budget.UsageLimitReached) as exc:
            budget.check(user)

        assert exc.value.window == "session"
        assert "sessione" in str(exc.value)

    def test_la_settimana_esaurita_ferma_anche_con_la_sessione_libera(self, limits, user):
        _start_trial(user, NOW - timedelta(days=2))
        for hours in (40, 30, 20, 10):
            _spend(user, NOW - timedelta(hours=hours), "1.0000")

        with pytest.raises(budget.UsageLimitReached) as exc:
            budget.check(user)

        assert exc.value.window == "week"

    def test_la_settimana_si_rinnova_a_blocchi_dall_inizio_della_prova(self, limits, user):
        _start_trial(user, NOW - timedelta(days=8))
        _spend(user, NOW - timedelta(days=7, hours=12), "4.0000")  # settimana scorsa

        current = budget.status(user, now=NOW)

        assert current.week.used_usd == 0
        assert current.week.started_at == NOW - timedelta(days=1)
        assert current.blocking is None

    def test_la_prova_finita_ferma_tutto(self, limits, user):
        _start_trial(user, NOW - timedelta(days=15))

        with pytest.raises(budget.UsageLimitReached) as exc:
            budget.check(user)

        assert exc.value.window == "trial_over"
        assert "prova" in str(exc.value)

    def test_le_righe_senza_prezzo_si_contano_al_prezzo_di_ripiego(self, limits, user):
        _start_trial(user, NOW - timedelta(days=1), session_started=NOW - timedelta(hours=1))
        _spend(user, NOW - timedelta(minutes=5), None, tokens=100_000)

        # 100.000 token a 10 $ per milione = 1 $: la sessione e' piena.
        assert budget.status(user, now=NOW).session.exhausted

    def test_spento_non_ferma_niente(self, limits, user, monkeypatch):
        monkeypatch.setattr(settings, "usage_limits_enabled", False)
        _start_trial(user, NOW - timedelta(days=15))

        budget.check(user)  # nessuna eccezione


class TestCosaSiFerma:
    """Il limite si guarda al confine (rotta, inizio del turno), mai dentro il gateway."""

    def test_il_gateway_non_ferma_un_lavoro_gia_accettato(self, limits, user, monkeypatch):
        from backend.llm import gateway

        _start_trial(user, NOW - timedelta(days=15))
        monkeypatch.setattr(settings, "openai_api_key", "sk-test-non-usata")

        class _Client:
            def stream(self, *_args, **_kwargs):
                yield type("M", (), {"content": "ok", "usage_metadata": None})()

        monkeypatch.setattr(gateway, "_client", lambda *_a, **_k: _Client())
        monkeypatch.setattr(gateway, "record", lambda **_k: None)

        with operation(OperationKind.SIMULATION_NARRATIVE, user_id=user):
            assert gateway.run(task=gateway.LlmTask.SIMULATION_NARRATIVE, messages=[]) is not None

    def test_la_dipendenza_della_rotta_ferma_prima_del_servizio(self, limits, user, monkeypatch):
        from backend.app import app
        from backend.simulation import whatif

        monkeypatch.setattr(settings, "delir_auth_enabled", False)
        _start_trial(user, NOW - timedelta(days=15))
        called = []
        monkeypatch.setattr(whatif, "translate", lambda *a, **k: called.append(a))

        response = TestClient(app).post(
            "/v1/workspace/bpmn-models/qualunque/simulation-what-if",
            headers={"X-DeliR-User-ID": user},
            json={"text": "e se raddoppiassi gli arrivi?"},
        )

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "usage_limit_reached"
        assert called == []


class TestPrevisione:
    def test_un_ritmo_che_esaurisce_prima_del_rinnovo_si_dice(self, limits, user):
        _start_trial(user, NOW - timedelta(days=1), session_started=NOW - timedelta(hours=1))
        _spend(user, NOW - timedelta(minutes=30), "0.5000")

        forecast = budget.status(user, now=NOW).forecast

        # Mezzo dollaro in un'ora: l'altro mezzo finisce fra un'ora, prima delle 5.
        assert forecast is not None and forecast.window == "session"
        assert abs((forecast.exhausts_at - (NOW + timedelta(hours=1))).total_seconds()) < 5

    def test_un_ritmo_tranquillo_non_allarma(self, limits, user):
        _start_trial(user, NOW - timedelta(days=1), session_started=NOW - timedelta(hours=4))
        _spend(user, NOW - timedelta(hours=3), "0.3000")

        assert budget.status(user, now=NOW).forecast is None


class TestRotte:
    @pytest.fixture()
    def client(self, monkeypatch):
        monkeypatch.setattr(settings, "delir_auth_enabled", False)
        from backend.app import app

        return TestClient(app)

    def test_il_consulente_vede_quote_e_orari_non_dollari(self, limits, user, client):
        _start_trial(user, NOW - timedelta(days=1), session_started=NOW - timedelta(hours=1))
        _spend(user, NOW - timedelta(minutes=10), "0.5000")

        body = client.get("/v1/usage/me", headers={"X-DeliR-User-ID": user}).json()

        assert body["enabled"] is True
        assert body["session"]["used_share"] == 0.5
        assert body["session"]["resets_at"]
        assert "used_usd" not in body["session"]
        assert body["blocking"] is None

    def test_l_amministratore_ripristina_la_sessione(self, limits, user, client):
        _start_trial(user, NOW - timedelta(days=1), session_started=NOW - timedelta(hours=1))
        _spend(user, NOW - timedelta(minutes=10), "1.0000")

        body = client.put(f"/v1/usage/plans/{user}", json={"reset_session": True}).json()

        assert body["session"]["used_share"] == 0
        assert body["blocking"] is None
        assert body["week"]["used_usd"] == "1.0000"

    def test_l_amministratore_alza_il_budget_di_un_consulente(self, limits, user, client):
        body = client.put(f"/v1/usage/plans/{user}", json={"week_budget_usd": "12.5"}).json()

        assert body["week"]["limit_usd"] == "12.5"

    def test_un_azione_bloccata_risponde_429_con_il_messaggio(self, limits, user):
        from fastapi import FastAPI

        from backend.api.errors import setup_api_error_handlers

        _start_trial(user, NOW - timedelta(days=15))
        app = FastAPI()
        setup_api_error_handlers(app)

        @app.get("/bloccata")
        def bloccata() -> None:
            budget.check(user)

        response = TestClient(app).get("/bloccata")

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "usage_limit_reached"
        assert "prova" in response.json()["error"]["message"]


class TestTurnoDiChat:
    @pytest.fixture(autouse=True)
    def consulente_ripristinato(self):
        from backend import security

        token = security.set_current_user_id(None)
        yield
        security._user_id.reset(token)

    def test_un_turno_oltre_il_limite_non_parte_e_lo_dice(self, limits, user):
        from backend.schemas.api import TraceContext
        from backend.security import set_current_user_id
        from backend.services.agent_runtime import usage_limit_error

        _start_trial(user, NOW - timedelta(days=15))
        set_current_user_id(user)
        context = TraceContext(request_id="r", trace_id="t")

        error = usage_limit_error(context)

        assert error is not None
        assert error.code == "usage_limit_reached"
        assert error.retryable is False

    def test_un_turno_sotto_il_limite_parte(self, limits, user):
        from backend.schemas.api import TraceContext
        from backend.security import set_current_user_id
        from backend.services.agent_runtime import usage_limit_error

        set_current_user_id(user)

        assert usage_limit_error(TraceContext(request_id="r", trace_id="t")) is None


class TestDallaReview:
    def test_guardare_il_pannello_non_crea_il_piano_ne_fa_partire_la_prova(self, limits, user):
        from sqlalchemy import select

        budget.status(user)
        budget.status(user)

        with workspace_connection() as session:
            rows = session.scalars(select(WorkspaceUsagePlan).where(WorkspaceUsagePlan.user_id == user)).all()
        assert rows == []

    def test_con_piu_finestre_esaurite_vince_quella_che_si_ripristina_per_ultima(self, limits, user):
        _start_trial(user, NOW - timedelta(days=2), session_started=NOW - timedelta(hours=1))
        _spend(user, NOW - timedelta(minutes=10), "4.0000")  # sessione e settimana insieme

        current = budget.status(user, now=NOW)

        assert current.session.exhausted and current.week.exhausted
        assert current.blocking.name == "week"

    def test_zero_vuol_dire_nessun_tetto_per_ogni_finestra(self, limits, user, monkeypatch):
        monkeypatch.setattr(settings, "usage_week_budget_usd", 0.0)
        monkeypatch.setattr(settings, "usage_session_budget_usd", 0.0)
        _start_trial(user, NOW - timedelta(days=1), session_started=NOW - timedelta(hours=1))
        _spend(user, NOW - timedelta(minutes=10), "3.0000")

        current = budget.status(user, now=NOW)

        assert current.week.limit_usd is None and current.session.limit_usd is None
        assert current.blocking is None

    def test_lo_stesso_id_in_un_altro_tenant_e_un_altra_persona(self, limits, user):
        _start_trial(user, NOW - timedelta(days=1), session_started=NOW - timedelta(hours=1))
        _spend(user, NOW - timedelta(minutes=10), "1.0000")

        other = budget.status(user, tenant_id="altro-tenant", now=NOW)

        assert other.week.used_usd == 0

    def test_due_primi_controlli_insieme_non_si_scontrano(self, limits, user):
        from concurrent.futures import ThreadPoolExecutor

        from backend.security import set_current_tenant_id

        tenant = get_current_tenant_id()

        def first_check(_):
            set_current_tenant_id(tenant)
            budget.reset_cache()
            budget.check(user)

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(first_check, range(4)))

    def test_una_data_senza_fuso_e_utc(self, limits, user):
        budget.update_plan(user, trial_ends_at=datetime(2026, 12, 10, 0, 0))

        with workspace_connection() as session:
            plan = session.get(WorkspaceUsagePlan, (get_current_tenant_id(), user))
        assert plan.trial_ends_at == "2026-12-10T00:00:00+00:00"

    def test_il_pannello_dice_la_durata_della_sessione(self, limits, user, monkeypatch):
        monkeypatch.setattr(settings, "delir_auth_enabled", False)
        monkeypatch.setattr(settings, "usage_session_hours", 3.0)
        from backend.app import app

        body = TestClient(app).get("/v1/usage/me", headers={"X-DeliR-User-ID": user}).json()

        assert body["session_hours"] == 3.0


class TestIlMessaggioArrivaAlConsulente:
    def test_la_chat_non_in_streaming_risponde_429_non_502(self, limits, user, monkeypatch):
        from backend.app import app
        from backend.services import agent_runtime

        monkeypatch.setattr(settings, "delir_auth_enabled", False)
        monkeypatch.setattr(settings, "delir_fake_llm", False)
        _start_trial(user, NOW - timedelta(days=15))
        monkeypatch.setattr(agent_runtime, "get_agent", lambda *_a, **_k: None)

        response = TestClient(app).post(
            "/chat",
            headers={"X-DeliR-User-ID": user},
            json={"thread_id": f"t-{user}", "messages": [{"role": "user", "content": "ciao"}]},
        )

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "usage_limit_reached"


def _listen(user_id: str, when: datetime, seconds: int, task: str = "live_transcription") -> None:
    with workspace_connection() as session:
        session.add(
            WorkspaceLlmUsage(
                id=uuid.uuid4().hex,
                tenant_id=get_current_tenant_id(),
                user_id=user_id,
                operation_kind="transcription",
                operation_id=uuid.uuid4().hex,
                task=task,
                model="gpt-realtime-whisper",
                input_tokens=0,
                output_tokens=0,
                reasoning_tokens=0,
                cached_input_tokens=0,
                audio_seconds=seconds,
                outcome="ok",
                duration_ms=1,
                attempt=1,
                cost_estimate="0.5000",
                created_at=when.isoformat(),
            )
        )


class TestAudioInOre:
    """L'audio ha un tetto in ore, separato dai dollari dei modelli."""

    @pytest.fixture(autouse=True)
    def ore(self, monkeypatch):
        monkeypatch.setattr(settings, "usage_week_audio_hours", 2.0)
        monkeypatch.setattr(settings, "usage_trial_audio_hours", 3.0)

    def test_l_audio_si_conta_in_secondi_e_non_entra_nei_dollari(self, limits, user):
        _start_trial(user, NOW - timedelta(days=1), session_started=NOW - timedelta(hours=1))
        _listen(user, NOW - timedelta(minutes=30), 3_600)
        _listen(user, NOW - timedelta(minutes=20), 1_800, task="transcription")

        current = budget.status(user, now=NOW)

        assert current.audio_week.used_seconds == 5_400
        assert current.audio_week.limit_seconds == 7_200
        assert current.session.used_usd == 0  # il costo dell'audio non tocca la sessione

    def test_ore_finite_fermano_le_registrazioni_non_la_chat(self, limits, user):
        _start_trial(user, NOW - timedelta(days=1))
        _listen(user, NOW - timedelta(hours=2), 7_200)

        budget.check(user)  # la chat passa
        with pytest.raises(budget.UsageLimitReached) as exc:
            budget.check_audio(user)

        assert exc.value.window == "audio_week"
        assert "registrazione" in str(exc.value)

    def test_le_ore_della_settimana_si_rinnovano(self, limits, user):
        _start_trial(user, NOW - timedelta(days=8))
        _listen(user, NOW - timedelta(days=7, hours=12), 7_200)  # settimana scorsa

        current = budget.status(user, now=NOW)

        assert current.audio_week.used_seconds == 0
        assert current.audio_trial.used_seconds == 7_200
        assert current.audio_blocking is None

    def test_zero_ore_vuol_dire_nessun_tetto(self, limits, user):
        budget.update_plan(user, week_audio_hours=Decimal(0), trial_audio_hours=Decimal(0))
        _listen(user, NOW - timedelta(minutes=5), 99_999)

        current = budget.status(user)

        assert current.audio_week.limit_seconds is None
        assert current.audio_blocking is None

    def test_il_pannello_riceve_le_ore(self, limits, user, monkeypatch):
        from backend.app import app

        monkeypatch.setattr(settings, "delir_auth_enabled", False)
        _start_trial(user, NOW - timedelta(days=1))
        _listen(user, NOW - timedelta(minutes=10), 1_800)

        body = TestClient(app).get("/v1/usage/me", headers={"X-DeliR-User-ID": user}).json()

        assert body["audio"]["week"]["used_seconds"] == 1_800
        assert body["audio"]["week"]["limit_seconds"] == 7_200
        assert body["audio"]["blocking"] is None

    def test_la_trascrizione_di_un_file_risponde_429_a_ore_finite(self, limits, user, monkeypatch):
        from backend.app import app

        monkeypatch.setattr(settings, "delir_auth_enabled", False)
        _start_trial(user, NOW - timedelta(days=1))
        _listen(user, NOW - timedelta(hours=1), 7_200)

        response = TestClient(app).post(
            "/v1/audio/transcriptions",
            headers={"X-DeliR-User-ID": user},
            files={"file": ("a.wav", b"RIFF0000", "audio/wav")},
        )

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "usage_limit_reached"


class TestMisuraDellAudio:
    def test_il_contatore_dal_vivo_conta_i_byte_mandati(self):
        import base64

        from backend.api.routes.audio import LiveAudioMeter

        meter = LiveAudioMeter()
        one_second = base64.b64encode(b"\x00" * 48_000).decode()
        for _ in range(90):
            meter.add(one_second)

        assert meter.seconds == 90

    def test_una_registrazione_lascia_la_sua_riga_con_i_secondi(self, user):
        from sqlalchemy import select

        from backend.api.routes.audio import record_live_session
        from backend.security import AuthPrincipal

        record_live_session(AuthPrincipal(user_id=user, tenant_id=get_current_tenant_id()), 754)

        with workspace_connection() as session:
            row = session.scalars(
                select(WorkspaceLlmUsage).where(WorkspaceLlmUsage.user_id == user)
            ).one()
        assert (row.task, row.audio_seconds) == ("live_transcription", 754)

    def test_la_durata_di_un_file_viene_dalla_risposta(self):
        from backend.llm.usage import extract_audio_seconds

        assert extract_audio_seconds({"duration": 61.6}) == 62
        assert extract_audio_seconds(type("R", (), {"duration": 30})()) == 30
        assert extract_audio_seconds({}) == 0
        assert extract_audio_seconds({"duration": True}) == 0

    def test_il_prezzo_al_minuto(self, monkeypatch):
        from backend.llm.prices import estimate_cost

        monkeypatch.setattr(settings, "llm_prices_json", '{"gpt-realtime-whisper": {"per_minute": 0.017}}')

        assert estimate_cost("gpt-realtime-whisper", input_tokens=0, output_tokens=0, audio_seconds=600) == Decimal("0.17")
