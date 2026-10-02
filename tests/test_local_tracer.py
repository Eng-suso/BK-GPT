"""Le tracce che scriviamo noi, quando LangSmith non le prende.

Il contesto e' una quota: 5.000 tracce al mese, e i test ne avevano consumate
5.069 in sei giorni lasciando il prodotto cieco per il resto del mese. La
divisione che questi test proteggono e' semplice e va tenuta:

- **i test tracciano da noi**, su file, senza chiamare nessuno;
- **il prodotto traccia su LangSmith**, con la quota tutta per se'.

Quello che non deve succedere e' che le due cose si accendano insieme senza che
qualcuno l'abbia chiesto: sarebbe il doppio del lavoro per la stessa
informazione.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.llm import local_tracer


@pytest.fixture()
def cartella(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("DELIR_LOCAL_TRACE_DIR", str(tmp_path / "tracce"))
    return tmp_path / "tracce"


class TestQuandoSiAccende:
    def test_acceso_quando_langsmith_e_spento(self, monkeypatch):
        """Il caso dei test, e di chi lavora senza chiave."""
        monkeypatch.setattr("backend.settings.langsmith_tracing_enabled", lambda: False)
        monkeypatch.delenv("DELIR_LOCAL_TRACE", raising=False)

        assert local_tracer._acceso() is True
        assert len(local_tracer.local_callbacks()) == 1

    def test_spento_quando_langsmith_traccia_gia(self, monkeypatch):
        """Il caso del prodotto in esecuzione: la quota e' sua, e due tracce
        della stessa chiamata sono lavoro doppio per la stessa informazione."""
        monkeypatch.setattr("backend.settings.langsmith_tracing_enabled", lambda: True)
        monkeypatch.delenv("DELIR_LOCAL_TRACE", raising=False)

        assert local_tracer._acceso() is False
        assert local_tracer.local_callbacks() == []

    def test_si_puo_chiedere_esplicitamente_anche_con_langsmith(self, monkeypatch):
        monkeypatch.setattr("backend.settings.langsmith_tracing_enabled", lambda: True)
        monkeypatch.setenv("DELIR_LOCAL_TRACE", "1")

        assert local_tracer._acceso() is True

    def test_si_puo_spegnere_esplicitamente_anche_senza_langsmith(self, monkeypatch):
        monkeypatch.setattr("backend.settings.langsmith_tracing_enabled", lambda: False)
        monkeypatch.setenv("DELIR_LOCAL_TRACE", "0")

        assert local_tracer._acceso() is False


class TestCosaFinisceSulFile:
    def _handler(self, monkeypatch):
        monkeypatch.setattr("backend.settings.langsmith_tracing_enabled", lambda: False)
        monkeypatch.delenv("DELIR_LOCAL_TRACE", raising=False)
        return local_tracer.local_callbacks()[0]

    def _righe(self, cartella: Path) -> list[dict]:
        file = list(cartella.glob("*.jsonl"))
        assert file, "nessun file di traccia scritto"
        return [json.loads(r) for r in file[0].read_text(encoding="utf-8").splitlines() if r.strip()]

    def test_una_chiamata_lascia_inizio_e_fine(self, cartella, monkeypatch):
        from uuid import uuid4

        h = self._handler(monkeypatch)
        run = uuid4()
        h.on_llm_start({"name": "ChatOpenAI"}, ["dimmi qualcosa"], run_id=run)
        h.on_llm_end(_risposta_finta(), run_id=run)

        eventi = self._righe(cartella)
        assert [e["evento"] for e in eventi] == ["llm_start", "llm_end"]
        assert eventi[0]["prompt"] == ["dimmi qualcosa"]
        assert eventi[1]["risposta"] == ["ecco"]
        assert eventi[1]["durata_ms"] >= 0

    def test_un_guasto_lascia_la_sua_riga(self, cartella, monkeypatch):
        from uuid import uuid4

        h = self._handler(monkeypatch)
        run = uuid4()
        h.on_llm_start({"name": "ChatOpenAI"}, ["x"], run_id=run)
        h.on_llm_error(TimeoutError("troppo lento"), run_id=run)

        eventi = self._righe(cartella)
        assert eventi[-1]["evento"] == "llm_error"
        assert eventi[-1]["errore"] == "TimeoutError"

    def test_i_testi_lunghi_si_troncano(self, cartella, monkeypatch):
        from uuid import uuid4

        h = self._handler(monkeypatch)
        h.on_llm_start({"name": "ChatOpenAI"}, ["a" * 9000], run_id=uuid4())

        prompt = self._righe(cartella)[0]["prompt"][0]
        assert "troncato" in prompt
        assert len(prompt) < 9000

    def test_si_possono_tenere_solo_i_numeri(self, cartella, monkeypatch):
        """Chi non vuole i dati dei clienti su disco tiene tempi, token ed esiti."""
        from uuid import uuid4

        monkeypatch.setenv("DELIR_LOCAL_TRACE_PAYLOAD", "0")
        h = self._handler(monkeypatch)
        run = uuid4()
        h.on_llm_start({"name": "ChatOpenAI"}, ["segreto industriale"], run_id=run)
        h.on_llm_end(_risposta_finta(), run_id=run)

        eventi = self._righe(cartella)
        assert "prompt" not in eventi[0]
        assert "risposta" not in eventi[1]
        assert eventi[1]["token"]["total_tokens"] == 25

    def test_scrivere_non_solleva_mai(self, monkeypatch, tmp_path):
        """Uno strumento di osservazione che rompe la cosa osservata viene spento
        al primo incidente, e allora non osserva piu' niente."""
        from uuid import uuid4

        monkeypatch.setattr(
            local_tracer, "percorso_del_giorno", _esplode
        )
        h = self._handler(monkeypatch)

        h.on_llm_start({"name": "ChatOpenAI"}, ["x"], run_id=uuid4())  # non deve sollevare


def _esplode():
    raise OSError("disco pieno")


def _risposta_finta():
    class _Gen:
        text = "ecco"

    class _Risposta:
        generations = [[_Gen()]]
        llm_output = {
            "token_usage": {"completion_tokens": 5, "prompt_tokens": 20, "total_tokens": 25}
        }

    return _Risposta()


class TestIlPonteColRegistroDeiConsumi:
    """Il registro dice quanto e' costata una chiamata, la traccia dice cosa le
    era stato mandato. `operation_id` e' il campo che le fa parlare: senza,
    sarebbero due archivi della stessa chiamata che non sanno l'uno dell'altro."""

    def test_ogni_evento_porta_l_operazione(self, cartella, monkeypatch):
        from uuid import uuid4

        from backend.llm import OperationKind, operation

        monkeypatch.setattr("backend.settings.langsmith_tracing_enabled", lambda: False)
        monkeypatch.delenv("DELIR_LOCAL_TRACE", raising=False)
        h = local_tracer.local_callbacks()[0]

        with operation(OperationKind.PLAN_SYNTHESIS, project_id="p-1") as op:
            h.on_llm_start({"name": "ChatOpenAI"}, ["x"], run_id=uuid4())

        evento = json.loads(next(cartella.glob("*.jsonl")).read_text(encoding="utf-8").strip())
        assert evento["operation_id"] == op.id
        assert evento["operation_kind"] == OperationKind.PLAN_SYNTHESIS
        assert evento["project_id"] == "p-1"

    def test_fuori_da_un_operazione_si_traccia_lo_stesso(self, cartella, monkeypatch):
        """Uno script o un notebook non hanno un'operazione: la traccia resta
        utile anche senza il collegamento."""
        from uuid import uuid4

        monkeypatch.setattr("backend.settings.langsmith_tracing_enabled", lambda: False)
        monkeypatch.delenv("DELIR_LOCAL_TRACE", raising=False)
        h = local_tracer.local_callbacks()[0]

        h.on_llm_start({"name": "ChatOpenAI"}, ["x"], run_id=uuid4())

        evento = json.loads(next(cartella.glob("*.jsonl")).read_text(encoding="utf-8").strip())
        assert "operation_id" not in evento
        assert evento["evento"] == "llm_start"

    def test_si_rileggono_solo_gli_eventi_di_quella_operazione(self, cartella, monkeypatch):
        from uuid import uuid4

        from backend.llm import OperationKind, ledger, operation

        monkeypatch.setattr("backend.settings.langsmith_tracing_enabled", lambda: False)
        monkeypatch.delenv("DELIR_LOCAL_TRACE", raising=False)
        h = local_tracer.local_callbacks()[0]

        with operation(OperationKind.PLAN_SYNTHESIS) as mia:
            h.on_llm_start({"name": "ChatOpenAI"}, ["la mia"], run_id=uuid4())
        with operation(OperationKind.KG_INGESTION):
            h.on_llm_start({"name": "ChatOpenAI"}, ["di un altro"], run_id=uuid4())

        eventi = ledger.traccia_locale(mia.id)

        assert len(eventi) == 1
        assert eventi[0]["prompt"] == ["la mia"]

    def test_un_operazione_senza_traccia_non_e_un_guasto(self, cartella, monkeypatch):
        """La chiamata e' avvenuta con LangSmith acceso: la traccia sta li'."""
        from backend.llm import ledger

        assert ledger.traccia_locale("operazione-che-non-ha-tracce-locali") == []

    def test_una_riga_illeggibile_non_fa_cadere_la_lettura(self, cartella, monkeypatch):
        from uuid import uuid4

        from backend.llm import OperationKind, ledger, operation

        monkeypatch.setattr("backend.settings.langsmith_tracing_enabled", lambda: False)
        monkeypatch.delenv("DELIR_LOCAL_TRACE", raising=False)
        h = local_tracer.local_callbacks()[0]

        with operation(OperationKind.PLAN_SYNTHESIS) as op:
            h.on_llm_start({"name": "ChatOpenAI"}, ["buona"], run_id=uuid4())
        file = next(cartella.glob("*.jsonl"))
        with file.open("a", encoding="utf-8") as f:
            f.write("{non e' json ma contiene " + op.id + "\n")

        eventi = ledger.traccia_locale(op.id)

        assert len(eventi) == 1
