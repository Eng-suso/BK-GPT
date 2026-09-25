"""P1 — leggere il registro: «dove sono andati i soldi ieri» e' una query.

Il gateway scrive, e altri test verificano che scriva. Qui si verifica l'altra
meta', quella che fino al 25/09 non esisteva: che quelle righe si possano
interrogare, e che le risposte dicano la verita' anche quando la verita' e'
«questo totale e' parziale».

Le righe si inseriscono a mano invece di passare da `record()`, per due motivi:
`created_at` deve essere fissato (altrimenti le finestre temporali non sono
testabili) e ogni test vive nel suo `tenant_id`, perche' il registro e' un tavolo
condiviso e le righe restano.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from backend.llm import ledger
from backend.workspace_storage import (
    WorkspaceBpmnReviewVersion,
    WorkspaceLlmUsage,
    workspace_connection,
)

IERI = "2026-09-20T12:00:00+00:00"
OGGI = "2026-09-21T12:00:00+00:00"
DOMANI = "2026-09-22T12:00:00+00:00"
# Una finestra chiusa attorno ai due giorni finti, cosi' i test non dipendono da
# quando girano: `giorni=N` guarda indietro da adesso, e "adesso" cambia.
DA, A = "2026-09-20T00:00:00+00:00", "2026-09-22T00:00:00+00:00"


@pytest.fixture()
def tenant() -> str:
    """Un tenant tutto per questo test. Le righe non si cancellano: si isolano."""
    return f"test-ledger-{uuid.uuid4().hex[:12]}"


def _riga(
    tenant: str,
    *,
    task: str = "plan_extraction",
    model: str = "gpt-prezzato",
    operation_kind: str = "plan_synthesis",
    outcome: str = "ok",
    input_tokens: int = 100,
    output_tokens: int = 20,
    reasoning_tokens: int = 0,
    cached_input_tokens: int = 0,
    cost_estimate: str | None = "0.0100",
    attempt: int = 1,
    reasoning_effort: str | None = "medium",
    project_id: str | None = "proj",
    process_id: str | None = "proc",
    created_at: str = OGGI,
) -> WorkspaceLlmUsage:
    return WorkspaceLlmUsage(
        id=uuid.uuid4().hex,
        tenant_id=tenant,
        operation_kind=operation_kind,
        operation_id=uuid.uuid4().hex,
        parent_operation_id=None,
        project_id=project_id,
        process_id=process_id,
        task=task,
        model=model,
        prompt_version=None,
        reasoning_effort=reasoning_effort,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cached_input_tokens=cached_input_tokens,
        outcome=outcome,
        error_kind=None,
        duration_ms=10,
        attempt=attempt,
        cost_estimate=cost_estimate,
        created_at=created_at,
    )


def _scrivi(*righe) -> None:
    with workspace_connection() as session:
        for riga in righe:
            session.add(riga)


class TestIlTotaleNonMenteSullaSuaCopertura:
    """La regola d'onesta' del modulo: un costo parziale non si spaccia per tutto."""

    def test_somma_token_costo_ed_esiti(self, tenant):
        _scrivi(
            _riga(tenant, input_tokens=100, output_tokens=20, cost_estimate="0.0100"),
            _riga(tenant, input_tokens=50, output_tokens=10, cost_estimate="0.0050"),
            _riga(tenant, outcome="timeout", input_tokens=30, output_tokens=0, cost_estimate="0.0030"),
        )

        t = ledger.totale(since=DA, until=A, tenant_id=tenant)

        assert t.righe == 3
        assert t.chiamate == 3
        assert t.fallite == 1
        assert (t.input, t.output) == (180, 30)
        assert t.costo_noto == Decimal("0.0180")

    def test_una_riga_senza_prezzo_si_vede_nella_copertura(self, tenant):
        """Il caso della trascrizione al minuto: token contati, costo ignoto."""
        _scrivi(
            _riga(tenant, input_tokens=100, output_tokens=0, cost_estimate="0.0100"),
            _riga(tenant, model="whisper-1", input_tokens=900, output_tokens=0, cost_estimate=None),
        )

        t = ledger.totale(since=DA, until=A, tenant_id=tenant)

        assert t.costo_noto == Decimal("0.0100")
        assert t.righe_senza_prezzo == 1
        assert t.token_senza_prezzo == 900
        # 100 token su 1000 hanno un prezzo: chi legge deve sapere che sta
        # guardando il 10% del volume, non un totale.
        assert t.copertura_prezzo == pytest.approx(0.1)

    def test_senza_token_la_copertura_non_si_inventa(self, tenant):
        """Una fetta di soli colpi di cache non ha una copertura da dichiarare."""
        _scrivi(_riga(tenant, outcome="cache_hit", input_tokens=0, output_tokens=0, cost_estimate=None))

        t = ledger.totale(since=DA, until=A, tenant_id=tenant)

        assert t.copertura_prezzo is None
        assert t.evitate == 1
        assert t.chiamate == 0
        # Una chiamata evitata non e' una riga «senza prezzo»: non e' spesa che
        # non sappiamo valorizzare, e' spesa che non c'e' stata.
        assert t.righe_senza_prezzo == 0

    def test_un_rifiuto_non_sporca_la_copertura(self, tenant):
        _scrivi(_riga(tenant, outcome="refused", input_tokens=0, output_tokens=0, cost_estimate=None))

        t = ledger.totale(since=DA, until=A, tenant_id=tenant)

        assert t.chiamate == 0
        assert t.righe_senza_prezzo == 0

    def test_un_costo_storto_non_fa_cadere_la_lettura(self, tenant):
        """Un valore illeggibile e' un difetto nostro, non un motivo per non rispondere."""
        _scrivi(
            _riga(tenant, cost_estimate="non-un-numero", input_tokens=10, output_tokens=5),
            _riga(tenant, cost_estimate="0.0100"),
        )

        t = ledger.totale(since=DA, until=A, tenant_id=tenant)

        assert t.costo_noto == Decimal("0.0100")
        assert t.righe_senza_prezzo == 1
        assert t.token_senza_prezzo == 15


class TestLaFinestraTemporale:
    def test_le_righe_fuori_finestra_non_entrano(self, tenant):
        _scrivi(
            _riga(tenant, created_at=IERI, cost_estimate="0.0100"),
            _riga(tenant, created_at=DOMANI, cost_estimate="9.9999"),
        )

        t = ledger.totale(since=DA, until=A, tenant_id=tenant)

        assert t.righe == 1
        assert t.costo_noto == Decimal("0.0100")

    def test_per_giorno_separa_i_giorni(self, tenant):
        _scrivi(
            _riga(tenant, created_at=IERI, cost_estimate="0.0100"),
            _riga(tenant, created_at=OGGI, cost_estimate="0.0200"),
            _riga(tenant, created_at=OGGI, cost_estimate="0.0300"),
        )

        with workspace_connection() as session:
            righe = session.query(WorkspaceLlmUsage).filter_by(tenant_id=tenant).count()
        assert righe == 3

        voci = {v.chiave: v.totale for v in ledger.per_giorno(giorni=3650, tenant_id=tenant)}

        assert voci["2026-09-20"].costo_noto == Decimal("0.0100")
        assert voci["2026-09-21"].costo_noto == Decimal("0.0500")


class TestIRaggruppamenti:
    def test_per_compito_ordina_dal_piu_caro(self, tenant):
        _scrivi(
            _riga(tenant, task="plan_extraction", cost_estimate="0.0100"),
            _riga(tenant, task="quality_judgement", cost_estimate="0.5000"),
            _riga(tenant, task="rerank", cost_estimate="0.0001"),
        )

        voci = ledger.per("task", since=DA, until=A, tenant_id=tenant)

        assert [v.chiave for v in voci] == ["quality_judgement", "plan_extraction", "rerank"]

    def test_la_spesa_senza_progetto_ha_un_nome(self, tenant):
        """`NULL` e' una risposta: e' chi non sta attribuendo il proprio lavoro."""
        _scrivi(
            _riga(tenant, project_id=None, cost_estimate="0.0100"),
            _riga(tenant, project_id="proj-a", cost_estimate="0.0200"),
        )

        voci = {v.chiave: v.totale for v in ledger.per("project_id", since=DA, until=A, tenant_id=tenant)}

        assert voci["(nessuno)"].costo_noto == Decimal("0.0100")
        assert voci["proj-a"].costo_noto == Decimal("0.0200")

    def test_una_dimensione_inventata_e_un_errore(self, tenant):
        """Meglio un errore che un raggruppamento silenziosamente sbagliato."""
        with pytest.raises(KeyError):
            ledger.per("colore_preferito", since=DA, until=A, tenant_id=tenant)


class TestQuantoCostanoIRetry:
    def test_conta_solo_i_tentativi_oltre_il_primo(self, tenant):
        _scrivi(
            _riga(tenant, attempt=1, cost_estimate="0.0100", input_tokens=100, output_tokens=0),
            _riga(tenant, attempt=2, cost_estimate="0.0100", input_tokens=100, output_tokens=0),
            _riga(tenant, attempt=3, cost_estimate="0.0100", input_tokens=100, output_tokens=0),
        )

        r = ledger.costo_dei_retry(since=DA, until=A, tenant_id=tenant)

        assert r.primi_tentativi == 1
        assert r.ritentativi == 2
        assert r.costo_ritentativi == Decimal("0.0200")
        assert r.token_ritentativi == 200


class TestQuantoRagionamentoPaghiamo:
    def test_la_quota_e_sul_totale_di_uscita(self, tenant):
        """`reasoning` e' un sottoinsieme di `output`, non un addendo."""
        _scrivi(
            _riga(tenant, task="quality_judgement", output_tokens=100, reasoning_tokens=60),
            _riga(tenant, task="quality_judgement", output_tokens=100, reasoning_tokens=40),
        )

        pesi = [p for p in ledger.peso_del_ragionamento(since=DA, until=A, tenant_id=tenant)]

        assert len(pesi) == 1
        assert pesi[0].output_tokens == 200
        assert pesi[0].reasoning_tokens == 100
        assert pesi[0].quota == pytest.approx(0.5)

    def test_senza_uscita_non_si_divide_per_zero(self, tenant):
        _scrivi(_riga(tenant, task="rerank", output_tokens=0, reasoning_tokens=0))

        pesi = ledger.peso_del_ragionamento(since=DA, until=A, tenant_id=tenant)

        assert pesi[0].quota is None


def _validazione(tenant: str, *, process_id: str, quando: str, versione: int = 1) -> WorkspaceBpmnReviewVersion:
    """Una validazione, con id unici per esecuzione.

    `uq_bpmn_review_version` e' su `(bpmn_model_id, version)` e **non** include
    il tenant: isolarsi per tenant basta per il registro dei consumi ma non per
    questa tabella, e senza id unici il secondo giro di questi test sbatte su
    una riga lasciata dal primo.
    """
    return WorkspaceBpmnReviewVersion(
        tenant_id=tenant,
        bpmn_model_id=f"model-{tenant}-{process_id}",
        process_id=process_id,
        version=versione,
        source_text="intervista",
        bpmn_brief="brief",
        readiness_score=80,
        missing_information_json="[]",
        status="approved",
        change_summary="Piano approvato: canvas generato",
        source="approval",
        created_at=quando,
    )


class TestIlKpiCostoPerAsIsValidato:
    """Il KPI di punta del piano. Il doc lo dava per «da verificare che esista»:
    l'evento c'e' gia', e' l'approvazione di una review."""

    def test_la_spesa_di_un_processo_fino_alla_sua_validazione(self, tenant):
        _scrivi(
            _riga(tenant, process_id=f"{tenant}-p1", created_at=IERI, cost_estimate="0.1000"),
            _riga(tenant, process_id=f"{tenant}-p1", created_at=OGGI, cost_estimate="0.2000"),
        )
        with workspace_connection() as session:
            session.add(_validazione(tenant, process_id=f"{tenant}-p1", quando=DOMANI))

        k = ledger.costo_per_as_is_validato(since=DA, until="2026-09-23T00:00:00+00:00", tenant_id=tenant)

        assert k.validazioni == 1
        assert k.costo_noto == Decimal("0.3000")
        assert k.costo_medio == Decimal("0.3000")

    def test_la_spesa_dopo_l_approvazione_e_manutenzione_e_non_conta(self, tenant):
        """Altrimenti il costo di produrre un AS-IS crescerebbe ogni volta che si
        torna su un processo vecchio, senza che sia cambiato niente."""
        _scrivi(
            _riga(tenant, process_id=f"{tenant}-p2", created_at=IERI, cost_estimate="0.1000"),
            _riga(tenant, process_id=f"{tenant}-p2", created_at=DOMANI, cost_estimate="5.0000"),
        )
        with workspace_connection() as session:
            session.add(_validazione(tenant, process_id=f"{tenant}-p2", quando=OGGI))

        k = ledger.costo_per_as_is_validato(since=DA, until="2026-09-23T00:00:00+00:00", tenant_id=tenant)

        assert k.validazioni == 1
        assert k.costo_noto == Decimal("0.1000")

    def test_due_approvazioni_dello_stesso_processo_contano_una_volta(self, tenant):
        _scrivi(_riga(tenant, process_id=f"{tenant}-p3", created_at=IERI, cost_estimate="0.1000"))
        with workspace_connection() as session:
            session.add(_validazione(tenant, process_id=f"{tenant}-p3", quando=OGGI, versione=1))
            session.add(_validazione(tenant, process_id=f"{tenant}-p3", quando=DOMANI, versione=2))

        k = ledger.costo_per_as_is_validato(since=DA, until="2026-09-23T00:00:00+00:00", tenant_id=tenant)

        assert k.validazioni == 1

    def test_le_righe_senza_process_id_sono_il_margine_di_errore(self, tenant):
        """Non entrano nel KPI, quindi vanno dette: se sono tante il costo per
        AS-IS e' sottostimato, e il difetto e' l'attribuzione."""
        _scrivi(
            _riga(tenant, process_id=f"{tenant}-p4", created_at=IERI, cost_estimate="0.1000"),
            _riga(tenant, process_id=None, created_at=IERI, cost_estimate="9.0000"),
        )
        with workspace_connection() as session:
            session.add(_validazione(tenant, process_id=f"{tenant}-p4", quando=OGGI))

        k = ledger.costo_per_as_is_validato(since=DA, until="2026-09-23T00:00:00+00:00", tenant_id=tenant)

        assert k.costo_noto == Decimal("0.1000")
        assert k.senza_attribuzione == 1

    def test_senza_validazioni_la_media_non_si_inventa(self, tenant):
        _scrivi(_riga(tenant, process_id=f"{tenant}-p5", created_at=IERI, cost_estimate="0.1000"))

        k = ledger.costo_per_as_is_validato(since=DA, until=A, tenant_id=tenant)

        assert k.validazioni == 0
        assert k.costo_medio is None


class TestQualiPrezziMancano:
    """Il registro conta i token sempre, ma senza listino il costo e' NULL su
    ogni riga: si sa quanto si e' consumato, non quanto si e' speso."""

    def test_dice_quali_modelli_il_listino_non_conosce(self, tenant, monkeypatch):
        from backend.settings import settings

        monkeypatch.setattr(
            settings, "llm_prices_json", '{"gpt-noto": {"input": 1.0, "output": 2.0}}'
        )
        _scrivi(
            _riga(tenant, model="gpt-noto", input_tokens=10, output_tokens=0),
            _riga(tenant, model="gpt-ignoto", input_tokens=5000, output_tokens=0),
        )

        modelli = {m.model: m for m in ledger.modelli_da_prezzare(since=DA, until=A, tenant_id=tenant)}

        assert modelli["gpt-noto"].prezzato is True
        assert modelli["gpt-ignoto"].prezzato is False
        assert modelli["gpt-ignoto"].token == 5000

    def test_i_mancanti_vengono_prima_e_i_piu_pesanti_per_primi(self, tenant, monkeypatch):
        """L'ordine e' il lavoro da fare: il modello che ha bruciato piu' token
        e' quello che rende cieco il totale."""
        from backend.settings import settings

        monkeypatch.setattr(
            settings, "llm_prices_json", '{"gpt-noto": {"input": 1.0, "output": 2.0}}'
        )
        _scrivi(
            _riga(tenant, model="gpt-noto", input_tokens=9999, output_tokens=0),
            _riga(tenant, model="gpt-piccolo", input_tokens=10, output_tokens=0),
            _riga(tenant, model="gpt-grosso", input_tokens=5000, output_tokens=0),
        )

        ordine = [m.model for m in ledger.modelli_da_prezzare(since=DA, until=A, tenant_id=tenant)]

        assert ordine == ["gpt-grosso", "gpt-piccolo", "gpt-noto"]
