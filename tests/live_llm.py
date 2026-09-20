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


#: Per un singolo test o una singola classe, quando il resto del modulo gira
#: offline. Si impilano: `@live` dice che puo' spendere, `@needs_live` che senza
#: opt-in si salta. Per un modulo interamente live si usano invece
#: `pytestmark = pytest.mark.live_llm` e `skip_unless_live()`.
live = pytest.mark.live_llm
needs_live = pytest.mark.skipif(
    not ENABLED or not settings.openai_api_key,
    reason="test a pagamento: serve DELIR_LIVE_LLM=1 e OPENAI_API_KEY",
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
    if not settings.openai_api_key:
        pytest.skip(
            "DELIR_LIVE_LLM=1 ma OPENAI_API_KEY non e' configurata",
            allow_module_level=True,
        )
    if requirements and not all(requirements):
        pytest.skip(reason or "requisiti del test live non configurati", allow_module_level=True)
