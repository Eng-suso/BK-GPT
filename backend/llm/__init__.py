"""Il gateway delle chiamate al modello: un punto di passaggio, non dieci.

Prima di questo pacchetto la spesa non era attribuibile: una decina di moduli
costruiva il proprio client, e il 18/09 il credito e' finito senza che si sapesse
dove fosse andato. Qui la chiamata passa da un posto solo, dichiara il compito e
il lavoro a cui serve, e lascia una riga.

L'uso normale e' due righe:

    from backend.llm import LlmTask, OperationKind, operation, run

    with operation(OperationKind.PLAN_SYNTHESIS, process_id=process_id):
        piano = run(task=LlmTask.PLAN_EXTRACTION, messages=..., output=...)

`backend/llm_config.py` resta il posto della policy sui parametri del client, e
questo pacchetto lo usa: non l'ha sostituito.
"""

from backend.llm.gateway import OperationNotOpen, record_avoided_call, run
from backend.llm.operation import (
    Operation,
    OperationKind,
    adopt,
    current_operation,
    inherit_operation,
    new_operation,
    operation,
)
from backend.llm.tasks import LlmTask, TaskProfile, all_profiles, profile_for
from backend.llm.usage import Outcome, TokenUsage

__all__ = [
    "LlmTask",
    "Operation",
    "OperationKind",
    "OperationNotOpen",
    "Outcome",
    "TaskProfile",
    "TokenUsage",
    "adopt",
    "all_profiles",
    "current_operation",
    "inherit_operation",
    "new_operation",
    "operation",
    "profile_for",
    "record_avoided_call",
    "run",
]
