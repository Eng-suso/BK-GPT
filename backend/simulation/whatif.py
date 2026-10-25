"""SIM-23: what-if in linguaggio naturale (gate G4).

Il consulente scrive "un approvatore in piu' e Verifica dura il 30% in meno";
il modello traduce la frase in modifiche tipizzate dello scenario e nient'altro.
Le regole di G4 restano:

- l'LLM traduce soltanto: sceglie fra attivita' e ruoli gia' mostrati, ognuno
  con il suo id, e dice una delle cinque modifiche che il pannello sa fare;
- i limiti dei valori sono codice: una modifica fuori scala o su un id
  inventato si scarta e si conta, non si corregge a intuito;
- l'applicazione alla bozza e' deterministica e vive nel frontend
  (``whatIf.ts``), accanto a quella degli esperimenti dell'advisor;
- nessun run parte da qui: il consulente vede l'anteprima e conferma.

Senza chiave del modello la funzione non parte e lo dice: niente traduzioni
inventate da regole fatte a mano.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

MAX_SENTENCE_CHARS = 400
MAX_ACTIVITIES = 60
MAX_RESOURCES = 40

# I limiti di una modifica sensata. Oltre, e' un errore di lettura del modello.
MAX_UNITS = 200
MIN_FACTOR, MAX_FACTOR = 0.05, 20.0
MAX_MINUTES = 525_600.0
MIN_DEMAND, MAX_DEMAND = 0.1, 10.0
MAX_COST_PER_HOUR = 10_000.0

SYSTEM = """Sei l'analista di simulazione di DeliR. Il consulente descrive con una frase
uno scenario da provare sul processo. Traduci la frase in modifiche, scegliendo solo
fra queste cinque:

- resource_units: quante persone ha un ruolo [R#]. mode "set" = il numero finale,
  mode "delta" = quante in piu' (negativo = in meno).
- activity_duration: quanto dura un'attivita' [A#]. mode "factor" = moltiplicatore
  della durata (30% in meno = 0.7, il doppio = 2), mode "set" = la nuova durata media
  in minuti.
- skip_activity: la percentuale dei casi che salta un'attivita' [A#] (togliere un
  passo = 100). mode "percent".
- demand: quanti casi arrivano, come moltiplicatore (20% in piu' = 1.2). target vuoto,
  mode "factor".
- resource_cost: il costo orario in euro di un ruolo [R#]. mode "set".

Regole:
- usa solo id che compaiono qui sotto; se la frase nomina un'attivita' o un ruolo
  che non c'e', non inventarlo;
- converti ore e giorni in minuti (un giorno = 1440 minuti);
- non aggiungere modifiche che la frase non chiede;
- metti in not_understood, con le parole della frase, cio' che non sai tradurre
  con queste cinque modifiche; lascialo vuoto se hai tradotto tutto."""


class _ModelChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["resource_units", "activity_duration", "skip_activity", "demand", "resource_cost"]
    target: str = Field(description="L'id dell'attivita' (A3) o del ruolo (R1); vuoto per demand")
    mode: Literal["set", "delta", "factor", "percent"]
    value: float


class WhatIfTranslation(BaseModel):
    """La risposta del modello: modifiche con gli id mostrati, e cio' che resta fuori."""

    model_config = ConfigDict(extra="forbid")

    changes: list[_ModelChange] = Field(default_factory=list)
    not_understood: str = ""


# --- Il contratto con il frontend ---


class WhatIfActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    name: str = Field(max_length=200)


class WhatIfResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)
    name: str = Field(max_length=200)
    units: int = Field(ge=0, le=10_000)


class SimulationWhatIfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sentence: str = Field(min_length=1, max_length=MAX_SENTENCE_CHARS)
    activities: list[WhatIfActivity] = Field(default_factory=list, max_length=MAX_ACTIVITIES)
    resources: list[WhatIfResource] = Field(default_factory=list, max_length=MAX_RESOURCES)


class ResourceUnitsChange(BaseModel):
    kind: Literal["resource_units"] = "resource_units"
    resource_id: str
    units: int


class ActivityDurationChange(BaseModel):
    kind: Literal["activity_duration"] = "activity_duration"
    element_id: str
    # Uno solo dei due: il moltiplicatore, o la nuova media in minuti.
    factor: float | None = None
    mean_minutes: float | None = None


class SkipActivityChange(BaseModel):
    kind: Literal["skip_activity"] = "skip_activity"
    element_id: str
    percent: float


class DemandChange(BaseModel):
    kind: Literal["demand"] = "demand"
    factor: float


class ResourceCostChange(BaseModel):
    kind: Literal["resource_cost"] = "resource_cost"
    resource_id: str
    cost_per_hour: float


WhatIfChange = Annotated[
    ResourceUnitsChange | ActivityDurationChange | SkipActivityChange | DemandChange | ResourceCostChange,
    Field(discriminator="kind"),
]


class SimulationWhatIfResponse(BaseModel):
    changes: list[WhatIfChange]
    # Le parole della frase che il modello non ha saputo tradurre.
    not_understood: str | None = None
    # Le modifiche del modello scartate: id non mostrato, valore fuori scala, forma sbagliata.
    rejected: int = 0


class WhatIfUnavailable(RuntimeError):
    """Senza chiave del modello il what-if non parte."""


class WhatIfFailed(RuntimeError):
    """Il modello non ha risposto, o non con lo schema."""


def prompt_version() -> str:
    from backend.llm.prompts import prompt_version as version

    return version("simulation_what_if", SYSTEM, json.dumps(WhatIfTranslation.model_json_schema(), sort_keys=True))


def render(request: SimulationWhatIfRequest) -> str:
    lines = ["Attivita':"]
    lines += [f"[A{i}] {activity.name or activity.id}" for i, activity in enumerate(request.activities)]
    lines.append("")
    lines.append("Ruoli (persone oggi):")
    lines += [f"[R{i}] {resource.name or resource.id} ({resource.units})" for i, resource in enumerate(request.resources)]
    lines.append("")
    lines.append(f"Frase del consulente: {request.sentence.strip()}")
    return "\n".join(lines)


def _index(target: str, prefix: str, size: int) -> int | None:
    value = target.strip().upper().removeprefix(prefix)
    if not value.isdigit() or int(value) >= size:
        return None
    return int(value)


def _translate_one(change: _ModelChange, request: SimulationWhatIfRequest) -> WhatIfChange | None:
    """Una modifica del modello con gli id veri, o ``None`` se non si puo' fidare."""
    if change.kind in ("resource_units", "resource_cost"):
        r = _index(change.target, "R", len(request.resources))
        if r is None:
            return None
        resource = request.resources[r]
        if change.kind == "resource_cost":
            if change.mode != "set" or not 0 <= change.value <= MAX_COST_PER_HOUR:
                return None
            return ResourceCostChange(resource_id=resource.id, cost_per_hour=change.value)
        if change.value != int(change.value):
            return None
        if change.mode == "set":
            units = int(change.value)
        elif change.mode == "delta":
            units = resource.units + int(change.value)
        else:
            return None
        if not 1 <= units <= MAX_UNITS or units == resource.units:
            return None
        return ResourceUnitsChange(resource_id=resource.id, units=units)
    if change.kind == "demand":
        if change.mode != "factor" or not MIN_DEMAND <= change.value <= MAX_DEMAND or change.value == 1:
            return None
        return DemandChange(factor=change.value)
    a = _index(change.target, "A", len(request.activities))
    if a is None:
        return None
    element_id = request.activities[a].id
    if change.kind == "skip_activity":
        if change.mode != "percent" or not 0 < change.value <= 100:
            return None
        return SkipActivityChange(element_id=element_id, percent=change.value)
    if change.mode == "factor" and MIN_FACTOR <= change.value <= MAX_FACTOR and change.value != 1:
        return ActivityDurationChange(element_id=element_id, factor=change.value)
    if change.mode == "set" and 0 < change.value <= MAX_MINUTES:
        return ActivityDurationChange(element_id=element_id, mean_minutes=change.value)
    return None


def _key(change: WhatIfChange) -> tuple[str, str]:
    target = getattr(change, "resource_id", None) or getattr(change, "element_id", None) or ""
    return change.kind, target


def parse(result: WhatIfTranslation, request: SimulationWhatIfRequest) -> SimulationWhatIfResponse:
    """Le modifiche che si possono applicare, nell'ordine della frase; una sola per elemento."""
    changes: list[WhatIfChange] = []
    seen: set[tuple[str, str]] = set()
    rejected = 0
    for item in result.changes:
        translated = _translate_one(item, request)
        if translated is None or _key(translated) in seen:
            rejected += 1
            continue
        seen.add(_key(translated))
        changes.append(translated)
    note = result.not_understood.strip() or None
    return SimulationWhatIfResponse(changes=changes, not_understood=note, rejected=rejected)


def translate(process_id: str, request: SimulationWhatIfRequest) -> SimulationWhatIfResponse:
    """La frase come modifiche dello scenario.

    Raises:
        WhatIfUnavailable: Senza chiave del modello, o con il modello finto.
        WhatIfFailed: Se il modello non risponde o risponde fuori schema.
    """
    from backend.settings import settings

    if not settings.openai_api_key or settings.delir_fake_llm:
        raise WhatIfUnavailable("Il what-if in linguaggio naturale richiede la chiave del modello.")

    from langchain_core.messages import HumanMessage, SystemMessage

    from backend.llm import LlmTask, OperationKind, operation, run

    user = render(request)
    try:
        with operation(OperationKind.SIMULATION_WHAT_IF, process_id=process_id):
            result = run(
                task=LlmTask.SIMULATION_WHAT_IF,
                messages=[SystemMessage(content=SYSTEM), HumanMessage(content=user)],
                output=WhatIfTranslation,
                input_characters=len(user),
                prompt_version=prompt_version(),
            )
    except Exception as exc:
        logger.warning("Traduzione del what-if non riuscita.", exc_info=True)
        raise WhatIfFailed("Il modello non ha tradotto la frase: riprova fra poco.") from exc
    return parse(result, request)
