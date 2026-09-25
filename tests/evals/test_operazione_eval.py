"""Che la fixture del conftest sia davvero addosso a ogni eval.

Gli eval veri sono skippati senza `DELIR_LIVE_LLM=1`, quindi un difetto nel
`conftest.py` accanto - un nome sbagliato, un `yield` che non entra - si
vedrebbe solo il giorno in cui si spende col modello vero, e si vedrebbe come
`OperationNotOpen` in mezzo a una passata che costa. Questo file non chiama
nessun modello: verifica la fixture, e per questo gira sempre.
"""

from __future__ import annotations

import pytest

from backend.llm import OperationKind, current_operation

_ID_VISTI: list[str] = []


def test_ogni_eval_gira_dentro_un_operazione_eval():
    operazione = current_operation()

    assert operazione is not None, "il conftest degli eval non ha aperto l'operazione"
    assert operazione.kind == OperationKind.EVAL


@pytest.mark.parametrize("giro", [1, 2])
def test_ogni_eval_ha_un_operazione_sua(giro):
    """Una per test, non una per sessione.

    Due esecuzioni dello stesso eval devono restare due numeri distinti: e' cosi'
    che si vede se un cambio di prompt ha reso il giudizio piu' caro. Il caso e'
    parametrizzato perche' il confronto ha senso solo fra due esecuzioni: con un
    giro solo l'asserzione passerebbe a vuoto.
    """
    operazione = current_operation()
    assert operazione is not None

    assert operazione.id not in _ID_VISTI, (
        f"giro {giro}: l'operazione e' la stessa del giro precedente, "
        "la fixture e' di sessione invece che di test"
    )
    _ID_VISTI.append(operazione.id)
