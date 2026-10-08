"""L'event log canonico di DeliR: uno solo per log reali e simulati.

Un log reale importato (CSV, XES) e il log che produce una simulazione finiscono
nella stessa forma, cosi' lo stesso strato analitico li legge entrambi e il
confronto simulato contro reale non ha bisogno di traduzioni.

Un evento e' l'esecuzione di un'attivita' in un caso. ``end`` c'e' sempre;
``start`` manca quando la fonte registra solo il completamento (molti export
ERP), e allora l'attesa e la lavorazione non sono separabili: chi calcola lo
deve sapere, non indovinare.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

AttributeValue = str | float | datetime
Origin = Literal["real", "simulated"]


@dataclass(frozen=True, slots=True)
class CanonicalEvent:
    case_id: str
    activity: str
    end: datetime
    start: datetime | None = None
    # Quando l'attivita' e' diventata eseguibile. Solo i log che lo registrano
    # (quelli simulati) lo hanno; per gli altri lo ricava ``kpi.to_log_events``.
    enabled: datetime | None = None
    resource: str | None = None
    role: str | None = None
    cost: float | None = None
    attributes: dict[str, AttributeValue] = field(default_factory=dict)
    # Riga del file da cui viene (1 = intestazione): per ritrovarla nel report.
    source_row: int | None = None


@dataclass(frozen=True, slots=True)
class EventLog:
    origin: Origin
    events: tuple[CanonicalEvent, ...]
    case_attributes: dict[str, dict[str, AttributeValue]] = field(default_factory=dict)
    source_name: str | None = None

    def cases(self) -> dict[str, list[CanonicalEvent]]:
        """Gli eventi per caso, in ordine di completamento."""
        by_case: dict[str, list[CanonicalEvent]] = {}
        for event in self.events:
            by_case.setdefault(event.case_id, []).append(event)
        for events in by_case.values():
            events.sort(key=lambda e: (e.start or e.end, e.end))
        return by_case

    def activities(self) -> list[str]:
        return sorted({event.activity for event in self.events})

    def resources(self) -> list[str]:
        return sorted({event.resource for event in self.events if event.resource})
