"""Quanto puo' durare un agente prima che il runtime lo fermi.

Il ciclo agente -> tool -> agente di `build_tool_chat_subgraph` non aveva
nessun tetto: ne' di passi di decisione, ne' di chiamate a tool, ne' di tempo.
Finiva quando il modello smetteva di chiedere tool, cioe' quando **il modello**
decideva di aver finito. Con `model_timeout_seconds=45` e un retry, ogni passo
puo' costare fino a novanta secondi, e nessuno stava contando i passi.

Il budget e' politica del runtime, come il budget del loop di engineering e
quello dei tentativi di correzione del canvas: l'agente decide *cosa* fare, il
runtime decide *per quanto*. Non e' una euristica di qualita' - non giudica se
il lavoro e' fatto bene - e' una garanzia di terminazione.

Tre limiti, perche' i modi di non finire sono tre:

- `max_decision_steps`: il modello continua a ragionare senza concludere;
- `max_tool_calls`: il modello continua a leggere senza scrivere;
- `deadline_seconds`: tutto procede, ma troppo lentamente perche' qualcuno stia
  ancora aspettando dall'altra parte.

Quando un budget si esaurisce il turno **non finge di aver finito**: il
sottografo si ferma e lascia in stato il motivo, cosi' chi scrive la risposta
puo' dire che si e' fermato e perche'.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from backend.settings import settings


@dataclass(frozen=True)
class AgentBudget:
    """I limiti di un run agentico, letti dalla configurazione del server."""

    max_decision_steps: int
    max_tool_calls: int
    deadline_seconds: float

    @classmethod
    def from_settings(cls) -> "AgentBudget":
        return cls(
            max_decision_steps=max(1, int(settings.agent_max_decision_steps)),
            max_tool_calls=max(0, int(settings.agent_max_tool_calls)),
            deadline_seconds=max(1.0, float(settings.agent_run_deadline_seconds)),
        )


# Le chiavi di stato del budget. Vivono in `ConversationState`, quindi sono
# condivise fra il grafo esterno e i sottografi: il tetto vale sul run, non sul
# singolo subagente, altrimenti tre subagenti da N passi farebbero 3N passi.
STEPS_KEY = "agent_decision_steps"
TOOL_CALLS_KEY = "agent_tool_calls"
STARTED_AT_KEY = "agent_run_started_at"
EXHAUSTED_KEY = "agent_budget_exhausted"


def run_started_at(state: dict) -> float:
    """L'istante di partenza del run, fissato una volta sola.

    Riscriverlo a ogni passo renderebbe la scadenza sempre lontana, cioe'
    inesistente - lo stesso difetto per cui confrontare uno snapshot con se
    stesso rende il controllo di deriva sempre vero.
    """
    started = state.get(STARTED_AT_KEY)
    if isinstance(started, (int, float)) and started > 0:
        return float(started)
    return monotonic()


def exhausted_reason(state: dict, budget: AgentBudget, *, now: float | None = None) -> str | None:
    """Perche' questo run deve fermarsi adesso, se deve.

    Args:
        state: Lo stato del turno, non affidabile.
        budget: I limiti in vigore.
        now: L'istante corrente, iniettabile per i test.

    Returns:
        La ragione tecnica, o `None` se il run puo' proseguire.
    """
    steps = int(state.get(STEPS_KEY) or 0)
    tool_calls = int(state.get(TOOL_CALLS_KEY) or 0)
    elapsed = (now if now is not None else monotonic()) - run_started_at(state)

    if steps >= budget.max_decision_steps:
        return (
            f"Budget di passi esaurito: {steps} decisioni su un massimo di "
            f"{budget.max_decision_steps}."
        )
    if tool_calls >= budget.max_tool_calls:
        return (
            f"Budget di chiamate a strumenti esaurito: {tool_calls} su un massimo "
            f"di {budget.max_tool_calls}."
        )
    if elapsed >= budget.deadline_seconds:
        return (
            f"Tempo massimo del turno superato: {int(elapsed)}s su "
            f"{int(budget.deadline_seconds)}s."
        )
    return None


BUDGET_EXHAUSTED_MESSAGE = (
    "Mi sono fermato prima di finire: questo turno ha superato il tempo o il "
    "numero di passaggi che ha a disposizione. Quello che ho salvato resta "
    "salvato, il resto non lo racconto come fatto."
)
