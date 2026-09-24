"""L6 — un test non paga il modello vero, a meno che non lo dichiari.

Prima di P0 i test live erano gated sulla *presenza* della chiave. In sviluppo
la chiave c'e' sempre, quindi giravano sempre: ~220 giudizi di qualita' reali in
due giorni, da tenant di test, fino a esaurire il credito il 18/09.

Questi test verificano il meccanismo che lo impedisce, non il suo effetto
collaterale: la chiave e' assente, il client non si costruisce, e chi lo prova
riceve un errore di configurazione invece di una chiamata.
"""

from __future__ import annotations

import os

import pytest

from backend.llm_config import MissingProviderKey, chat_openai_kwargs
from backend.settings import settings


def test_la_chiave_del_provider_non_arriva_nei_test():
    """Ne' dai settings ne' dall'ambiente: `langchain_openai` guarda entrambi."""
    assert settings.openai_api_key is None
    assert os.environ.get("OPENAI_API_KEY") is None


def test_costruire_un_client_senza_chiave_e_un_errore_di_configurazione():
    with pytest.raises(MissingProviderKey):
        chat_openai_kwargs()


def test_il_gateway_non_costruisce_un_client_senza_chiave():
    """Il percorso reale, da quando i compiti passano dal gateway.

    Prima qui si chiamava `_understanding_llm()`, il builder dell'estrazione.
    Quel builder non esiste piu': il modello lo costruisce il gateway, e senza
    chiave si ferma prima di uscire di processo — lasciando pero' la sua riga
    nel registro, perche' un'installazione senza chiave non e'
    un'installazione che spende zero perche' e' efficiente.
    """
    from backend.llm import LlmTask, OperationKind, operation
    from backend.llm import run as llm_run

    with operation(OperationKind.PLAN_SYNTHESIS):
        with pytest.raises(MissingProviderKey):
            llm_run(task=LlmTask.PLAN_EXTRACTION, messages=[])


def test_l_estrazione_dichiara_la_configurazione_mancante_invece_di_fallire_sporco():
    """Un guasto di configurazione ha un esito tipizzato, non un'eccezione nuda."""
    from backend.process_understanding import build_process_understanding

    result = build_process_understanding("Processo Test", "note di un'intervista")

    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.kind == "configuration_error"
    # Non e' un guasto transitorio: ritentarlo costa e non cambia niente.
    assert result.failure.retryable is False


@pytest.mark.live_llm
def test_un_test_marcato_live_llm_tiene_la_chiave():
    """L'opt-in e' vero: senza `DELIR_LIVE_LLM=1` questo test si salta da solo.

    Verifica il ramo opposto della fixture — il marker sospende l'azzeramento —
    senza spendere: guarda i settings, non chiama il provider.
    """
    from tests.live_llm import ENABLED

    if not ENABLED:
        pytest.skip("serve DELIR_LIVE_LLM=1")
    assert settings.openai_api_key
