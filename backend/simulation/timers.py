"""Timer BPMN per la simulazione (SIM-35): durate ISO 8601 e il segno che un
timer lascia nel BPMN normalizzato.

Un timer d'escalation interrompente sul bordo di un'attivita' diventa, nel BPMN
normalizzato, una decisione dopo l'attivita' (``bpmn_normalizer``). La
decisione porta in attributi di questo namespace cosa era: l'attivita', dopo
quanti secondi scatta, quale ramo e' il percorso normale. ``ir/escalations.py``
la compila nel motore con la quota dei casi che superano il timer.
"""

from __future__ import annotations

import re

DELIR_SIM_NS = "https://delir.ai/bpmn/simulation"
ESCALATION_OF = f"{{{DELIR_SIM_NS}}}escalationOf"
ESCALATION_AFTER = f"{{{DELIR_SIM_NS}}}escalationAfter"
ESCALATION_NORMAL_FLOW = f"{{{DELIR_SIM_NS}}}escalationNormalFlow"

# Solo durate fisse: anni e mesi non hanno una lunghezza in secondi.
_DURATION = re.compile(
    r"^P(?:(?P<weeks>\d+(?:\.\d+)?)W)?(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?(?:(?P<minutes>\d+(?:\.\d+)?)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)
_SECONDS = {"weeks": 604_800, "days": 86_400, "hours": 3_600, "minutes": 60, "seconds": 1}


def duration_seconds(text: str | None) -> float | None:
    """``PT48H`` -> 172800. ``None`` se non e' una durata fissa positiva."""
    if not text:
        return None
    match = _DURATION.match(text.strip().upper())
    if match is None or text.strip().upper() in {"P", "PT"} or text.strip().upper().endswith("T"):
        return None
    total = sum(float(value) * _SECONDS[unit] for unit, value in match.groupdict().items() if value)
    return total if total > 0 else None
