"""Gli eval sono un punto d'ingresso come gli altri, e spendono davvero.

Girano col modello vero (`DELIR_LIVE_LLM=1`) e sono l'unico posto in cui la
spesa nasce da un test invece che da un consulente. Senza un'operazione aperta
il gateway le rifiuterebbe - giustamente - e comunque la loro spesa non sarebbe
attribuibile: nel registro comparirebbe accanto a quella del prodotto, senza un
modo per dire «questa e' nostra, non del cliente».

`OperationKind.EVAL` esiste nel registro da P1.1 proprio per questo, e fino a
qui non lo usava nessuno.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from backend.llm import OperationKind, operation


@pytest.fixture(autouse=True)
def _eval_operation() -> Iterator[None]:
    """Ogni eval gira dentro la sua operazione.

    Una per test e non una per sessione: due esecuzioni dello stesso eval sono
    due numeri distinti, ed e' cosi' che si vede se un cambio di prompt ha reso
    il giudizio piu' caro.
    """
    with operation(OperationKind.EVAL):
        yield
