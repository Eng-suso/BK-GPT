"""Che L0 giri come il resto della CI: senza un'operazione EVAL addosso.

Il conftest degli eval apre un'operazione per ogni eval che spende, e lascia
fuori `l0_deterministic/`. Se l'esclusione si rompe, le invarianti girano in un
contesto che la CI non ha, e nessuno se ne accorge: questo test lo dice.
"""

from __future__ import annotations

from backend.llm import current_operation


def test_l0_non_gira_dentro_un_operazione_eval():
    assert current_operation() is None
