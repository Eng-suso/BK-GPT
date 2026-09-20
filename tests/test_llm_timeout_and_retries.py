"""P0.2 / P0.3 — il timeout segue l'input, e i retry stanno in un posto solo.

Due sprechi misurati il 18/09, quando il credito si e' esaurito:

- un timeout costante di 45 s tarato sul caso breve mandava in scadenza
  l'estrazione di un'intervista di 4.000 caratteri. Il tempo era pagato, il
  risultato buttato, il tentativo rifatto (caso Esaote);
- i retry dell'SDK si moltiplicavano con quelli applicativi: 2 x 2 per fonte x 5
  di coda = 20 tentativi per una fonte che fallisce.

Qui si verifica la regola, non i numeri di oggi: i numeri sono settings e
cambieranno con la misura di P1.
"""

from __future__ import annotations

import pytest

from backend.llm_config import chat_openai_kwargs, timeout_for_input
from backend.settings import settings


@pytest.fixture()
def con_chiave(monkeypatch):
    """Una chiave finta: costruire i kwargs non chiama nessuno.

    Serve perche' `chat_openai_kwargs` senza chiave alza `MissingProviderKey`,
    che e' il comportamento verificato in `test_no_live_llm_by_default.py`.
    """
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-non-usata")


class TestTimeoutSegueInput:
    def test_un_input_corto_prende_il_pavimento(self):
        assert timeout_for_input(0) == settings.model_timeout_seconds
        assert timeout_for_input(None) == settings.model_timeout_seconds

    def test_un_intervista_lunga_prende_piu_tempo_di_una_nota(self):
        nota = timeout_for_input(200)
        intervista = timeout_for_input(4_000)

        assert intervista > nota, (
            "il caso Esaote: 4.000 caratteri non si estraggono nel tempo di una nota"
        )

    def test_il_timeout_cresce_in_modo_monotono(self):
        scala = [timeout_for_input(n) for n in (0, 1_000, 4_000, 10_000, 100_000)]

        assert scala == sorted(scala)

    def test_esiste_un_tetto(self):
        """Oltre il tetto non e' lentezza, e' un compito che non finisce."""
        assert timeout_for_input(10_000_000) == settings.model_timeout_max_seconds

    def test_il_timeout_non_scende_mai_sotto_il_pavimento(self):
        assert timeout_for_input(-5) == settings.model_timeout_seconds

    def test_i_kwargs_portano_il_timeout_scalato(self, con_chiave):
        corto = chat_openai_kwargs()["timeout"]
        lungo = chat_openai_kwargs(input_characters=8_000)["timeout"]

        assert corto == settings.model_timeout_seconds
        assert lungo > corto


class TestRetryInUnPostoSolo:
    def test_di_default_i_compiti_task_scoped_non_ritentano_nell_sdk(self):
        """Dietro c'e' la coda, con il suo backoff, e il guasto e' classificato.

        Si verifica il *default dichiarato*, non il valore effettivo: `.env` puo'
        alzarlo, ed e' esattamente cosi' che lo spreco e' nato — il default era 1,
        la configurazione diceva 2, e nessuno guardava. Un deployment che vuole
        ritentare nell'SDK ora lo scrive contro un default che dice di no.
        """
        assert type(settings).model_fields["model_max_retries"].default == 0

    def test_il_task_scoped_non_ritenta_mai_piu_dei_path_interattivi(self):
        """La regola che ordina i tre valori, qualunque sia la configurazione.

        Un compito con una coda dietro non ha ragione di ritentare piu' di un
        turno di chat, che non ha niente dietro. Se questa si rompe, la gerarchia
        e' stata invertita per sbaglio.
        """
        assert settings.model_max_retries <= settings.agent_max_retries
        assert settings.model_max_retries <= settings.transcription_max_retries

    def test_i_path_interattivi_ritentano_perche_nessuno_lo_fa_per_loro(self):
        assert settings.agent_max_retries >= 1
        assert settings.transcription_max_retries >= 1

    def test_i_kwargs_portano_il_numero_configurato(self, con_chiave):
        """Il gateway non reinventa la policy: la legge dai settings."""
        assert chat_openai_kwargs()["max_retries"] == settings.model_max_retries


class TestFasceDellaCache:
    def test_le_fasce_arrotondano_per_eccesso(self):
        """Il timeout non deve mai scendere sotto quello che l'input meriterebbe."""
        from backend.process_understanding import _timeout_bucket

        for caratteri in (1, 999, 2_000, 2_001, 5_500):
            assert _timeout_bucket(caratteri) >= caratteri

    def test_le_fasce_restano_poche(self):
        """Senza arrotondamento ogni intervista costruirebbe un client nuovo."""
        from backend.process_understanding import _timeout_bucket

        fasce = {_timeout_bucket(n) for n in range(0, 20_001, 137)}

        assert len(fasce) <= 12, f"troppe fasce, la cache non serve piu': {sorted(fasce)}"
