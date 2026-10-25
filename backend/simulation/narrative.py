"""SIM-24, seconda parte: la lettura di un'alternativa redatta per il cliente (gate G4).

La lettura calcolata di ``interpretation.ts`` (dove si sposta il vincolo, che
scambio c'e' fra tempo e costo) resta la fonte. Qui il modello la riscrive in
poche frasi da consegnare, e niente di piu':

- **non scrive cifre**: ogni numero lo cita con un segnaposto ``[K#]`` di un KPI
  che gli e' stato mostrato, e il codice lo sostituisce con il valore dei run;
- un testo con una cifra sua (fuori dai nomi del processo) o con un segnaposto
  che non esiste si rifiuta: resta la lettura calcolata, che il pannello mostra
  comunque;
- una differenza che l'intervallo non distingue da zero arriva marcata come
  "non certa", e il prompt chiede di non presentarla come un guadagno.

Senza chiave del modello la funzione non parte e lo dice.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

MAX_KPIS = 8
MAX_READING = 6
MAX_NAMES = 60
MAX_TEXT_CHARS = 900

SYSTEM = """Sei l'analista di DeliR e scrivi per il cliente del consulente. Ti do il
confronto, gia' calcolato, fra lo scenario attuale (AS-IS) e un'alternativa: i KPI
con il loro id [K#] e una lettura in frasi.

Scrivi da due a quattro frasi che spiegano al cliente cosa cambia con l'alternativa.

Regole:
- non scrivere nessuna cifra: per ogni numero usa il segnaposto del KPI, per esempio
  "il tempo di un caso scende di [K1]"; il segnaposto diventa il valore con il suo
  intervallo;
- un KPI marcato "non certa" non e' un miglioramento ne' un peggioramento: dillo cosi';
- non aggiungere fatti, cause o raccomandazioni che non sono nei dati;
- usa i nomi delle attivita' e dei ruoli come sono scritti;
- scrivi nella lingua indicata, in tono professionale e semplice, senza elenchi."""


class _Kpi(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    label: str = Field(min_length=1, max_length=80)
    # Gia' formattato dal pannello, con il segno e l'intervallo: "−1 h 20 min ± 12 min".
    value: str = Field(min_length=1, max_length=80)
    verdict: Literal["better", "worse", "unclear", "same"]


class SimulationNarrativeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    language: Literal["it", "en"]
    as_is_name: str = Field(min_length=1, max_length=120)
    scenario_name: str = Field(min_length=1, max_length=120)
    kpis: list[_Kpi] = Field(min_length=1, max_length=MAX_KPIS)
    reading: list[str] = Field(default_factory=list, max_length=MAX_READING)
    # I nomi di attivita', decisioni e ruoli: le cifre che contengono non sono numeri inventati.
    names: list[str] = Field(default_factory=list, max_length=MAX_NAMES)


class NarrativeDraft(BaseModel):
    """La risposta del modello: il testo con i segnaposto."""

    model_config = ConfigDict(extra="forbid")

    text: str


class SimulationNarrativeResponse(BaseModel):
    text: str
    # I KPI citati, nell'ordine in cui compaiono: "K1", "K3".
    cited: list[str]


class NarrativeUnavailable(RuntimeError):
    """Senza chiave del modello il testo non si scrive."""


class NarrativeRejected(RuntimeError):
    """Il modello non ha risposto, o ha scritto un testo che non si puo' verificare."""


_VERDICT = {
    "it": {"better": "migliore", "worse": "peggiore", "unclear": "non certa", "same": "uguale"},
    "en": {"better": "better", "worse": "worse", "unclear": "not certain", "same": "the same"},
}
_PLACEHOLDER = re.compile(r"\[K(\d+)\]")


def prompt_version() -> str:
    from backend.llm.prompts import prompt_version as version

    return version("simulation_narrative", SYSTEM, json.dumps(NarrativeDraft.model_json_schema(), sort_keys=True))


def render(request: SimulationNarrativeRequest) -> str:
    words = _VERDICT[request.language]
    lines = [
        f"Lingua: {'italiano' if request.language == 'it' else 'inglese'}",
        f"AS-IS: {request.as_is_name}",
        f"Alternativa: {request.scenario_name}",
        "",
        "KPI (alternativa contro AS-IS):",
    ]
    lines += [f"[K{i + 1}] {kpi.label}: differenza {words[kpi.verdict]}" for i, kpi in enumerate(request.kpis)]
    if request.reading:
        lines.append("")
        lines.append("Lettura calcolata (i numeri sono gia' nei KPI, non ripeterli):")
        lines += [f"- {_without_digits(line)}" for line in request.reading]
    return "\n".join(lines)


def _without_digits(line: str) -> str:
    # La lettura calcolata contiene durate e importi: al modello arriva senza, cosi' non li copia.
    return re.sub(r"[−+-]?\d[\d.,:]*\s*", "", line).strip()


def verify(draft: NarrativeDraft, request: SimulationNarrativeRequest) -> SimulationNarrativeResponse:
    """Il testo con i valori veri al posto dei segnaposto, o un errore se non si puo' fidare."""
    text = " ".join(draft.text.split())
    if not text or len(text) > MAX_TEXT_CHARS:
        raise NarrativeRejected("Il testo del modello e' vuoto o troppo lungo: resta la lettura calcolata.")
    cited: list[str] = []
    for match in _PLACEHOLDER.finditer(text):
        index = int(match.group(1))
        if not 1 <= index <= len(request.kpis):
            raise NarrativeRejected("Il testo del modello cita un KPI che non esiste: resta la lettura calcolata.")
        if f"K{index}" not in cited:
            cited.append(f"K{index}")
    # Una cifra fuori dai segnaposto e dai nomi del processo e' un numero che nessun run ha prodotto.
    stripped = _PLACEHOLDER.sub(" ", text)
    for name in sorted({request.as_is_name, request.scenario_name, *request.names}, key=len, reverse=True):
        if name:
            stripped = stripped.replace(name, " ")
    if re.search(r"\d", stripped):
        raise NarrativeRejected("Il testo del modello contiene numeri non verificabili: resta la lettura calcolata.")
    final = _PLACEHOLDER.sub(lambda m: request.kpis[int(m.group(1)) - 1].value, text)
    return SimulationNarrativeResponse(text=final, cited=cited)


def write(process_id: str, request: SimulationNarrativeRequest) -> SimulationNarrativeResponse:
    """Il testo per il cliente.

    Raises:
        NarrativeUnavailable: Senza chiave del modello, o con il modello finto.
        NarrativeRejected: Se il modello non risponde o scrive un testo non verificabile.
    """
    from backend.settings import settings

    if not settings.openai_api_key or settings.delir_fake_llm:
        raise NarrativeUnavailable("Il testo per il cliente richiede la chiave del modello.")

    from langchain_core.messages import HumanMessage, SystemMessage

    from backend.llm import LlmTask, OperationKind, operation, run

    user = render(request)
    try:
        with operation(OperationKind.SIMULATION_NARRATIVE, process_id=process_id):
            draft = run(
                task=LlmTask.SIMULATION_NARRATIVE,
                messages=[SystemMessage(content=SYSTEM), HumanMessage(content=user)],
                output=NarrativeDraft,
                input_characters=len(user),
                prompt_version=prompt_version(),
            )
    except Exception as exc:
        logger.warning("Redazione del testo per il cliente non riuscita.", exc_info=True)
        raise NarrativeRejected("Il modello non ha scritto il testo: riprova fra poco.") from exc
    return verify(draft, request)
