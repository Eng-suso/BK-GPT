"""Opt-in esplicito per i test che pagano il modello vero.

Prima di questo modulo i test live erano gated sulla *presenza* della chiave
(`skipif(not settings.openai_api_key)`). Con un `.env` popolato — cioe' sempre,
in sviluppo — quei test non si skippavano: giravano e pagavano. Fra il 16 e il
18/09 sono usciti ~220 giudizi di qualita' reali da tenant di test, e il credito
e' finito senza che nessuno sapesse dove.

La chiave non e' piu' un permesso: e' un requisito. Il permesso e'
`DELIR_LIVE_LLM=1`, che si esporta a mano quando si vuole pagare.

Un test che puo' chiamare il provider fa due cose:

    pytestmark = pytest.mark.live_llm          # la fixture gli lascia la chiave
    skip_unless_live()                         # e senza opt-in si salta

Il marker senza il gate paga in CI. Il gate senza il marker trova la chiave a
`None` e falla. Servono entrambi, ed e' voluto: sono due domande diverse
(«questo test puo' spendere?» e «adesso vogliamo spendere?»).
"""

from __future__ import annotations

import os

import pytest

from backend.settings import settings

#: `True` solo con l'opt-in esplicito. Nessun default che paga.
ENABLED = os.environ.get("DELIR_LIVE_LLM") == "1"


# --- il modello dei test ----------------------------------------------------
#
# I test non parlano con OpenAI: OpenAI e' il modello della produzione e delle
# prove a mano. Un test live gira su un endpoint compatibile OpenAI gratuito o
# economico, dichiarato da tre variabili:
#
#   DELIR_TEST_LLM_BASE_URL   es. https://generativelanguage.googleapis.com/v1beta/openai/
#                                 (Gemini) oppure http://localhost:11434/v1 (Ollama)
#   DELIR_TEST_LLM_API_KEY    la chiave di quel provider (per Ollama una qualsiasi)
#   DELIR_TEST_LLM_MODEL      il nome del modello per quel provider
#
# Pagare OpenAI da un test resta possibile, ma e' una scelta in piu' e non il
# ripiego silenzioso: DELIR_TEST_LLM_ALLOW_OPENAI=1, con OPENAI_API_KEY.
#
# Gli embedding restano fuori: lo schema vuole vettori a 1536 dimensioni dal
# modello OpenAI (INV-4), e un provider di test ne darebbe di altri. Sul modello
# dei test il retrieval usa il solo ramo lessicale.

TEST_LLM_BASE_URL = os.environ.get("DELIR_TEST_LLM_BASE_URL", "").strip()
TEST_LLM_API_KEY = os.environ.get("DELIR_TEST_LLM_API_KEY", "").strip()
TEST_LLM_MODEL = os.environ.get("DELIR_TEST_LLM_MODEL", "").strip()
TEST_LLM_CONFIGURED = bool(TEST_LLM_BASE_URL and TEST_LLM_API_KEY and TEST_LLM_MODEL)
ALLOW_OPENAI = os.environ.get("DELIR_TEST_LLM_ALLOW_OPENAI") == "1"


def provider_ready() -> bool:
    """C'e' un modello su cui un test live puo' girare."""
    return TEST_LLM_CONFIGURED or (ALLOW_OPENAI and bool(settings.openai_api_key))


def provider_missing_reason() -> str:
    return (
        "DELIR_LIVE_LLM=1 ma nessun modello per i test: configura DELIR_TEST_LLM_BASE_URL, "
        "DELIR_TEST_LLM_API_KEY e DELIR_TEST_LLM_MODEL (oppure DELIR_TEST_LLM_ALLOW_OPENAI=1)"
    )


def use_test_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Punta i client del backend sul modello dei test, per la durata del test.

    Non fa niente se il modello dei test non e' configurato: allora il test gira
    su OpenAI, e ci arriva solo con DELIR_TEST_LLM_ALLOW_OPENAI=1.
    """
    if not TEST_LLM_CONFIGURED:
        return
    import backend.agent as agent_module
    import backend.settings as settings_module
    from backend.memory import embeddings

    monkeypatch.setattr(settings, "openai_base_url", TEST_LLM_BASE_URL)
    monkeypatch.setattr(settings, "openai_api_key", TEST_LLM_API_KEY)
    monkeypatch.setattr(settings, "openai_model", TEST_LLM_MODEL)
    # `langchain_openai` ricade sull'ambiente quando un client non riceve la
    # chiave: anche li' deve trovare quella del modello dei test.
    monkeypatch.setenv("OPENAI_API_KEY", TEST_LLM_API_KEY)
    # Il modello della conversazione passa da una lista di modelli ammessi, e
    # uno sconosciuto torna al default di produzione: con un altro endpoint
    # sarebbe un 404.
    for module in (settings_module, agent_module):
        monkeypatch.setattr(module, "ALLOWED_MODELS", {*module.ALLOWED_MODELS, TEST_LLM_MODEL})
        monkeypatch.setattr(module, "DEFAULT_OPENAI_MODEL", TEST_LLM_MODEL)
    monkeypatch.setattr(embeddings, "available", lambda: False)


#: Per un singolo test o una singola classe, quando il resto del modulo gira
#: offline. Si impilano: `@live` dice che puo' spendere, `@needs_live` che senza
#: opt-in si salta. Per un modulo interamente live si usano invece
#: `pytestmark = pytest.mark.live_llm` e `skip_unless_live()`.
live = pytest.mark.live_llm
needs_live = pytest.mark.skipif(
    not ENABLED or not provider_ready(),
    reason="test col modello: serve DELIR_LIVE_LLM=1 e il modello dei test (DELIR_TEST_LLM_*)",
)


def skip_unless_live(*requirements: object, reason: str = "") -> None:
    """Salta il modulo se non e' lecito, o non e' possibile, chiamare il provider.

    Da chiamare a livello di modulo, dopo `pytestmark = pytest.mark.live_llm`.

    Parameters:
        requirements: Valori che devono essere tutti veri (DSN, password, chiavi
            di servizi terzi). Un requisito mancante e' una configurazione
            incompleta, non un errore: si salta.
        reason: Messaggio per i requisiti aggiuntivi. Serve a dire *quale*
            variabile manca, perche' "requisiti non configurati" non aiuta
            nessuno a rimediare.
    """
    if not ENABLED:
        pytest.skip(
            "test a pagamento: esporta DELIR_LIVE_LLM=1 per eseguirlo",
            allow_module_level=True,
        )
    if not provider_ready():
        pytest.skip(provider_missing_reason(), allow_module_level=True)
    if requirements and not all(requirements):
        pytest.skip(reason or "requisiti del test live non configurati", allow_module_level=True)
